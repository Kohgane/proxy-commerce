"""src/services/image_cdn_backfill.py — 번역본을 **외부에서 열리는 주소**로 (D2b).

## 왜

D2는 번역본을 DB에 두고 `/seller/collect/image-ko/<item>/<idx>`로 서빙했다.
그 주소는 **로그인 게이트 뒤**다 — 우리 화면엔 보이지만 **마켓 서버는 못 가져간다.**
쿠팡이 그 URL로 이미지를 받으러 오면 404를 본다(우리 세션 쿠키가 없으니까).

그래서 등록에 나가는 주소는 외부에서 열리는 것이어야 한다 → Cloudinary.

## 멱등

이미 `cdn_url`이 있으면 **다시 올리지 않는다.** 백필은 몇 번을 돌려도 같은 결과여야 한다 —
돌릴 때마다 새로 올리면 CDN에 같은 이미지가 쌓이고, 그게 비용이 된다.

바이트가 바뀌면(다시 번역) `put`이 `cdn_url`을 비우므로 그때만 다시 올라간다.

## 실패는 행별로 적는다

한 장이 실패했다고 나머지를 멈추지 않는다. 대신 **왜 실패했는지**를 그 행에 적는다
(`cdn_error`) — 나중에 「왜 이 장만 안 올라갔지」를 추측으로 풀지 않게.
"""
from __future__ import annotations

import json
import logging

logger = logging.getLogger(__name__)

# 한 번에 올릴 장수. 부팅 때 도는 것이라 길면 기동이 늦어진다.
BATCH = 50


#: 0-b — 저장소 kind → 이름표 파이프라인. D3 벤치 렌더본은 실제 인페인터 이름으로.
_KIND_PIPELINE = {"gallery": "TENCENT", "detail": "TENCENT", "d3": "TELEA", "d3g": "GEN_REMOVE"}


def _stamp(prefix: str) -> str:
    from src.media.image_label import run_stamp
    return run_stamp(prefix)


def _label(run_id: str, item_id, idx, pipeline: str) -> dict:
    """백필 이름표 — 벤치 렌더본(d3·d3g)은 `bench` 폴더, 나머지는 `seller` 폴더."""
    from src.media.image_label import make_label
    folder = "bench" if pipeline in ("TELEA", "GEN_REMOVE") else "seller"
    return make_label(run_id, item_id, idx, pipeline, folder=folder)


def cdn_ready() -> bool:
    """Cloudinary가 붙어 있나. 없으면 백필은 **아무것도 하지 않는다**(할 수가 없다)."""
    try:
        from src.media.image_pipeline import _CDN_UPLOAD_ENABLED, _cloudinary_configured
        return bool(_CDN_UPLOAD_ENABLED and _cloudinary_configured())
    except Exception:
        return False


def _upload(raw: bytes, label=None) -> tuple:
    """`(url, error)` — 하나만 채워진다. 가짜 URL을 만들지 않는다.

    F31: 예전엔 `_upload_to_cdn`(반환 `str|None`)을 불러서, 여섯 가지 실패가 전부
    **「업로드가 주소를 돌려주지 않았습니다」** 한 문장이 됐다(오너 실측 ×5).
    이제 **결과 dict**를 받아 사유를 그대로 올린다 — 토글·자격·dry-run·SDK 미설치·
    SDK 예외·응답에 주소 없음(+ **응답 키 목록**)이 각각 다른 문장이다.
    """
    try:
        from src.media.image_pipeline import upload_bytes
    except Exception as exc:
        return "", f"이미지 파이프라인 미가용: {type(exc).__name__}"
    try:
        res = upload_bytes(raw, label=label) if label else upload_bytes(raw)
    except Exception as exc:
        return "", f"{type(exc).__name__}: {str(exc)[:160]}"
    if res.get("ok") and res.get("secure_url"):
        return str(res["secure_url"]), ""
    # 원본 URL 되돌림 같은 「성공 같은 실패」도 여기서 실패로 떨어진다(ok가 아니면 실패다).
    #   사유는 **화면에 닿기 전에** 같은 세척기를 지난다(한 필드 두 규칙 금지).
    from src.utils.redact import scrub_infra
    return "", scrub_infra(str(res.get("error") or "업로드가 주소를 돌려주지 않았습니다"))


def normalize_outward(url: str, base_url: str = "") -> str:
    """마켓이 가져갈 수 있는 **절대 주소**로 편다. 못 펴면 빈 문자열 (F34-2b).

    확장이 `data-src`·`srcset` **원문 그대로**를 보낸다(`content_script.js:239` 등 —
    `im.src`와 달리 브라우저가 절대화해 주지 않는다). 그래서 타오바오·1688·Temu처럼
    스킴 없는 주소(`//img.example.com/a.jpg`)를 쓰는 사이트의 상세 이미지가
    **스킴 없는 채로** 초안에 박힌다.

    `image_reachability.is_internal()`은 스킴이나 호스트가 없으면 **우리 주소로 친다**
    (그게 안전한 기본값이다). 그래서 그런 장은 등록에서 「우리 서버 주소」로 막힌다 —
    **메시지는 정확하지 않지만 판정은 옳다**(마켓은 그 주소를 못 연다).

    ## F34-2d — 상대 경로는 **그 상품의 소스 페이지**를 기준으로 편다

    F34-2b에선 사이트 상대 경로(`/img/a.jpg`)를 「호스트 미상」으로 두었다. 호스트를
    지어내면 안 되니까. 그런데 **지어낼 필요가 없었다** — 그 이미지가 실려 있던 페이지 주소가
    수집 시점에 저장돼 있다(행의 `url`). 브라우저가 그 페이지에서 하는 일과 **같은 계산**이다.

    > ★ **발명과 참조는 다르다.** 호스트를 만들어 내는 건 발명이고,
    > **그 이미지가 있던 페이지**를 기준으로 푸는 건 참조다.

    `base_url`이 없으면 예전대로 「호스트 미상」이다 — 그땐 정말 모른다.
    """
    u = str(url or "").strip()
    if not u:
        return ""
    if u.startswith("//"):
        return "https:" + u
    if u.startswith(("http://", "https://")):
        return u
    base = str(base_url or "").strip()
    if base.startswith(("http://", "https://")):
        from urllib.parse import urljoin
        joined = urljoin(base, u)
        return joined if joined.startswith(("http://", "https://")) else ""
    return ""


def fetch_original(url: str, *, timeout: int = 15, base_url: str = "") -> tuple:
    """원본 이미지 바이트를 가져온다 — `(bytes, error)`. 하나만 채워진다 (F34-2b).

    번역본은 우리가 만들었으니 바이트가 저장소에 있다. **원본은 없다** —
    CDN에 올리려면 공급사에서 한 번 받아 와야 한다.
    """
    direct = normalize_outward(url, base_url)
    if not direct:
        return b"", ("원본 주소를 절대 주소로 펴지 못했습니다"
                     "(상대 경로인데 그 상품의 소스 페이지 주소도 없습니다)")
    try:
        import requests
    except Exception as exc:                                   # pragma: no cover
        return b"", f"확인 불가: {type(exc).__name__}"
    try:
        # 공급사가 핫링크를 막는 경우가 있어 리퍼러를 보내지 않는다(우리 화면도 같은 규약).
        r = requests.get(direct, timeout=timeout,
                         headers={"User-Agent": "gogabridj-imagefetch/1.0",
                                  "Referer": "", "Accept": "image/*,*/*"})
    except Exception as exc:
        return b"", f"{type(exc).__name__}: {str(exc)[:120]}"
    if r.status_code != 200:
        return b"", f"공급사 응답 HTTP {r.status_code}"
    if not r.content:
        return b"", "공급사가 빈 응답을 줬습니다"
    return r.content, ""


def run_originals(items, limit: int = BATCH) -> dict:
    """**번역 안 된 원본**을 CDN에 올린다 — `{ok, uploaded, failed, reason, results}`.

    순회 대상은 저장소가 아니라 **등록에 나가는 집합**이다(`outbound_pages`).
    오너 실측: 진단 「남은 장 0」인데 등록은 상세 1번째에서 막혔다 — 그 장은
    blob에 행이 없어 **아무도 안 보고 있었다.**

    이미 밖에서 열리는 장은 **건드리지 않는다**(멱등 · 비용).
    """
    import json as _json

    from src.services import image_translate_store as store

    if not cdn_ready():
        return {"ok": False, "uploaded": 0, "failed": 0, "skipped": 0, "results": [],
                "reason": "CDN 미연결 — CLOUDINARY_CLOUD_NAME/API_KEY/API_SECRET 확인"}

    uploaded = failed = 0
    results = []
    _run_o = _stamp("origin")
    for it in items or []:
        if uploaded + failed >= limit:
            break
        item_id = str(it.get("id") or "")
        try:
            extra = _json.loads(it.get("extra_json") or "{}") or {}
        except Exception:
            continue
        changed = False
        # F34-2d: 상대 경로를 풀 기준 = **그 상품의 소스 페이지**. 수집 시점에 저장된
        #   실측값이다(행의 `url`) — 호스트를 지어내는 것과 다르다.
        from src.seller_console.upload_dispatcher import draft_url
        base = str(it.get("url") or "").strip() or draft_url(extra)
        for p in store.outbound_missing(extra, item_id=item_id):
            if uploaded + failed >= limit:
                break
            # 번역본이 나가는 장은 번역본 백필(`run`)의 몫이다 — 여기선 원본만 본다.
            if p.get("source") == "translated":
                continue
            raw, err = fetch_original(p.get("original") or "", base_url=base)
            if not raw:
                failed += 1
                results.append({"item_id": item_id, "kind": p["kind"], "idx": p["idx"],
                                "ok": False, "error": err})
                continue
            url, uerr = _upload(raw, _label(_run_o, item_id, p["idx"], "ORIGINAL"))
            if not url:
                failed += 1
                results.append({"item_id": item_id, "kind": p["kind"], "idx": p["idx"],
                                "ok": False, "error": uerr})
                continue
            extra = store.set_origin_cdn(extra, p["kind"], p["idx"], url)
            changed = True
            uploaded += 1
            results.append({"item_id": item_id, "kind": p["kind"], "idx": p["idx"],
                            "ok": True, "error": ""})
        if changed:
            from src.seller_console import collect_history_store as chs
            if not chs.update(item_id, extra_json=_json.dumps(extra, ensure_ascii=False)):
                # 올렸는데 초안에 못 적었다 — F34-2와 같은 반쪽 성공이다. 사실대로 남긴다.
                logger.warning("[CDN 백필] 원본 주소 기록 실패 item=%s", item_id)
                results.append({"item_id": item_id, "kind": "", "idx": -1, "ok": False,
                                "error": "CDN에는 올렸지만 초안에 주소를 적지 못했습니다"})
                failed += 1
    return {"ok": True, "uploaded": uploaded, "failed": failed, "skipped": 0,
            "reason": "", "results": results}


def _point_entry_at_cdn(item_id: str, idx: int, kind: str, url: str) -> bool:
    """초안의 그 장이 **CDN 주소를 가리키게** 한다. 원본 `images`는 건드리지 않는다.

    이걸 해야 `effective_images`가 저절로 외부 주소를 쓴다 — 계산하는 자리를 늘리지 않는다.
    """
    try:
        from src.seller_console import collect_history_store as store
        row = store.get(item_id) or {}
        if not row:
            return False
        extra = json.loads(row.get("extra_json") or "{}") or {}
        ko_key = "images_ko" if kind == "gallery" else "detail_images_ko"
        rows = extra.get(ko_key) or []
        hit = False
        for e in rows:
            if isinstance(e, dict) and int(e.get("idx", -1)) == int(idx):
                e["url"] = url
                e["stored_by"] = "cdn"
                hit = True
        if not hit:
            return False
        extra[ko_key] = rows
        return bool(store.update(item_id, extra_json=json.dumps(extra, ensure_ascii=False)))
    except Exception as exc:
        logger.warning("[CDN 백필] 초안 갱신 실패 item=%s idx=%s: %s", item_id, idx, exc)
        return False


def run(limit: int = BATCH) -> dict:
    """대기 중인 번역본을 올린다. `{ok, uploaded, failed, skipped, reason}`.

    Cloudinary가 없으면 **아무것도 하지 않고 그렇게 말한다** — 「0건 처리」가 아니라 「할 수 없다」다.
    """
    from src.db import image_ko_blobs_pg as blobs

    if not cdn_ready():
        return {"ok": False, "uploaded": 0, "failed": 0, "skipped": 0,
                "reason": "CDN 미연결 — CLOUDINARY_CLOUD_NAME/API_KEY/API_SECRET 확인"}

    pending = blobs.pending_cdn(limit=limit)
    _run_t = _stamp("backfill")
    uploaded = failed = skipped = 0
    # F31-3: 「지금 올리기」가 숫자만 돌려주면 **어느 장이 왜 실패했는지**를 또 모른다.
    #   장별 결과를 그대로 싣는다(화면이 바로 편다).
    results = []
    for p in pending:
        item_id, idx, kind = p["item_id"], int(p["idx"]), p.get("kind", "gallery")
        # 멱등: 그 사이 누가 올렸으면 건너뛴다.
        if blobs.get_cdn(item_id, idx, kind=kind):
            skipped += 1
            results.append({"item_id": item_id, "idx": idx, "kind": kind,
                            "ok": True, "skipped": True, "error": "이미 올라가 있음"})
            continue
        raw, _ct = blobs.get(item_id, idx, kind=kind)
        if not raw:
            blobs.set_cdn(item_id, idx, "", kind=kind, error="바이트가 없습니다")
            failed += 1
            results.append({"item_id": item_id, "idx": idx, "kind": kind,
                            "ok": False, "error": "바이트가 없습니다"})
            continue
        url, err = _upload(raw, _label(_run_t, item_id, idx, _KIND_PIPELINE.get(kind, "TENCENT")))
        if not url:
            blobs.set_cdn(item_id, idx, "", kind=kind, error=err)
            failed += 1
            results.append({"item_id": item_id, "idx": idx, "kind": kind,
                            "ok": False, "error": err})
            logger.warning("[CDN 백필] 실패 item=%s idx=%s: %s", item_id, idx, err)
            continue
        # F34-2: 초안 갱신 결과를 **버리면 안 된다.** 못 고치면 blob엔 CDN 주소가 있어
        #   진단은 「대기 0」인데 등록은 여전히 우리 주소를 보내 막힌다 — 두 화면이
        #   서로를 반박한다. (읽는 쪽도 이제 blob을 정본으로 보지만, 못 고쳤다는 사실은
        #   사실대로 남긴다 — 조용한 반쪽 성공을 만들지 않는다.)
        repointed = _point_entry_at_cdn(item_id, idx, kind, url)
        note = "" if repointed else "CDN에는 올렸지만 초안이 그 주소를 가리키게 하지 못했습니다"
        blobs.set_cdn(item_id, idx, url, kind=kind, error=note)
        if not repointed:
            logger.warning("[CDN 백필] 초안 미갱신 item=%s idx=%s kind=%s", item_id, idx, kind)
        uploaded += 1
        results.append({"item_id": item_id, "idx": idx, "kind": kind, "ok": True,
                        "repointed": repointed, "error": note})

    if uploaded or failed:
        logger.info("[CDN 백필] 올림 %s · 실패 %s · 건너뜀 %s (대기 %s)",
                    uploaded, failed, skipped, len(pending))
    return {"ok": True, "uploaded": uploaded, "failed": failed, "skipped": skipped,
            "pending": len(pending), "reason": "", "results": results}


def run_quietly() -> None:
    """부팅 훅용 — 실패해도 기동을 막지 않는다(백필은 부가 작업이다)."""
    try:
        run()
    except Exception as exc:
        logger.warning("[CDN 백필] 건너뜀: %s", exc)
