"""tests/test_v39_e_fab_label.py — v39 E: 수집기 버튼 라벨 '고가수집기 수집' → '고가수집기'."""
from __future__ import annotations

import json
from pathlib import Path

CS = Path("extensions/chrome-collector/content_script.js").read_text(encoding="utf-8")
MANIFEST = json.loads(Path("extensions/chrome-collector/manifest.json").read_text(encoding="utf-8"))


def test_fab_label_is_gogasujipgi():
    # FAB 라벨에서 중복 '수집' 제거 → '고가수집기'
    assert ">고가수집기</span>" in CS
    assert "고가수집기 수집" not in CS          # 옛 중복 라벨 0


def test_fab_still_always_shown_on_sourcing():
    # v38 #4: 상품 페이지 휴리스틱 가드 없이 host 게이트만(소싱처면 항상 노출) 유지
    assert "if (!looksLikeProductPage() && !kgpIsDetailUrl()) return;" not in CS
    assert "if (!kgpHostAllowed() && !kgpEntrySession()) return;" in CS


def test_extension_version_bumped():
    assert MANIFEST["version"] == "1.5.43"
