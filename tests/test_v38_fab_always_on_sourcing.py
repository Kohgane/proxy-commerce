"""tests/test_v38_fab_always_on_sourcing.py — v38 #4: 고가수집기 FAB 소싱처 항상 노출 + SPA 재주입."""
from __future__ import annotations

import json
import re
from pathlib import Path

CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
MANIFEST = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))


def test_fab_no_longer_gated_by_product_heuristic():
    # 소싱처에선 상품 페이지 휴리스틱과 무관하게 노출 — 옛 가드(조기 return) 제거
    assert "if (!looksLikeProductPage() && !kgpIsDetailUrl()) return;" not in CS
    # host 게이트는 유지(소싱처/앱 진입에 한정)
    assert "if (!kgpHostAllowed() && !kgpEntrySession()) return;" in CS


def test_spa_reinjection_observer_and_history_hooks():
    # SPA 라우팅/재렌더에도 버튼 유지 — MutationObserver + history pushState/replaceState 후킹
    assert "MutationObserver" in CS
    assert "pushState" in CS and "replaceState" in CS
    assert "popstate" in CS


def test_list_vs_detail_still_mutually_exclusive():
    # 목록=중앙 바 / 상세=우측 FAB 상호배타(동시 노출 0) 유지
    assert "kgpRemoveFab()" in CS and "kgpInjectListing()" in CS
    assert "kgpRemoveListing()" in CS and "injectCollectButton()" in CS


def test_extension_version_bumped():
    assert MANIFEST["version"] == "1.5.140"
