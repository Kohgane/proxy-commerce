import logging
import os
from typing import Any, Dict, List, Optional

import gspread
from oauth2client.service_account import ServiceAccountCredentials

from .google_credentials import GoogleCredentialsLoader, CredentialsLoadError

logger = logging.getLogger(__name__)

SCOPES = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']

# 필수 워크시트 목록
_REQUIRED_WORKSHEETS = ["catalog", "orders", "fx_rates", "fx_history"]

# 자동 워크시트 생성 옵트인 (AUTO_BOOTSTRAP_SHEETS=1 시 활성화)
_AUTO_BOOTSTRAP = os.getenv("AUTO_BOOTSTRAP_SHEETS", "0") == "1"

# 모듈 레벨 로더 (소스 기록 공유)
_loader = GoogleCredentialsLoader()


def get_credentials_dict() -> dict:
    """다중 소스에서 서비스 계정 자격증명 dict 반환."""
    return _loader.load()


def get_credentials_source() -> Optional[str]:
    """마지막으로 성공한 자격증명 소스 반환 (None = 아직 로드 안 됨)."""
    return _loader.source


def _service_account():
    data = get_credentials_dict()
    creds = ServiceAccountCredentials.from_json_keyfile_dict(data, SCOPES)
    client = gspread.authorize(creds)
    return client


def open_sheet(sheet_id: str, worksheet: str):
    """Google Sheets 워크시트 열기 (없으면 자동 생성)."""
    client = _service_account()
    sh = client.open_by_key(sheet_id)
    try:
        ws = sh.worksheet(worksheet)
    except gspread.exceptions.WorksheetNotFound:
        logger.info("Worksheet '%s' not found, creating...", worksheet)
        ws = sh.add_worksheet(title=worksheet, rows=1000, cols=20)
    return ws


def open_sheet_object(sheet_id: str):
    """Google Sheets Spreadsheet 객체 반환 (워크시트 선택 없이)."""
    client = _service_account()
    return client.open_by_key(sheet_id)


def get_or_create_worksheet(sheet, name: str, headers: Optional[List[str]] = None):
    """워크시트 없으면 생성 + 헤더 작성.

    AUTO_BOOTSTRAP_SHEETS=1 환경변수로 옵트인.
    옵트인 안 된 경우에도 워크시트가 이미 있으면 그대로 반환.

    Args:
        sheet: gspread Spreadsheet 인스턴스
        name: 워크시트 이름
        headers: 첫 번째 행에 쓸 헤더 리스트 (워크시트 신규 생성 시만 적용)

    Returns:
        gspread Worksheet 인스턴스
    """
    try:
        ws = sheet.worksheet(name)
        return ws
    except gspread.exceptions.WorksheetNotFound:
        if not _AUTO_BOOTSTRAP:
            logger.warning(
                "워크시트 '%s' 없음 — AUTO_BOOTSTRAP_SHEETS=1 로 자동 생성 가능", name
            )
            raise

        cols = max(len(headers or []), 10)
        ws = sheet.add_worksheet(title=name, rows=1000, cols=cols)
        logger.info("워크시트 '%s' 자동 생성 완료", name)
        if headers:
            ws.update("A1", [headers])
            logger.info("워크시트 '%s' 헤더 작성: %s", name, headers)
        return ws


def get_worksheet(name: str, headers: Optional[List[str]] = None) -> Optional[gspread.Worksheet]:
    """기본 Spreadsheet에서 워크시트 반환 (GOOGLE_SHEET_ID 사용).

    워크시트가 없으면 AUTO_BOOTSTRAP_SHEETS=1 시 자동 생성.
    키 미설정 시 None 반환 (graceful).

    Args:
        name: 워크시트 이름
        headers: 신규 생성 시 첫 행 헤더

    Returns:
        gspread Worksheet 인스턴스 또는 None
    """
    sheet_id = os.getenv("GOOGLE_SHEET_ID")
    if not sheet_id:
        logger.debug("GOOGLE_SHEET_ID 미설정 — 워크시트 '%s' 건너뜀", name)
        return None
    try:
        sh = open_sheet_object(sheet_id)
        return get_or_create_worksheet(sh, name, headers=headers)
    except Exception as exc:
        logger.debug("워크시트 '%s' 접근 실패: %s", name, exc)
        return None


def _is_duplicate_header_error(exc: Exception) -> bool:
    """중복/비정상 헤더로 인한 get_all_records 예외인지 판별한다."""
    if not isinstance(exc, (ValueError, gspread.exceptions.GSpreadException)):
        return False
    message = str(exc).lower()
    if "not unique" in message:
        return True
    return any(token in message for token in ("header row", "duplicate header", "duplicated header"))


def _dedupe_headers(headers: List[Any]) -> List[str]:
    """헤더 행을 비어 있음/중복 없음 상태로 정규화한다."""
    normalized: List[str] = []
    seen: Dict[str, int] = {}

    for index, header in enumerate(headers, start=1):
        base = str(header or "").strip() or f"col_{index}"
        count = seen.get(base, 0) + 1
        seen[base] = count
        normalized.append(base if count == 1 else f"{base}_{count}")

    return normalized


def get_all_records_safe(
    ws: gspread.Worksheet,
    expected_headers: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """중복 헤더가 있어도 안전하게 워크시트 레코드 목록을 반환한다.

    기본적으로는 gspread의 ``get_all_records()``를 그대로 사용한다.
    다만 헤더 중복/비정상으로 인한 예외가 발생하면 raw 값을 읽어 첫 행 헤더를
    자동 보정한 뒤 각 행을 dict로 매핑해 반환한다.
    """
    try:
        if expected_headers is None:
            return ws.get_all_records()
        return ws.get_all_records(expected_headers=expected_headers)
    except Exception as exc:
        if not _is_duplicate_header_error(exc):
            raise

        logger.warning(
            "중복 헤더 감지로 안전 로더 폴백 사용: worksheet=%s",
            getattr(ws, "title", "<unknown>"),
        )

        values = ws.get_all_values()
        if not values:
            return []

        raw_headers = values[0]
        if not any(str(header or "").strip() for header in raw_headers):
            return []

        headers = _dedupe_headers(raw_headers)
        records: List[Dict[str, Any]] = []
        for row in values[1:]:
            padded = list(row) + [""] * max(0, len(headers) - len(row))
            record = {header: padded[index] for index, header in enumerate(headers)}
            records.append(record)
        return records


def diagnose_sheets_connection() -> Dict[str, Any]:
    """Google Sheets 연결을 단계별로 진단하고 상세 결과를 반환한다.

    GoogleCredentialsLoader를 통해 다중 소스 자격증명을 로드한 뒤
    시트 열기 + 워크시트 존재 확인까지 수행한다.

    보안: private_key, 토큰 등 시크릿 값은 절대 반환하지 않는다.
    """
    loader = GoogleCredentialsLoader()

    # 자격증명 로드
    try:
        data = loader.load()
    except CredentialsLoadError as exc:
        return {
            "status": "fail",
            "detail": f"자격증명 로드 실패: {exc}",
            "hint": (
                "다음 중 하나를 설정하세요: "
                "Secret File /etc/secrets/service-account.json, "
                "GOOGLE_SERVICE_JSON_B64, GOOGLE_SERVICE_JSON"
            ),
        }

    svc_email = data.get("client_email", "")
    cred_source = loader.source

    # 서비스 계정 인증
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(data, SCOPES)
        client = gspread.authorize(creds)
    except Exception as exc:
        return {
            "status": "fail",
            "detail": f"서비스 계정 인증 실패: {exc}",
            "service_account": svc_email,
            "source": cred_source,
        }

    # 시트 열기
    sheet_id = os.getenv('GOOGLE_SHEET_ID', '')
    if not sheet_id:
        return {
            "status": "skip",
            "detail": "GOOGLE_SHEET_ID 환경변수 미설정",
            "hint": "Render 환경변수 탭에서 GOOGLE_SHEET_ID 추가",
            "service_account": svc_email,
            "source": cred_source,
        }
    try:
        sh = client.open_by_key(sheet_id)
    except gspread.exceptions.APIError as exc:
        status_code = getattr(getattr(exc, 'response', None), 'status_code', 0)
        masked_id = _mask_sheet_id(sheet_id)
        if status_code == 403:
            return {
                "status": "fail",
                "detail": f"permission denied — 시트 접근 권한 없음 (ID: {masked_id})",
                "hint": (
                    f"Google Sheets 공유 메뉴에서 '{svc_email}'을 편집자로 추가했는지 확인. "
                    f"또는 GOOGLE_SHEET_ID 환경변수가 시트 URL의 /d/와 /edit 사이 부분과 일치하는지 확인"
                ),
                "service_account": svc_email,
                "source": cred_source,
            }
        if status_code == 404:
            return {
                "status": "fail",
                "detail": f"spreadsheet not found — 시트를 찾을 수 없음 (ID: {masked_id})",
                "hint": "GOOGLE_SHEET_ID가 올바른지 확인 (시트 URL의 /d/ 다음 부분)",
                "service_account": svc_email,
                "source": cred_source,
            }
        return {
            "status": "fail",
            "detail": f"시트 열기 실패: {exc}",
            "service_account": svc_email,
            "source": cred_source,
        }
    except Exception as exc:
        return {
            "status": "fail",
            "detail": f"시트 열기 실패: {exc}",
            "service_account": svc_email,
            "source": cred_source,
        }

    # 필수 워크시트 존재 확인
    try:
        existing = {ws.title for ws in sh.worksheets()}
        missing_ws = [ws for ws in _REQUIRED_WORKSHEETS if ws not in existing]
        if missing_ws:
            return {
                "status": "fail",
                "detail": f"누락된 워크시트: {missing_ws}",
                "hint": f"Google Sheets에 다음 워크시트 생성 필요: {missing_ws}",
                "service_account": svc_email,
                "source": cred_source,
            }
    except Exception as exc:
        # 워크시트 목록 조회 실패는 non-fatal (연결은 됐음)
        logger.warning("diagnose_sheets_connection: worksheets 조회 실패: %s", exc)

    return {
        "status": "ok",
        "detail": "연결 성공",
        "service_account": svc_email,
        "source": cred_source,
    }


def _mask_sheet_id(sheet_id: str) -> str:
    """시트 ID 마스킹 (앞 4자 + *** + 뒤 4자)."""
    if len(sheet_id) <= 8:
        return "***"
    return f"{sheet_id[:4]}***{sheet_id[-4:]}"
