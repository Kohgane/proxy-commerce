"""
Google 서비스 계정 자격증명 다중 소스 로더.

우선순위:
1. GOOGLE_APPLICATION_CREDENTIALS (파일 경로)
2. /etc/secrets/service-account.json (Render Secret File)
3. /etc/secrets/google-service-account.json
4. GOOGLE_SERVICE_JSON_B64 (base64 인코딩된 JSON)
5. GOOGLE_SERVICE_JSON (raw JSON 문자열)
6. ./service-account.json (개발용)
"""

import base64
import json
import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class CredentialsLoadError(Exception):
    pass


class GoogleCredentialsLoader:
    """Google 서비스 계정 자격증명을 다양한 소스에서 로드한다."""

    SECRET_FILE_PATHS = [
        "/etc/secrets/service-account.json",
        "/etc/secrets/google-service-account.json",
    ]
    DEV_FILE_PATH = "service-account.json"

    def __init__(self):
        self.source: Optional[str] = None
        self.error: Optional[str] = None

    def load(self) -> dict:
        """자격증명을 dict로 반환. 실패 시 CredentialsLoadError.
        성공 시 self.source에 사용된 소스 기록.
        """
        # 1. GOOGLE_APPLICATION_CREDENTIALS
        path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if path and Path(path).is_file():
            return self._load_from_file(path, source="GOOGLE_APPLICATION_CREDENTIALS")

        # 2~3. Secret File 경로들
        for sf_path in self.SECRET_FILE_PATHS:
            if Path(sf_path).is_file():
                return self._load_from_file(sf_path, source=f"secret_file:{sf_path}")

        # 4. b64 env
        b64 = os.getenv("GOOGLE_SERVICE_JSON_B64", "").strip()
        if b64:
            return self._load_from_b64(b64)

        # 5. raw JSON env
        raw = os.getenv("GOOGLE_SERVICE_JSON", "").strip()
        if raw:
            return self._load_from_raw(raw)

        # 6. 개발용 파일
        if Path(self.DEV_FILE_PATH).is_file():
            return self._load_from_file(self.DEV_FILE_PATH, source="local_file")

        raise CredentialsLoadError(
            "자격증명 소스를 찾을 수 없음. 다음 중 하나 필요: "
            "Secret File /etc/secrets/service-account.json, "
            "GOOGLE_SERVICE_JSON_B64, GOOGLE_SERVICE_JSON"
        )

    def _load_from_file(self, path: str, source: str) -> dict:
        with open(path, "rb") as f:
            data = f.read()
        return self._parse_bytes(data, source=source)

    def _load_from_b64(self, b64: str) -> dict:
        # CRLF/LF 정규화 + 공백 제거
        clean = b64.replace("\r", "").replace("\n", "").replace(" ", "").strip()
        try:
            # 패딩 정규화 (길이가 4의 배수가 되도록)
            padding = (4 - len(clean) % 4) % 4
            decoded = base64.b64decode(clean + "=" * padding, validate=True)
        except Exception as exc:
            raise CredentialsLoadError(
                f"GOOGLE_SERVICE_JSON_B64 base64 디코드 실패: {exc}. "
                f"길이={len(clean)} 첫문자={clean[:10]!r}. "
                f"힌트: base64 -w 0 service-account.json 으로 다시 인코딩"
            )
        return self._parse_bytes(decoded, source="GOOGLE_SERVICE_JSON_B64")

    def _load_from_raw(self, raw: str) -> dict:
        return self._parse_bytes(raw.encode("utf-8"), source="GOOGLE_SERVICE_JSON")

    def _parse_bytes(self, data: bytes, source: str) -> dict:
        # BOM 제거
        if data.startswith(b"\xef\xbb\xbf"):
            data = data[3:]
        text = data.decode("utf-8", errors="replace").strip()
        try:
            obj = json.loads(text)
        except json.JSONDecodeError as e:
            raise CredentialsLoadError(
                f"{source} JSON 파싱 실패: {e}. "
                f"첫 문자: {text[:30]!r}. "
                f"힌트: 파일 형식이 올바른지, base64 인코딩 시 LF/개행 옵션 확인"
            )
        # private_key의 literal \n 처리
        if "private_key" in obj and "\\n" in obj["private_key"] and "\n" not in obj["private_key"]:
            obj["private_key"] = obj["private_key"].replace("\\n", "\n")
        # 필수 필드 검증
        for required in ("type", "project_id", "private_key", "client_email"):
            if required not in obj:
                raise CredentialsLoadError(
                    f"{source} JSON에 필수 필드 '{required}' 누락"
                )
        if obj.get("type") != "service_account":
            raise CredentialsLoadError(
                f"{source} JSON의 type이 'service_account'가 아님: {obj.get('type')!r}"
            )
        self.source = source
        return obj
