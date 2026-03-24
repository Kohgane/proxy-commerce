"""src/resilience/health_monitor.py — 종합 헬스 모니터.

외부 서비스 연결 상태, 메모리/CPU 사용량, 업타임을 모니터링한다.
Flask 앱에 /health/detailed 엔드포인트를 제공한다.

환경변수:
  HEALTH_MONITOR_TIMEOUT — 각 서비스 체크 타임아웃 초 (기본 5)
"""

import logging
import os
import time
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

_TIMEOUT = int(os.getenv("HEALTH_MONITOR_TIMEOUT", "5"))
_START_TIME = time.time()


# ──────────────────────────────────────────────────────────
# 시스템 리소스 (psutil 없이 /proc 파싱)
# ──────────────────────────────────────────────────────────

def _read_memory_mb() -> Optional[float]:
    """현재 프로세스 메모리 사용량(MB)을 읽는다. /proc 기반 (Linux)."""
    try:
        import resource
        usage = resource.getrusage(resource.RUSAGE_SELF)
        # maxrss: Linux에서 kilobytes
        return round(usage.ru_maxrss / 1024, 1)
    except Exception:
        return None


def _read_cpu_times() -> Optional[Dict[str, float]]:
    """현재 프로세스 CPU 시간을 읽는다. /proc/self/stat 기반."""
    try:
        with open("/proc/self/stat", "r") as f:
            fields = f.read().split()
        utime = int(fields[13])
        stime = int(fields[14])
        clk_tck = os.sysconf("SC_CLK_TCK")
        return {
            "user_seconds": round(utime / clk_tck, 2),
            "system_seconds": round(stime / clk_tck, 2),
        }
    except Exception:
        return None


# ──────────────────────────────────────────────────────────
# 외부 서비스 체크
# ──────────────────────────────────────────────────────────

def _check_google_sheets() -> Dict[str, Any]:
    """Google Sheets 연결 상태를 확인한다."""
    sheet_id = os.getenv("GOOGLE_SHEET_ID", "")
    if not sheet_id:
        return {"ok": False, "reason": "GOOGLE_SHEET_ID 미설정"}
    try:
        from ..utils.sheets import open_sheet
        worksheet_name = os.getenv("WORKSHEET", "catalog")
        open_sheet(sheet_id, worksheet_name)
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "reason": str(exc)[:120]}


def _check_shopify() -> Dict[str, Any]:
    """Shopify API 연결 상태를 확인한다."""
    shop = os.getenv("SHOPIFY_SHOP", "")
    token = os.getenv("SHOPIFY_ACCESS_TOKEN", "")
    if not shop or not token:
        return {"ok": False, "reason": "SHOPIFY 환경변수 미설정"}
    try:
        import urllib.request
        url = f"https://{shop}/admin/api/{os.getenv('SHOPIFY_API_VERSION', '2024-07')}/shop.json"
        req = urllib.request.Request(
            url,
            headers={"X-Shopify-Access-Token": token},
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            if resp.status == 200:
                return {"ok": True}
            return {"ok": False, "reason": f"HTTP {resp.status}"}
    except Exception as exc:
        return {"ok": False, "reason": str(exc)[:120]}


def _check_woocommerce() -> Dict[str, Any]:
    """WooCommerce API 연결 상태를 확인한다."""
    base_url = os.getenv("WOO_BASE_URL", "")
    ck = os.getenv("WOO_CK", "")
    cs = os.getenv("WOO_CS", "")
    if not base_url or not ck or not cs:
        return {"ok": False, "reason": "WOOCOMMERCE 환경변수 미설정"}
    try:
        import urllib.request
        import base64
        version = os.getenv("WOO_API_VERSION", "wc/v3")
        url = f"{base_url.rstrip('/')}/wp-json/{version}/system_status"
        credentials = base64.b64encode(f"{ck}:{cs}".encode()).decode()
        req = urllib.request.Request(url, headers={"Authorization": f"Basic {credentials}"})
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            if resp.status == 200:
                return {"ok": True}
            return {"ok": False, "reason": f"HTTP {resp.status}"}
    except Exception as exc:
        return {"ok": False, "reason": str(exc)[:120]}


def _check_deepl() -> Dict[str, Any]:
    """DeepL API 연결 상태를 확인한다."""
    api_key = os.getenv("DEEPL_API_KEY", "")
    if not api_key:
        return {"ok": False, "reason": "DEEPL_API_KEY 미설정"}
    try:
        import urllib.request
        api_url = os.getenv("DEEPL_API_URL", "https://api-free.deepl.com/v2/translate")
        usage_url = api_url.replace("/translate", "/usage")
        req = urllib.request.Request(
            usage_url,
            headers={"Authorization": f"DeepL-Auth-Key {api_key}"},
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            if resp.status == 200:
                return {"ok": True}
            return {"ok": False, "reason": f"HTTP {resp.status}"}
    except Exception as exc:
        return {"ok": False, "reason": str(exc)[:120]}


# ──────────────────────────────────────────────────────────
# 헬스 모니터
# ──────────────────────────────────────────────────────────

class HealthMonitor:
    """종합 헬스 모니터.

    Flask 앱에 /health/detailed 엔드포인트를 등록하거나,
    독립적으로 get_status()를 호출해 사용할 수 있다.
    """

    def __init__(self, app=None, start_time: Optional[float] = None):
        self._start_time = start_time or _START_TIME
        if app is not None:
            self.init_app(app)

    def init_app(self, app) -> None:
        """Flask 앱에 /health/detailed 엔드포인트를 등록한다."""
        from flask import jsonify

        @app.get("/health/detailed")
        def health_detailed():
            status = self.get_status(include_external=True)
            code = 200 if status["overall"] == "ok" else 503
            return jsonify(status), code

    def get_status(self, include_external: bool = True) -> Dict[str, Any]:
        """전체 시스템 상태를 딕셔너리로 반환한다.

        Args:
            include_external: 외부 서비스 체크 포함 여부 (기본 True)

        Returns:
            {
                "overall": "ok" | "degraded",
                "uptime_seconds": float,
                "timestamp": str,
                "system": {...},
                "services": {...},
            }
        """
        import datetime
        now = datetime.datetime.now(tz=datetime.timezone.utc)
        uptime = round(time.time() - self._start_time, 1)

        result: Dict[str, Any] = {
            "timestamp": now.isoformat(),
            "uptime_seconds": uptime,
            "system": self._get_system_info(),
            "services": {},
        }

        if include_external:
            result["services"] = self._check_all_services()

        all_services_ok = all(v.get("ok", False) for v in result["services"].values()) if result["services"] else True
        result["overall"] = "ok" if all_services_ok else "degraded"
        return result

    def _get_system_info(self) -> Dict[str, Any]:
        """메모리, CPU 정보를 반환한다."""
        info: Dict[str, Any] = {}
        mem = _read_memory_mb()
        if mem is not None:
            info["memory_mb"] = mem
        cpu = _read_cpu_times()
        if cpu is not None:
            info["cpu"] = cpu
        return info

    def _check_all_services(self) -> Dict[str, Any]:
        """등록된 외부 서비스 연결 상태를 모두 확인한다."""
        services: Dict[str, Any] = {}

        # Google Sheets
        services["google_sheets"] = _check_google_sheets()

        # Shopify (환경변수 설정 시에만)
        if os.getenv("SHOPIFY_SHOP"):
            services["shopify"] = _check_shopify()

        # WooCommerce (환경변수 설정 시에만)
        if os.getenv("WOO_BASE_URL"):
            services["woocommerce"] = _check_woocommerce()

        # DeepL (환경변수 설정 시에만)
        if os.getenv("DEEPL_API_KEY"):
            services["deepl"] = _check_deepl()

        return services
