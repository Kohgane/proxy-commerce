"""
tests/test_google_credentials.py — GoogleCredentialsLoader 단위 테스트.
"""

import base64
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from src.utils.google_credentials import GoogleCredentialsLoader, CredentialsLoadError


# ── 공통 fixtures ─────────────────────────────────────────────────────────────

def _make_sa_dict(**overrides) -> dict:
    """유효한 서비스 계정 JSON dict 생성."""
    base = {
        "type": "service_account",
        "project_id": "test-project",
        "private_key_id": "key123",
        "private_key": "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0Z3VS5JJcds\n-----END RSA PRIVATE KEY-----\n",
        "client_email": "svc@test-project.iam.gserviceaccount.com",
        "client_id": "123",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }
    base.update(overrides)
    return base


def _b64_encode(obj: dict) -> str:
    """dict → base64 문자열 (LF 없이)."""
    return base64.b64encode(json.dumps(obj).encode()).decode()


# ── 소스 우선순위 테스트 ──────────────────────────────────────────────────────

class TestCredentialsLoaderPriority:

    def test_source1_google_application_credentials(self, tmp_path):
        """GOOGLE_APPLICATION_CREDENTIALS 파일이 있으면 1순위로 사용."""
        sa = _make_sa_dict()
        sa_file = tmp_path / "sa.json"
        sa_file.write_text(json.dumps(sa))

        with patch.dict(os.environ, {"GOOGLE_APPLICATION_CREDENTIALS": str(sa_file)}):
            loader = GoogleCredentialsLoader()
            result = loader.load()

        assert result["client_email"] == sa["client_email"]
        assert loader.source == "GOOGLE_APPLICATION_CREDENTIALS"

    def test_source2_render_secret_file(self, tmp_path):
        """GOOGLE_APPLICATION_CREDENTIALS 미설정 시 Secret File 사용."""
        sa = _make_sa_dict()
        sf_path = tmp_path / "service-account.json"
        sf_path.write_text(json.dumps(sa))

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
            loader = GoogleCredentialsLoader()
            loader.SECRET_FILE_PATHS = [str(sf_path)]
            result = loader.load()

        assert result["client_email"] == sa["client_email"]
        assert loader.source == f"secret_file:{sf_path}"

    def test_source4_b64_env(self):
        """Secret File 없으면 GOOGLE_SERVICE_JSON_B64 사용."""
        sa = _make_sa_dict()
        b64 = _b64_encode(sa)

        env = {"GOOGLE_SERVICE_JSON_B64": b64}
        with patch.dict(os.environ, env):
            os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
            loader = GoogleCredentialsLoader()
            loader.SECRET_FILE_PATHS = []  # Secret File 비활성
            result = loader.load()

        assert result["client_email"] == sa["client_email"]
        assert loader.source == "GOOGLE_SERVICE_JSON_B64"

    def test_source5_raw_json_env(self):
        """b64 env도 없으면 GOOGLE_SERVICE_JSON 사용."""
        sa = _make_sa_dict()
        raw = json.dumps(sa)

        env = {"GOOGLE_SERVICE_JSON": raw}
        with patch.dict(os.environ, env):
            os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
            os.environ.pop("GOOGLE_SERVICE_JSON_B64", None)
            loader = GoogleCredentialsLoader()
            loader.SECRET_FILE_PATHS = []
            result = loader.load()

        assert result["client_email"] == sa["client_email"]
        assert loader.source == "GOOGLE_SERVICE_JSON"

    def test_source6_local_dev_file(self, tmp_path, monkeypatch):
        """모든 env 없으면 로컬 service-account.json 사용."""
        sa = _make_sa_dict()
        sa_file = tmp_path / "service-account.json"
        sa_file.write_text(json.dumps(sa))

        monkeypatch.chdir(tmp_path)
        env_clear = {"GOOGLE_SERVICE_JSON_B64": "", "GOOGLE_SERVICE_JSON": ""}
        with patch.dict(os.environ, env_clear):
            os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
            loader = GoogleCredentialsLoader()
            loader.SECRET_FILE_PATHS = []
            result = loader.load()

        assert loader.source == "local_file"
        assert result["client_email"] == sa["client_email"]

    def test_no_source_raises(self):
        """아무 소스도 없으면 CredentialsLoadError 발생."""
        with patch.dict(os.environ, {"GOOGLE_SERVICE_JSON_B64": "", "GOOGLE_SERVICE_JSON": ""}):
            os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
            loader = GoogleCredentialsLoader()
            loader.SECRET_FILE_PATHS = []
            loader.DEV_FILE_PATH = "/nonexistent/path/service-account.json"
            with pytest.raises(CredentialsLoadError):
                loader.load()


# ── b64 인코딩 edge case 테스트 ───────────────────────────────────────────────

class TestB64Decoding:

    def _load_from_b64(self, b64_str: str) -> dict:
        """GOOGLE_SERVICE_JSON_B64 만 설정하고 로드."""
        env = {"GOOGLE_SERVICE_JSON_B64": b64_str}
        with patch.dict(os.environ, env):
            os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
            loader = GoogleCredentialsLoader()
            loader.SECRET_FILE_PATHS = []
            return loader.load()

    def test_b64_crlf_normalized(self):
        """CRLF가 포함된 base64 → 정상 처리 (Windows-style)."""
        sa = _make_sa_dict()
        raw_b64 = _b64_encode(sa)
        # 76자마다 CRLF 삽입 (Windows base64 도구 스타일)
        chunked = "\r\n".join(raw_b64[i:i+76] for i in range(0, len(raw_b64), 76))
        result = self._load_from_b64(chunked)
        assert result["client_email"] == sa["client_email"]

    def test_b64_extra_spaces_stripped(self):
        """base64 문자열에 공백이 섞여있어도 정상 처리."""
        sa = _make_sa_dict()
        raw_b64 = _b64_encode(sa)
        spaced = "  " + raw_b64[:20] + "  " + raw_b64[20:]
        result = self._load_from_b64(spaced)
        assert result["client_email"] == sa["client_email"]

    def test_b64_invalid_raises_friendly_error(self):
        """잘못된 base64 → CredentialsLoadError + 친절한 메시지."""
        with pytest.raises(CredentialsLoadError) as exc_info:
            self._load_from_b64("THIS IS NOT VALID JSON BASE64!!@#$%")
        # 에러 메시지에 힌트 포함 여부 확인
        assert "힌트" in str(exc_info.value) or "base64" in str(exc_info.value).lower()

    def test_b64_invalid_json_shows_first_chars(self):
        """base64는 성공하나 JSON이 아닌 경우 → 첫 문자 노출."""
        # base64 of "not json"
        b64 = base64.b64encode(b"not json at all").decode()
        with pytest.raises(CredentialsLoadError) as exc_info:
            self._load_from_b64(b64)
        err = str(exc_info.value)
        assert "JSON 파싱 실패" in err


# ── private_key \n 처리 ───────────────────────────────────────────────────────

class TestPrivateKeyNormalization:

    def test_literal_backslash_n_converted(self):
        """private_key에 literal \\n이 있으면 실제 개행으로 변환."""
        sa = _make_sa_dict()
        # literal \n (이스케이프되지 않은 상태로 JSON에 들어간 경우)
        sa["private_key"] = "-----BEGIN RSA PRIVATE KEY-----\\nMIIE\\n-----END RSA PRIVATE KEY-----\\n"
        b64 = _b64_encode(sa)

        env = {"GOOGLE_SERVICE_JSON_B64": b64}
        with patch.dict(os.environ, env):
            os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
            loader = GoogleCredentialsLoader()
            loader.SECRET_FILE_PATHS = []
            result = loader.load()

        # literal \n → 실제 \n으로 변환됐는지 확인
        assert "\\n" not in result["private_key"]
        assert "\n" in result["private_key"]


# ── 필수 필드 검증 테스트 ─────────────────────────────────────────────────────

class TestRequiredFieldValidation:

    def _load_b64(self, sa_dict: dict) -> dict:
        b64 = _b64_encode(sa_dict)
        env = {"GOOGLE_SERVICE_JSON_B64": b64}
        with patch.dict(os.environ, env):
            os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)
            loader = GoogleCredentialsLoader()
            loader.SECRET_FILE_PATHS = []
            return loader.load()

    def test_missing_type_raises(self):
        """type 필드 누락 → CredentialsLoadError."""
        sa = _make_sa_dict()
        del sa["type"]
        with pytest.raises(CredentialsLoadError) as exc_info:
            self._load_b64(sa)
        assert "'type'" in str(exc_info.value)

    def test_missing_project_id_raises(self):
        """project_id 필드 누락 → CredentialsLoadError."""
        sa = _make_sa_dict()
        del sa["project_id"]
        with pytest.raises(CredentialsLoadError) as exc_info:
            self._load_b64(sa)
        assert "'project_id'" in str(exc_info.value)

    def test_wrong_type_raises(self):
        """type이 'service_account'가 아니면 → CredentialsLoadError."""
        sa = _make_sa_dict(type="authorized_user")
        with pytest.raises(CredentialsLoadError) as exc_info:
            self._load_b64(sa)
        assert "service_account" in str(exc_info.value)


# ── BOM 처리 ──────────────────────────────────────────────────────────────────

class TestBomHandling:

    def test_bom_stripped_from_file(self, tmp_path):
        """BOM이 붙은 파일도 정상 파싱."""
        sa = _make_sa_dict()
        bom_content = b"\xef\xbb\xbf" + json.dumps(sa).encode("utf-8")
        sa_file = tmp_path / "sa_bom.json"
        sa_file.write_bytes(bom_content)

        with patch.dict(os.environ, {"GOOGLE_APPLICATION_CREDENTIALS": str(sa_file)}):
            loader = GoogleCredentialsLoader()
            result = loader.load()

        assert result["type"] == "service_account"
