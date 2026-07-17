#!/usr/bin/env python3
"""scripts/gen_coverage_matrix.py — v75 STEP1: docs/coverage_matrix.md 생성(레지스트리에서 파생).

근거는 실페이지 하네스 픽스처(fixtures/realpages/*.expected.json)의 실제 어서션뿐(추측 기입 금지).
sourcing_registry.coverage 데이터 단일 소스에서 9항목 매트릭스 + 오너 스냅샷 요청 목록을 렌더한다.
수기 편집 금지 — 이 스크립트로 재생성. 가드 test_v75_coverage_matrix가 파생 정합을 강제한다.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.collectors.sourcing_registry import coverage_matrix_rows, snapshot_needed  # noqa: E402

_LEVEL_KO = {"full": "완전 지원", "partial": "부분 지원", "unverified": "미검증"}


def render() -> str:
    rows = coverage_matrix_rows()
    L = []
    L.append("# 디폴트 소싱처 커버리지 매트릭스 (v75 STEP1)\n")
    L.append("> 근거는 **실페이지 하네스 픽스처**(`fixtures/realpages/<fixture>.expected.json`)의 실제 어서션뿐이다.")
    L.append("> 추측 기입 금지 — 픽스처 없는 마켓은 '픽스처 필요'(오너 스냅샷 제출 후 하네스 검증).")
    L.append("> 버튼 3열(목록·호버·상세)은 **제네릭 타일 감지**로 전 사이트 보장(v70/v74). 추출 6열은 하네스 검증분만 ✓.\n")
    L.append("| 마켓 | 도메인 | 목록 | 호버 | 상세 | 제목 | 가격+통화 | 갤러리 | 옵션 | 상세 | 리뷰 | 지원수준 | 근거 픽스처 |")
    L.append("|---|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|---|")
    for r in rows:
        L.append("| {label} | {domains} | {list_btn} | {hover} | {detail_btn} | {title} | {price} | {gallery} | {options} | {description} | {reviews} | {lv} | {fx} |".format(
            lv=_LEVEL_KO.get(r["level"], r["level"]), fx=(r["fixture"] or "—"), **r))
    L.append("\n## 오너 스냅샷 요청 목록 (미검증 마켓)")
    L.append("각 사이트의 **상품 상세 1곳**에서 확장 팝업 '진단 스냅샷 저장'으로 스냅샷을 커밋하면 하네스 계약을 추가한다.\n")
    for s in snapshot_needed():
        L.append(f"- [ ] **{s['label']}** (`{s['domains']}`) → `fixtures/realpages/{s['id']}-detail.html` + `.expected.json`")
    L.append("\n## 수리 우선순위 (× 칸 중 3핵심=제목·가격·갤러리 미달)")
    L.append("픽스처 도착 순서대로 마켓당 1커밋(하네스 계약 동반)으로 어댑터/제네릭 보강. 현재 검증 완료: **아마존·테무(완전), 알리(부분·상세/리뷰 남음)**.")
    L.append("\n> 이 파일은 `src/collectors/sourcing_registry.py`의 coverage 데이터에서 파생(수기 편집 금지). 재생성: `python scripts/gen_coverage_matrix.py`.")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out = os.path.join(root, "docs", "coverage_matrix.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write(render())
    print("wrote", out)
