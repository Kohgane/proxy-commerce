import base64
import json
import logging
import os
from typing import Any, Dict

import gspread
from oauth2client.service_account import ServiceAccountCredentials

logger = logging.getLogger(__name__)

SCOPES = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']

# 필수 워크시트 목록
_REQUIRED_WORKSHEETS = ["catalog", "orders", "fx_rates", "fx_history"]


def _service_account():
    b64 = os.getenv('GOOGLE_SERVICE_JSON_B64')
    if not b64:
        raise RuntimeError('GOOGLE_SERVICE_JSON_B64 missing')
    data = json.loads(base64.b64decode(b64))
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


def diagnose_sheets_connection() -> Dict[str, Any]:
    """Google Sheets 연결을 단계별로 진단하고 상세 결과를 반환한다.

    각 단계:
      1. GOOGLE_SERVICE_JSON_B64 base64 디코딩
      2. JSON 파싱
      3. private_key 형식 검증 (literal \\n 처리)
      4. 서비스 계정 인증
      5. GOOGLE_SHEET_ID 시트 열기
      6. 필수 워크시트 존재 확인

    보안: private_key, 토큰 등 시크릿 값은 절대 반환하지 않는다.
    """
    # 단계 1: base64 디코딩
    b64 = os.getenv('GOOGLE_SERVICE_JSON_B64', '')
    if not b64:
        return {
            "status": "skip",
            "detail": "GOOGLE_SERVICE_JSON_B64 환경변수 미설정",
            "hint": "Render 환경변수 탭에서 GOOGLE_SERVICE_JSON_B64 추가",
        }
    try:
        raw = base64.b64decode(b64)
    except Exception as exc:
        return {
            "status": "fail",
            "detail": f"base64 decode 실패: {exc}",
            "hint": "base64 -w 0 service-account.json | tr -d '\\n' 으로 다시 인코딩",
        }

    # 단계 2: JSON 파싱
    try:
        data = json.loads(raw)
    except Exception as exc:
        return {
            "status": "fail",
            "detail": f"JSON 파싱 실패: {exc}",
            "hint": "공백/개행 제거 후 다시 시도",
        }

    # 단계 3: private_key 형식 검증
    private_key = data.get("private_key", "")
    if private_key and "\\n" in private_key and "\n" not in private_key:
        # literal \n → 실제 개행으로 치환
        data["private_key"] = private_key.replace("\\n", "\n")
        logger.info("diagnose_sheets_connection: private_key literal \\n → 실제 개행으로 치환")

    svc_email = data.get("client_email", "")

    # 단계 4: 서비스 계정 인증
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(data, SCOPES)
        client = gspread.authorize(creds)
    except Exception as exc:
        return {
            "status": "fail",
            "detail": f"서비스 계정 인증 실패: {exc}",
            "service_account": svc_email,
        }

    # 단계 5: 시트 열기
    sheet_id = os.getenv('GOOGLE_SHEET_ID', '')
    if not sheet_id:
        return {
            "status": "skip",
            "detail": "GOOGLE_SHEET_ID 환경변수 미설정",
            "hint": "Render 환경변수 탭에서 GOOGLE_SHEET_ID 추가",
            "service_account": svc_email,
        }
    try:
        sh = client.open_by_key(sheet_id)
    except gspread.exceptions.APIError as exc:
        status_code = getattr(getattr(exc, 'response', None), 'status_code', 0)
        if status_code == 403:
            return {
                "status": "fail",
                "detail": "permission denied — 시트 접근 권한 없음",
                "hint": (
                    f"시트의 공유 메뉴에서 서비스계정 이메일 ({svc_email}) 을 편집자로 추가"
                ),
                "service_account": svc_email,
            }
        if status_code == 404:
            return {
                "status": "fail",
                "detail": "spreadsheet not found — 시트를 찾을 수 없음",
                "hint": "GOOGLE_SHEET_ID가 올바른지 확인 (시트 URL의 /d/ 다음 부분)",
                "service_account": svc_email,
            }
        return {
            "status": "fail",
            "detail": f"시트 열기 실패: {exc}",
            "service_account": svc_email,
        }
    except Exception as exc:
        return {
            "status": "fail",
            "detail": f"시트 열기 실패: {exc}",
            "service_account": svc_email,
        }

    # 단계 6: 필수 워크시트 존재 확인
    try:
        existing = {ws.title for ws in sh.worksheets()}
        missing_ws = [ws for ws in _REQUIRED_WORKSHEETS if ws not in existing]
        if missing_ws:
            return {
                "status": "fail",
                "detail": f"누락된 워크시트: {missing_ws}",
                "hint": f"Google Sheets에 다음 워크시트 생성 필요: {missing_ws}",
                "service_account": svc_email,
            }
    except Exception as exc:
        # 워크시트 목록 조회 실패는 non-fatal (연결은 됐음)
        logger.warning("diagnose_sheets_connection: worksheets 조회 실패: %s", exc)

    return {
        "status": "ok",
        "detail": "연결 성공",
        "service_account": svc_email,
    }
