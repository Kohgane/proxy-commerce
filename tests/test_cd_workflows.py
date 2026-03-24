"""tests/test_cd_workflows.py — CD 워크플로 YAML 파싱 테스트.

시크릿 조건 체크 존재 여부를 검증한다.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

WORKFLOWS_DIR = os.path.join(os.path.dirname(__file__), "..", ".github", "workflows")


def _read_workflow(filename: str) -> str:
    path = os.path.join(WORKFLOWS_DIR, filename)
    with open(path, encoding="utf-8") as f:
        return f.read()


class TestCdStagingWorkflow:
    """cd_staging.yml 워크플로 시크릿 조건 체크 테스트."""

    def setup_method(self):
        self.content = _read_workflow("cd_staging.yml")

    def test_render_hook_has_empty_check(self):
        """Deploy to Render 스텝에 시크릿 빈값 조건이 있어야 한다."""
        assert "RENDER_DEPLOY_HOOK_STAGING != ''" in self.content, (
            "Deploy to Render 스텝에 RENDER_DEPLOY_HOOK_STAGING 빈값 체크가 없습니다."
        )

    def test_healthcheck_has_app_url_check(self):
        """Post-deploy healthcheck 스텝에 APP_URL 조건이 있어야 한다."""
        assert "STAGING_APP_URL != ''" in self.content, (
            "Post-deploy healthcheck 스텝에 STAGING_APP_URL 빈값 체크가 없습니다."
        )

    def test_notify_success_has_telegram_check(self):
        """Notify success 스텝에 텔레그램 토큰 조건이 있어야 한다."""
        assert "STAGING_TELEGRAM_BOT_TOKEN != ''" in self.content, (
            "Notify success 스텝에 STAGING_TELEGRAM_BOT_TOKEN 빈값 체크가 없습니다."
        )

    def test_notify_failure_has_telegram_check(self):
        """Notify failure 스텝에 텔레그램 토큰 조건이 있어야 한다."""
        assert "failure()" in self.content
        assert "STAGING_TELEGRAM_BOT_TOKEN != ''" in self.content

    def test_curl_not_called_unconditionally(self):
        """curl 이 조건 없이 직접 호출되지 않아야 한다 (빈 URL 방지)."""
        lines = self.content.splitlines()
        for i, line in enumerate(lines):
            if "curl -fsSL -X POST" in line and "RENDER_DEPLOY_HOOK" in line:
                # 앞의 줄에 if 조건이 있어야 함
                preceding = "\n".join(lines[max(0, i - 5):i])
                assert "if:" in preceding, (
                    f"curl 호출 (줄 {i + 1}) 앞에 if 조건이 없습니다."
                )


class TestCdProductionWorkflow:
    """cd_production.yml 워크플로 시크릿 조건 체크 테스트."""

    def setup_method(self):
        self.content = _read_workflow("cd_production.yml")

    def test_render_hook_has_empty_check(self):
        """Deploy to Render 스텝에 시크릿 빈값 조건이 있어야 한다."""
        assert "RENDER_DEPLOY_HOOK_PRODUCTION != ''" in self.content, (
            "Deploy to Render 스텝에 RENDER_DEPLOY_HOOK_PRODUCTION 빈값 체크가 없습니다."
        )

    def test_healthcheck_has_app_url_check(self):
        """Post-deploy healthcheck 스텝에 APP_URL 조건이 있어야 한다."""
        assert "PRODUCTION_APP_URL != ''" in self.content, (
            "Post-deploy healthcheck 스텝에 PRODUCTION_APP_URL 빈값 체크가 없습니다."
        )

    def test_rollback_hook_guarded(self):
        """롤백 훅도 빈값 체크가 있어야 한다."""
        assert "RENDER_ROLLBACK_HOOK_PRODUCTION" in self.content
        # if 조건 또는 shell 빈값 체크
        assert (
            "RENDER_ROLLBACK_HOOK_PRODUCTION != ''" in self.content
            or '[ -n "${{ secrets.RENDER_ROLLBACK_HOOK_PRODUCTION }}"' in self.content
        ), "RENDER_ROLLBACK_HOOK_PRODUCTION 빈값 체크가 없습니다."

    def test_notify_failure_has_telegram_check(self):
        """Notify failure 스텝에 텔레그램 토큰 조건이 있어야 한다."""
        assert "PROD_TELEGRAM_BOT_TOKEN != ''" in self.content
