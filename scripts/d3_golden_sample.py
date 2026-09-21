#!/usr/bin/env python3
"""D3 골든 샘플 — 1·2·3단계를 한 번에 돌려 before/after와 5축 채점표를 낸다.

## 쓰는 법

    python scripts/d3_golden_sample.py <이미지경로|URL> [--out docs/screens/d3/]
    # 텐센트 자격증명 필요(1단계). 없으면 무엇이 없는지 말하고 멈춘다.

## 무엇이 나오나

| 파일 | 무엇 |
|---|---|
| `golden-before.jpg` | 원본 |
| `golden-tencent.jpg` | 텐센트 **렌더본**(비교용 — 우리가 버리는 그것) |
| `golden-after.jpg` | **우리 3단계** 결과(지우고 다시 쓴 것) |

그리고 표준출력에 **줄별 표**(원문 → 우리 번역 → 그렸나/왜 안 그렸나)와
**5축 채점 서식**, **장당 원가**가 찍힌다.

## ★ 채점은 사람이 한다

이 스크립트는 **채점표를 채워 주지 않는다** — 축마다 「무엇을 보라」만 적고 빈칸을 남긴다.
스스로 매긴 점수로 스스로를 통과시키면 그건 측정이 아니다. A·B·D는 기계가 재는 부분이
있어 그 수치를 같이 찍고, **C(박스 수납)·E(타이포)는 눈으로 보는 것**이다.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.getcwd())

import argparse
import base64
from pathlib import Path

AXES = [
    ("A", "브랜드 보존", "워드마크(PORTER 등)가 번역되거나 음차되지 않았나"),
    ("B", "관용구", "三合一 같은 표현이 직역(「삼합일」)으로 남지 않았나"),
    ("C", "박스 수납", "글자가 박스를 넘거나 옆 요소를 덮지 않았나 · 지운 자국이 보이지 않나"),
    ("D", "영문 UI", "제품 화면 속 영문·숫자(12:30·START)에 없던 한국어가 생기지 않았나"),
    ("E", "타이포", "읽을 수 있는 크기인가 · 줄바꿈이 어색하지 않나 · 굵기가 맞나"),
]


def _load(src: str) -> bytes:
    if src.startswith(("http://", "https://")):
        import requests
        r = requests.get(src, timeout=30)
        r.raise_for_status()
        return r.content
    return Path(src).read_bytes()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("image", help="골든 샘플 이미지(경로 또는 URL) — 수행방패 갤러리 1")
    ap.add_argument("--out", default="docs/screens/d3", help="결과를 쓸 디렉터리")
    ap.add_argument("--method", default="telea", choices=["telea", "ns"])
    args = ap.parse_args()

    from src.services import image_text_glossary as G
    from src.services import image_text_render as R
    from src.services import image_translate_tencent as T

    if not T.is_configured():
        print("텐센트 자격증명이 없습니다 — 1단계(박스+원문)를 못 얻습니다.")
        print("필요: TENCENT_SECRET_ID · TENCENT_SECRET_KEY")
        return 2

    raw = _load(args.image)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "golden-before.jpg").write_bytes(raw)

    # 1단계 — 박스 + 원문만 쓴다(렌더본은 비교용으로만 저장).
    res = T.translate_image(data=raw, mode=0)
    if not res.get("ok"):
        print(f"1단계 실패: {res.get('error') or res}")
        return 1
    if res.get("image_b64"):
        (out_dir / "golden-tencent.jpg").write_bytes(base64.b64decode(res["image_b64"]))
    lines = res.get("lines") or []
    print(f"1단계: 줄 {len(lines)}개 · 원문언어={res.get('source_lang')}\n")

    # 2단계 — 우리가 번역한다. 번역기는 주입이다.
    def _translate(text: str) -> str:
        from src.ai.translator import AITranslator
        return AITranslator().translate(text, target="ko")

    rows = G.translate_lines(lines, _translate)

    # 3단계 — 지우고 쓴다.
    out = R.render(raw, rows, method=args.method)
    (out_dir / "golden-after.jpg").write_bytes(out["image_bytes"])

    print(f"{'원문':<28} {'우리 번역':<28} 결과")
    print("-" * 78)
    skipped = {s.get("text"): s.get("reason") for s in out.get("skipped", [])}
    for r in rows:
        src_t = (r.get("source") or "")[:26]
        got = (r.get("render_text") or "")[:26]
        mark = r.get("action")
        if r.get("translate_error"):
            mark = f"원문유지({r['translate_error'][:20]})"
        elif got in skipped:
            mark = f"안 그림 — {skipped[got][:30]}"
        print(f"{src_t:<28} {got:<28} {mark}")

    print(f"\n지움 {out['erased']}박스 · 그림 {out['drawn']}줄 · 건너뜀 {len(out['skipped'])}줄")
    print(G.summarize(rows))

    print("\n== 장당 원가 ==")
    print("  텐센트 ImageTranslateLLM 1콜 = (공식 단가표 확인 후 기입)")
    print("  LLM 번역 = 줄 %d개 × (프로바이더 단가) " % len(rows))
    print("  ※ 실제 청구서로 확인하기 전까지 숫자를 쓰지 않는다.")

    print("\n== 5축 채점 (사람이 채운다) ==")
    for key, name, what in AXES:
        print(f"  [{key}] {name:<8} □통과 □미달   — {what}")
    print("\n  before/after: %s" % out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
