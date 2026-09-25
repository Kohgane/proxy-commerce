"""src/services/image_gen_remove.py — D3-5 ① **생성형 지우기**(Cloudinary `e_gen_remove`).

## 왜 (오너 브리프 D3-5, 2026-09-25)

> 「쓰여지기 전 이미지」 복원 품질. 글자 마스크 영역을 먼저 Cloudinary `e_gen_remove`로
> 지운 결과를 받아 그 위에 렌더. **telea는 폴백.**

`cv2.inpaint`(TELEA)는 **주변 색을 안쪽으로 번지게** 메운다. 단색·그라데이션 배경엔 충분하지만
**사진 위 글자**(호환성 장 등)에선 그 자리가 뭉개진 얼룩으로 남는다. 생성형 지우기는
그 자리에 **있었을 법한 텍스처**를 새로 그린다 — 그게 F축이 재려는 차이다.

## 문서에서 확인한 것만 쓴다 (발명 0, Context7 · cloudinary.com/documentation)

| 무엇 | 값 | 출처 |
|---|---|---|
| 문법 | `e_gen_remove:region_((x_<x>;y_<y>;w_<w>;h_<h>)[;…;(x_…)])` | 변환 레퍼런스 `gen_remove` |
| 영역 | **프롬프트 또는 영역** 중 하나. 영역은 여러 개 가능 | 〃 |
| fetch 이미지 | **지원 안 함** → 업로드가 먼저 있어야 한다 | 〃 Notes |
| 투명 이미지 | 지원 안 함(불투명만) | 〃 |
| 큰 이미지 | 최대 **6140×6140**으로 줄였다가 다시 키운다(화질 영향) | 〃 |
| 비동기 | 파생본 생성 중이면 **423**, incoming 변환이면 **420 pending** | 〃 |
| 준비 | **eager 변환**으로 업로드 시점에 미리 만들 수 있다 | 〃 · eager 문서 |
| 과금 | **50 tx** — 표준 변환 수에 **더해서** | 「Effects with special counts」 |
| 환산 | **1 크레딧 = 1,000 변환** | 「Credits (Free plan and self-service paid plans)」 |
| 지역 | **아시아·태평양 데이터센터에선 못 쓴다** | 〃 Notes |

⚠️ **문서가 말하지 않은 것** — 영역 **개수·크기 상한**은 적혀 있지 않다(프롬프트 쪽에
「아주 작거나 아주 큰 물체는 못 찾을 수 있다」는 말만 있다). 그래서 상한을 지어 두지 않고,
공급사가 거절하면 **그 원문을 그대로** 들고 나온다.

⚠️ 문서 예시 문자열 일부는 **닫는 괄호가 잘려** 있다(`region_((x_300;y_200;w_750;h_500`).
우리는 예시가 아니라 **형식 정의**(레퍼런스의 문법 줄)를 따른다.

## 원가 한 줄

한 장 = `gen_remove` **1회**(영역 여러 개를 한 효과에 담는다) = **50 + 1 = 51 tx ≈ 0.051 크레딧**.
「+1」은 파생본 하나를 새로 만드는 표준 변환이다(문서: 변환은 **새 파생본을 만들 때만** 센다).

★ **청구됐는지는 우리가 추정하지 않는다.** 파생본 주소가 돌아왔으면 만들어진 것이고(청구됨),
업로드부터 실패했으면 0이다. **그 사이**(업로드는 됐는데 eager 결과가 비었다)는 **모른다** —
`tx=None`으로 남긴다. 0으로 적으면 쓴 돈을 안 쓴 것처럼 보인다.
"""
from __future__ import annotations

import logging
import time
from typing import Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)

#: 문서 「Effects with special counts」 — Generative remove.
TX_GEN_REMOVE = 50
#: 새 파생본 하나 = 표준 변환 1(특수 카운트는 이것에 **더해진다**).
TX_BASE = 1
#: 문서 「Credits」 — One credit equals 1,000 transformations.
TX_PER_CREDIT = 1000

#: 문서: 파생본 생성 중이면 423, incoming 변환이면 420 pending.
_PENDING_STATUSES = (420, 423)
_PENDING_RETRIES = 3
_PENDING_WAIT_SEC = 2.0


def region_param(rects: Sequence[Tuple[int, int, int, int]]) -> str:
    """`[(x,y,w,h), …]` → `region_((x_…;y_…;w_…;h_…);(…))` (레퍼런스 문법 그대로).

    0 이하 폭·높이는 **보내지 않는다** — 공급사가 뭐라고 할지 모르는 값을 만들지 않는다.
    """
    parts = []
    for r in rects or []:
        x, y, w, h = (int(v) for v in r)
        if w <= 0 or h <= 0:
            continue
        parts.append(f"(x_{max(0, x)};y_{max(0, y)};w_{w};h_{h})")
    if not parts:
        return ""
    return "region_(" + ";".join(parts) + ")"


def cost_of(calls: int) -> Dict:
    """`{tx, credits}` — **문서 상수로만** 계산한다."""
    n = max(0, int(calls or 0))
    tx = n * (TX_GEN_REMOVE + TX_BASE)
    return {"tx": tx, "credits": round(tx / TX_PER_CREDIT, 4)}


def _eager_url(eager: List) -> str:
    for e in eager or []:
        if not isinstance(e, dict):
            continue
        url = e.get("secure_url") or e.get("url")
        if url:
            return str(url)
    return ""


def _download(url: str) -> Dict:
    """파생본 받기 — 423/420이면 **짧게 몇 번** 기다린다(문서: 준비될 때까지 그 코드를 준다)."""
    import requests

    last = {"ok": False, "bytes": b"", "http_status": None, "error": "", "raw": ""}
    for attempt in range(_PENDING_RETRIES):
        try:
            r = requests.get(url, timeout=60)
        except Exception as exc:
            last.update(error=f"파생본을 받지 못했습니다: {type(exc).__name__}")
            return last
        last["http_status"] = r.status_code
        if r.status_code == 200 and r.content:
            last.update(ok=True, bytes=r.content, error="")
            return last
        # 헤더·본문을 **그대로** 조금 싣는다 — 공급사가 이유를 어디에 적는지 우리가 정하지 않는다.
        hdr = {k: v for k, v in (getattr(r, "headers", {}) or {}).items()
               if "error" in str(k).lower()}
        last["raw"] = (str(hdr) + " " + (getattr(r, "text", "") or "")[:200]).strip()
        if r.status_code in _PENDING_STATUSES and attempt < _PENDING_RETRIES - 1:
            time.sleep(_PENDING_WAIT_SEC)
            continue
        if r.status_code in _PENDING_STATUSES:
            last["error"] = (f"파생본이 아직 준비되지 않았습니다(HTTP {r.status_code}, "
                             f"{_PENDING_RETRIES}회 기다림)")
        else:
            last["error"] = f"파생본을 받지 못했습니다 (HTTP {r.status_code})"
        return last
    return last                                                # pragma: no cover


def gen_remove(image_bytes: bytes,
               rects: Sequence[Tuple[int, int, int, int]]) -> Dict:
    """글자 영역을 **생성형으로 지운** 바이트 — `{ok, image_bytes, tx, credits, …}`.

    실패하면 `ok=False` + 사유이고, **원본을 지운 척 돌려주지 않는다**
    (`image_bytes`는 빈 값). 호출부(`image_text_render.render`)가 telea로 폴백한다.
    """
    out: Dict = {"ok": False, "image_bytes": b"", "tx": 0, "credits": 0.0,
                 "public_id": "", "url": "", "http_status": None, "error": "",
                 "raw": "", "regions": len(rects or []), "effect": ""}
    region = region_param(rects)
    if not region:
        out["error"] = "지울 영역이 없습니다(글자 마스크가 비었다)"
        return out
    effect = f"gen_remove:{region}"
    out["effect"] = effect

    from src.media.image_pipeline import upload_bytes
    up = upload_bytes(image_bytes, eager=[{"effect": effect}])
    out["public_id"] = up.get("public_id", "")
    if not up.get("ok"):
        # 업로드부터 실패 — 파생본은 **안 만들어졌다**. 청구 0은 추정이 아니라 사실이다.
        out["error"] = "업로드 실패: " + (up.get("error") or "사유 불명")
        return out

    url = _eager_url(up.get("eager") or [])
    if not url:
        # 업로드는 됐는데 eager 결과가 없다 — **만들어졌는지 모른다.** 0으로 적지 않는다.
        out.update(tx=None, credits=None,
                   error=("eager 결과에 파생본 주소가 없습니다 — 응답 키: "
                          + (", ".join(up.get("keys") or []) or "(비어 있음)")))
        return out

    # 파생본 주소가 돌아왔다 = **만들어졌다** = 청구됐다.
    c = cost_of(1)
    out.update(url=url, tx=c["tx"], credits=c["credits"])
    got = _download(url)
    out.update(http_status=got["http_status"], raw=got.get("raw", ""))
    if not got["ok"]:
        out["error"] = got["error"]
        return out
    out.update(ok=True, image_bytes=got["bytes"])
    return out


def configured() -> Tuple[bool, str]:
    """쓸 수 있나 — `(가능, 사유)`. **부르기 전에** 화면이 말할 수 있게."""
    import os

    from src.media.image_pipeline import _CDN_UPLOAD_ENABLED, _cloudinary_configured
    if not _CDN_UPLOAD_ENABLED:
        return False, "IMAGE_CDN_UPLOAD_ENABLED=0 — Cloudinary 업로드가 꺼져 있습니다"
    if not _cloudinary_configured():
        return False, "Cloudinary 자격 미설정 — gen_remove를 쓸 수 없습니다"
    if os.getenv("ADAPTER_DRY_RUN", "0") == "1":
        return False, "ADAPTER_DRY_RUN=1 — 외부 호출을 막았습니다"
    return True, ""
