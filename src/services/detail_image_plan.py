"""Y9(오너 2026-10-13) — 상세 이미지: 텐센트 본선으로 보내기 전 정리 · 등록에 나갈 장 고르기.

실측(VRSUK 라운지체어 4ebaf1b8): 상세 28장이 D3(글자 지우기 렌더)로 갔다 — 성공 10장은 원문 글자만 지우고 한국어가
없었다(target_text == source_text), 15장 「그릴 줄이 없습니다」, 텐센트 InvalidParameterValue.Data 2장(.gif·`s.gif`),
내려받기 실패 1장(`//img…jpg_1200x1200q30.jpg_.webp` — 스킴 없음). 갤러리는 텐센트 본선이라 한국어가 들어갔다.

여기 있는 것:
- `fix_url` — 스킴 없는 주소에 https, 알리 CDN 리사이즈·webp 꼬리(`.jpg_1200x1200q30.jpg_.webp`) → 원본 `.jpg`
- `prepare_for_tencent` — webp·gif(첫 프레임)·기타 → JPEG, 긴 변 ≤ 4096 · 바이트 ≤ 4MB(텐센트 Data 한도), 디코드 가드(`open_small`)
- `url_exclusion` / `text_exclusion` — 스페이서·작은 아이콘(로고) / 판촉·스토어 UI·수상 배너 글자 → 「등록에서 뺍니다 — 사유」
- `section` — 상품 사진·치수표·소재표(앞) vs 브랜드 스토리(뒤)
- `arrange` — 제외 → 순서 → 상한 20장(네이버 본문 길이 보호, 넘으면 뒤에서 자른다). 「그래도 넣기」(`promo_include`)는 제외를 이긴다.
"""
from __future__ import annotations

import io
import os
import re
from typing import Dict, List, Optional, Tuple

TENCENT_MAX_SIDE = 4096
TENCENT_MAX_BYTES = 4 * 1024 * 1024
DETAIL_LIMIT_DEFAULT = 20
ICON_MAX_SIDE = 300                       # 이보다 작은 그림(가로·세로 둘 다)은 아이콘·로고 — 상품 사진이 아니다

_ALI_TAIL = re.compile(r"(\.(?:jpe?g|png))_[^/?#]*$", re.I)
_TPS_SIZE = re.compile(r"-tps-(\d+)-(\d+)\.", re.I)
_SPACER = re.compile(r"(?:^|/)(?:s|spacer|blank|pixel|transparent)\.gif(?:$|\?)", re.I)

#: 판촉어(`ko_polish` promo_img)에 없는 **스토어 UI·수상·후기 통계** 글자 — 상품 정보가 아니다(오너 Y9 4).
#:   상품 사진에 흔한 워터마크(「天猫」·「淘宝」 한 단어)는 넣지 않는다 — 그것만으로 상품 사진을 빼면 안 된다.
STORE_UI = ("旗舰店", "专营店", "官方店", "邀请入驻", "品牌奖", "设计奖", "新锐品牌", "权威认可", "好评率", "总销量", "用户口碑",
            "回购", "关注店铺", "进店有礼", "TMALL GLOBAL", "Tmall Global", "AWARDS", "Awards", "#1 BRAND", "88VIP")
#: 브랜드 스토리(뒤로) — 상품 자체가 아니라 회사·디자이너·철학 이야기.
STORY = ("设计团队", "致敬", "品牌故事", "品牌理念", "创始", "匠心", "初心", "原创设计", "为原创而生", "Brand Story", "BRAND STORY",
         "since", "Since", "SINCE", "创新无止境", "我们致力于")
#: 치수표·소재표(앞) — 사러 오는 사람이 먼저 봐야 할 것.
SPEC = ("cm", "CM", "mm", "尺寸", "尺码", "规格", "参数", "材质", "面料", "填充", "承重", "重量", "kg", "KG", "MATERIALI",
        "SIZE", "Size", "치수", "사이즈", "소재", "재질", "규격")


def detail_limit() -> int:
    try:
        return max(1, int(os.getenv("DETAIL_IMAGE_LIMIT", str(DETAIL_LIMIT_DEFAULT))))
    except (TypeError, ValueError):
        return DETAIL_LIMIT_DEFAULT


def fix_url(url: str) -> str:
    """주소 정리 — `//` → `https://`, 알리 CDN 꼬리(`.jpg_1200x1200q30.jpg_.webp`·`.png_.webp`) → 원본 확장자에서 끊는다."""
    u = str(url or "").strip()
    if u.startswith("//"):
        u = "https:" + u
    if "alicdn.com" in u:
        u = _ALI_TAIL.sub(r"\1", u)
    return u


def url_exclusion(url: str) -> str:
    """주소만 보고 뺄 장 — 사유(빈 문자열 = 아님). 공급사에 보내지 않는다(돈 0)."""
    u = str(url or "")
    if _SPACER.search(u):
        return "빈 칸 이미지(스페이서 1px)"
    m = _TPS_SIZE.search(u)
    if m and max(int(m.group(1)), int(m.group(2))) < ICON_MAX_SIDE:
        return f"작은 아이콘·로고({m.group(1)}×{m.group(2)})"
    return ""


def size_exclusion(w: int, h: int) -> str:
    if w and h and max(w, h) < ICON_MAX_SIDE:
        return f"작은 아이콘·로고({w}×{h})"
    return ""


def text_exclusion(text: str) -> str:
    """OCR 글(원문·번역문)로 뺄 장 — 판촉어(`promo_img`) + 스토어 UI·수상 배너. 사유 한 줄(빈 문자열 = 아님)."""
    s = str(text or "")
    if not s.strip():
        return ""
    hits: List[str] = []
    try:
        from src.collectors.ko_polish import promo_hits
        hits += promo_hits(s)
    except Exception:
        pass
    for t in STORE_UI:
        if t in s and t not in hits:
            hits.append(t)
    if not hits:
        return ""
    kind = "판촉·스토어 문구" if any(h in s for h in ("券", "折", "减", "SALE", "OFF", "쿠폰", "세일", "할인", "VIP", "促")) \
        else "스토어·수상 배너"
    return f"{kind}({', '.join(hits[:4])})"


def section(text: str) -> str:
    """`spec`(치수·소재) · `story`(브랜드 이야기) · `photo`(그 밖 — 글자 적은 상품 사진 포함)."""
    s = str(text or "")
    if any(t in s for t in STORY):
        return "story"
    if any(t in s for t in SPEC):
        return "spec"
    return "photo"


def entry_text(e: dict) -> str:
    e = e or {}
    t = " ".join(str(e.get(k) or "") for k in ("source_text", "target_text", "ocr_text"))
    try:                                          # Y11: 편집본에서 지운 상자 글자는 빼고(판촉·상표 판정이 편집본 기준)
        from src.services.image_translate_store import erased_out
        return erased_out(e, t)
    except Exception:                             # noqa: BLE001
        return t


def verdict(e: dict, orig_url: str) -> Dict[str, str]:
    """한 장 — `{use: translated|original|excluded|pending|failed, reason, section}`. 「그래도 넣기」면 제외를 무른다."""
    e = e or {}
    st = str(e.get("status") or "")
    why = url_exclusion(fix_url(orig_url)) or str(e.get("exclude") or "") or text_exclusion(entry_text(e))
    sec = str(e.get("section") or section(entry_text(e)))
    if e.get("risk_exclude"):                     # Y10: 리스크 게이트 「빼고 등록」 — 「그래도 넣기」로 무르지 않는다(게이트에서 결정을 바꾼다)
        return {"use": "excluded", "reason": str(e["risk_exclude"]), "section": sec}
    if why and not e.get("promo_include"):
        return {"use": "excluded", "reason": why, "section": sec}
    if st == "done" and e.get("url") and e.get("use", True):
        return {"use": "translated", "reason": "한국어 번역" + (" · 그래도 넣기" if why else ""), "section": sec}
    if st == "skipped":
        return {"use": "original", "reason": str(e.get("reason") or "글자 없는 사진 — 원본 그대로"), "section": sec}
    # 옛 D3 기록: 실패로 적혔지만 사유가 「그릴 줄 없음(글자 없는 사진)」 — 실패가 아니라 원본 그대로 쓰는 장(Y9 ③)
    from src.db.image_translate_queue_pg import is_no_text
    if st in ("failed", "error") and is_no_text(str(e.get("error_message") or e.get("reason") or "")):
        return {"use": "original", "reason": "글자 없는 사진 — 원본 그대로", "section": sec}
    if st in ("queued", "running", ""):
        return {"use": "pending" if st else "original", "reason": "번역 대기" if st else "아직 번역 안 함 — 원본", "section": sec}
    return {"use": "failed", "reason": str(e.get("error_message") or e.get("error_class") or "실패")[:120] + " — 원본으로",
            "section": sec}


def arrange(pairs: List[Tuple[int, str]], by_idx: Dict[int, dict], originals: List[str],
            limit: Optional[int] = None) -> List[Tuple[int, str]]:
    """등록에 나갈 상세 `[(idx, url)]` — 제외 빼고 · 상품 사진/치수·소재 앞, 브랜드 스토리 뒤(각자 원래 순서) · 상한에서 자른다."""
    keep = []
    for i, u in pairs:
        orig = originals[i] if 0 <= i < len(originals) else u
        v = verdict(by_idx.get(i) or {}, orig)
        if v["use"] == "excluded":
            continue
        keep.append((i, fix_url(u) if u == orig else u, v["section"]))
    front = [(i, u) for i, u, s in keep if s != "story"]
    back = [(i, u) for i, u, s in keep if s == "story"]
    return (front + back)[: (limit or detail_limit())]


def table(extra: dict) -> List[dict]:
    """28장 분류표(보고·화면) — `[{no, idx, url, use, reason, section, outbound_pos}]`. `outbound_pos`는 등록 순서(1부터, 빠지면 0)."""
    ex = extra or {}
    originals = [u for u in (ex.get("detail_images") or []) if u]
    by_idx = {int(e.get("idx", -1)): e for e in (ex.get("detail_images_ko") or []) if isinstance(e, dict)}
    order = [i for i, _u in arrange(list(enumerate(originals)), by_idx, originals)]
    rows = []
    for i, u in enumerate(originals):
        v = verdict(by_idx.get(i) or {}, u)
        rows.append({"no": i + 1, "idx": i, "url": fix_url(u), **v,
                     "outbound_pos": (order.index(i) + 1) if i in order else 0})
    return rows


# ── 텐센트 입력 정규화 ─────────────────────────────────────────────────────────────────────────────

def _fmt(raw: bytes) -> str:
    b = raw[:16] if raw else b""
    if b.startswith(b"\xff\xd8"):
        return "JPEG"
    if b.startswith(b"\x89PNG"):
        return "PNG"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "WEBP"
    if b[:3] == b"GIF":
        return "GIF"
    return ""


def prepare_for_tencent(raw: bytes) -> Tuple[Optional[bytes], dict]:
    """원본 바이트 → 텐센트가 받는 JPEG/PNG(긴 변 ≤ 4096 · ≤ 4MB). `(bytes | None, {fmt, w, h, converted, note})`.

    JPEG·PNG가 이미 한도 안이면 그대로(다시 인코딩하지 않는다 — 화질 손실 0). webp·gif(첫 프레임)·그 밖은 JPEG로.
    디코드는 `open_small` 가드를 지난다(JPEG 아닌 1200만 화소 초과는 풀지 않음 — Z10-B).
    """
    info = {"fmt": _fmt(raw), "w": 0, "h": 0, "converted": False, "note": ""}
    if not raw:
        info["note"] = "빈 이미지"
        return None, info
    try:
        from src.collectors.image_norm import image_head, open_small
    except Exception as exc:                                       # noqa: BLE001
        info["note"] = f"정규화 모듈 없음({type(exc).__name__})"
        return None, info
    try:
        fmt, w, h = image_head(raw)[:3]
        info.update(fmt=str(fmt or info["fmt"]), w=int(w or 0), h=int(h or 0))
    except Exception:
        pass
    if info["fmt"] in ("JPEG", "PNG") and len(raw) <= TENCENT_MAX_BYTES and max(info["w"], info["h"]) <= TENCENT_MAX_SIDE \
            and info["w"]:
        return raw, info
    im, fmt, w, h, why = open_small(raw, TENCENT_MAX_SIDE)
    info.update(w=w or info["w"], h=h or info["h"])
    if im is None:
        info["note"] = why or "이미지를 풀지 못했어요"
        return None, info
    try:
        for q in (90, 82, 72, 60):
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=q)
            data = buf.getvalue()
            if len(data) <= TENCENT_MAX_BYTES:
                info.update(converted=True, note=f"{info['fmt'] or fmt or '이미지'} → JPEG {im.size[0]}×{im.size[1]} q{q}")
                return data, info
            im.thumbnail((int(im.size[0] * 0.8), int(im.size[1] * 0.8)))
        info["note"] = "4MB 안으로 줄이지 못했어요"
        return None, info
    finally:
        try:
            im.close()
        except Exception:                                          # noqa: BLE001
            pass
