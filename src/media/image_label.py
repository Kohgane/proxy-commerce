"""src/media/image_label.py — Cloudinary에 올리는 이미지의 **이름표 하나**.

## 왜 (오너 실측 2026-09-25 · D3-6 ⓪ → 2026-09-26 0-b)

D3-6에서 벤치 결과에만 이름표(`<run>_<product>_p<page>_<pipeline>`)를 붙였다. 그런데 오너가 실제로
보는 것은 **셀러 경로**(상품 편집 → 이미지 번역) 결과였고, 그쪽은 여전히 무작위 public_id였다
(`xyazoygebncalnyewnxu.jpg` · `prgyknh91xdd8gxblvde.webp`). **벤치만 이름이 붙으면 오너가 보는 건 늘 이름 없는 쪽이다.**

그래서 규칙을 **한 곳**에 둔다. 올리는 자리는 전부 `upload_bytes(label=…)`를 지나고,
이름은 여기서만 만든다(두 벌이면 한쪽만 고쳐진다).

## 모양

`<폴더>/<run>_<product>_p<page>_<pipeline>` — 영숫자·`-`·`_`만(Cloudinary public_id 규칙).
같은 값을 `context`에도 둔다(콘솔에서 검색).

| pipeline | 무엇 |
|---|---|
| TENCENT | 공급사(텐센트) 번역본 |
| TELEA · GEN_REMOVE | D3 렌더본(실제로 쓴 인페인터 이름) |
| ORIGINAL | 원본 저장본(내려받아 그대로 · 또는 크기·형식만 정리) |
| CLEAN | 셀러가 누른 「이미지 정제」 결과 |
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Dict, Optional

PIPELINES = ("TENCENT", "TELEA", "GEN_REMOVE", "ORIGINAL", "CLEAN")
_KEYS = ("run_id", "item_no", "page", "pipeline")


def run_stamp(prefix: str) -> str:
    """실행 이름표 — `<prefix>-YYYYMMDD-HHMMSS`(UTC). 벤치의 `bench_run_id`와 같은 모양."""
    return datetime.now(timezone.utc).strftime(f"{prefix}-%Y%m%d-%H%M%S")


def make_label(run_id: str, item_no, page, pipeline: str, *, folder: str) -> Dict[str, str]:
    if pipeline not in PIPELINES:
        raise ValueError(f"모르는 파이프라인: {pipeline}")
    return {"run_id": str(run_id or ""), "item_no": str(item_no or ""),
            "page": str(page if page is not None else ""), "pipeline": pipeline,
            "folder": str(folder or "")}


def public_id(label: Dict[str, str]) -> str:
    """`{run_id, item_no, page, pipeline}` → public_id. 쓸 수 없는 글자는 `-`로."""
    parts = [label.get("run_id", ""), label.get("item_no", ""),
             f"p{label.get('page', '')}", label.get("pipeline", "")]
    return "_".join(re.sub(r"[^A-Za-z0-9_-]", "-", str(p)) for p in parts if str(p))


def upload_opts(label: Optional[Dict[str, str]]) -> Dict:
    """`upload_bytes`가 쓰는 `{folder, public_id, context}`. 이름표가 없으면 빈 dict."""
    if not label:
        return {}
    return {"folder": str(label.get("folder") or ""), "public_id": public_id(label),
            "context": {k: str(label.get(k, "")) for k in _KEYS}}
