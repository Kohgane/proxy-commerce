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
