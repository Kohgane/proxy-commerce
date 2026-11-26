"""오너 11-26 감독 1 — 짧은 링크를 **렌더 IP에서** 펴 보는 실측을 서버가 스스로 남긴다.

배포(빌드)마다 첫 틱에 한 번 `a.co/d/00RG5ThB`(OKNIFE Otacle D1 — 11-25 표본)를 `link_diag.resolve_share_link`로 펴 보고
`{build, at, ok, item_id, canonical_url, reason, hops:[{status, host}], elapsed_ms}`를 `app_state link_selfprobe:last`에 적는다.
`/health/deep`의 `link_probe` 한 줄이 그걸 그대로 보인다. 읽기만(GET 리다이렉트) · 상품 페이지 본문은 받지 않는다 · 쿼리(추적값)는 안 적는다.
막히면(`ok:false`) 앱 세션에 「공유 확장이 리다이렉트를 풀어 `final_url`로 같이 보내기」를 요청한다(서버는 이미 그 힌트를 쓴다).
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

KEY = "link_selfprobe:last"
SAMPLE = os.getenv("LINK_SELFPROBE_URL", "https://a.co/d/00RG5ThB")


def last() -> dict:
    from src.db import image_translate_queue_pg as st
    return dict(st.state_get(KEY) or {})


def due(build: str) -> bool:
    """이 빌드에서 아직 안 쟀나."""
    try:
        return str(last().get("build") or "") != str(build or "")
    except Exception:                                           # noqa: BLE001 — 못 읽으면 재지 않는다(틱을 막지 않게)
        return False


def run(build: str = "") -> dict:
    from src.collectors import link_diag as L
    from src.db import image_translate_queue_pg as st
    if not build:
        from src.utils.build_info import get_build_sha
        build = get_build_sha()
    L._RESOLVED.pop(SAMPLE, None)                                # 기억해 둔 값이 아니라 지금 잰 값
    r = L.resolve_share_link(SAMPLE)
    rec = {"build": str(build), "at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "url": SAMPLE,
           "ok": bool(r.get("ok")), "item_id": r.get("item_id", ""), "canonical_url": r.get("canonical_url", ""),
           "reason": r.get("reason", ""), "hops": list(r.get("hops") or [])[:8], "elapsed_ms": int(r.get("elapsed_ms") or 0)}
    st.state_set(KEY, rec)
    logger.info("[링크 자가 실측] build=%s ok=%s reason=%s hops=%s %sms", build, rec["ok"], rec["reason"],
                "→".join(f"{h.get('host')}:{h.get('status')}" for h in rec["hops"]), rec["elapsed_ms"])
    return rec


def health_line() -> dict:
    """`/health/deep` 한 줄 — 안 쟀으면 `{measured: false}`."""
    rec = last()
    if not rec:
        return {"measured": False}
    hops = " → ".join(f"{h.get('host')} {h.get('status')}" for h in rec.get("hops") or [])
    return {"measured": True, "build": rec.get("build"), "at": rec.get("at"), "ok": rec.get("ok"),
            "line": (f"{rec.get('url')} → {rec.get('canonical_url') or '못 폄'} · {rec.get('reason')} · {hops} · {rec.get('elapsed_ms')}ms")}
