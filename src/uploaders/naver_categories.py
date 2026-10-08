"""Y7-B(오너 2026-10-08) — 네이버 리프 카테고리 가드.

실측(오너 폰 16:26 KST, 플리츠 세트 셰고가): `POST /v2/products` → 400
`invalidInputs[originProduct.leafCategoryId] NotValid 「리프 카테고리ID 항목이 유효하지 않습니다」`.
원인(코드·운영 DB): 상품 `category_code=CLO` → 업로더 `CATEGORY_MAP['CLO']='50000000'`(최상위 「패션의류」).
`CATEGORY_MAP`은 전부 최상위 ID라 어떤 상품이든 리프가 아니다 — 운영 DB 등록 기록에 스마트스토어 성공은 0건.
「고코스모스엔 『자동 배정 — 카테고리 CLO』」는 **스토어 배정 규칙**(`smartstore_routing.json`: 고코스모스 categories에
CLO가 있고 셰고가엔 없음)이지 카테고리 ID 매핑이 아니다 — 두 스토어 모두 같은 `50000000`을 보냈다.

여기서 하는 일:
- 네이버 카테고리 트리(`GET /v1/categories`, 문서: id·name·wholeCategoryName·last)를 **하루 1회** 받아
  `app_state`에 캐시한다.
- 등록이 보낼 `leafCategoryId`를 고르는 순서: 오너가 지정한 `naver_category_id` → 정본 사전 매칭(상품명).
  둘 다 없으면 **보류**(`category_unset`) — 정본 기본 리프(`50004132`)로 옷을 보내면 등록 후 카테고리를 못 바꾼다
  (네이버 `NotChangable.product.category`).
- 고른 ID가 캐시에서 `last=true`가 아니면 **보류**(`category_not_leaf`) — 네이버까지 가서 400을 받지 않게.
  캐시를 못 받았으면(키·네트워크) 판정 못 함 = 막지 않는다(네이버가 답한다).
"""
from __future__ import annotations

import logging
import re
import threading
import time
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

STATE_KEY = "naver_categories"
TTL_SEC = 24 * 3600
REASON_NOT_LEAF = "category_not_leaf"
REASON_UNSET = "category_unset"
_MEM: Dict = {"at": 0.0, "data": None}
_LOCK = threading.Lock()


def _store():
    from src.db import image_translate_queue_pg as st
    return st


def _fetch(account: str = "") -> Optional[list]:
    """네이버에서 전체 카테고리 — 실패하면 None(사유는 로그)."""
    from src.uploaders.naver_uploader import NaverSmartStoreUploader
    accounts = [account] if account else []
    accounts += [a for a in NaverSmartStoreUploader.ACCOUNT_PREFIXES if a not in accounts]
    for acct in accounts:
        try:
            up = NaverSmartStoreUploader(account=acct)
            if not (up.client_id and up.client_secret):
                continue
            res = up._api_request("GET", "/v1/categories")
        except Exception as exc:                            # noqa: BLE001
            logger.warning("[네이버 카테고리] %s 조회 예외: %s", acct, exc)
            continue
        if isinstance(res, list):
            return res
        logger.warning("[네이버 카테고리] %s 조회 실패: %s", acct, str((res or {}).get("error") or res)[:200])
    return None


def _pack(rows: list) -> dict:
    leaves, parents = {}, []
    for r in rows or []:
        if not isinstance(r, dict) or not r.get("id"):
            continue
        cid = str(r["id"])
        if r.get("last"):
            leaves[cid] = str(r.get("wholeCategoryName") or r.get("name") or "")
        else:
            parents.append(cid)
    return {"fetched_at": time.time(), "leaves": leaves, "parents": parents}


# Z8(오너 2026-10-08 23:3x 워커 교착): 전체 카테고리 받기(수천 줄·릴레이 경유)는 **요청 스레드에서 하지 않는다.**
#   캐시가 없거나 하루가 지났으면 백그라운드 스레드 하나가 받고(동시에 하나만), 그동안 요청은 저장본(낡았어도)을
#   쓰거나 저장본도 없으면 「트리 미수신 → 리프 검사 생략」으로 지나간다. 실패하면 다음 요청이 다시 띄운다
#   (실패 직후 `RETRY_SEC` 동안은 다시 안 띄운다). 부팅 직후엔 `start_background_refresh()`가 한 번 띄운다.
BACKGROUND = True          # 테스트는 False로 바꿔 예전처럼 그 자리에서 받는다(계약 재현용)
RETRY_SEC = 60.0
_REFRESH: Dict = {"thread": None, "last_fail": 0.0, "last_ok": 0.0}


def _fetch_and_store(account: str = "") -> Optional[dict]:
    rows = _fetch(account)
    if not rows:
        with _LOCK:
            _REFRESH["last_fail"] = time.time()
        return None
    d = _pack(rows)
    try:
        _store().state_set(STATE_KEY, d)
    except Exception as exc:                            # noqa: BLE001
        logger.warning("[네이버 카테고리] 저장 실패(메모리만): %s", exc)
    logger.info("[네이버 카테고리] 갱신 — 리프 %d · 상위 %d", len(d["leaves"]), len(d["parents"]))
    with _LOCK:
        _MEM["data"] = d
        _REFRESH["last_ok"] = time.time()
    return d


def start_background_refresh(account: str = "", *, force: bool = False) -> bool:
    """백그라운드로 받기 시작 — 이미 도는 중이거나 실패 직후 `RETRY_SEC` 안이면 False."""
    with _LOCK:
        t = _REFRESH["thread"]
        if t is not None and t.is_alive():
            return False
        if not force and time.time() - float(_REFRESH["last_fail"] or 0) < RETRY_SEC:
            return False
        t = threading.Thread(target=_fetch_and_store, args=(account,), daemon=True, name="naver-category-tree")
        _REFRESH["thread"] = t
    t.start()
    return True


def tree(*, refresh: bool = False, account: str = "") -> Optional[dict]:
    """`{fetched_at, leaves: {id: 전체 이름}, parents: [id]}` — 하루 1회 갱신(백그라운드). 저장본이 없으면 None.

    `refresh=True`는 백그라운드·관리자 진단처럼 **요청 밖**에서만 — 그 자리에서 받는다.
    """
    now = time.time()
    with _LOCK:
        d = _MEM["data"]
        if d and not refresh and now - float(d.get("fetched_at") or 0) < TTL_SEC:
            return d
    if not d:
        try:
            d = _store().state_get(STATE_KEY) or None
        except Exception:
            d = None
        if d:
            with _LOCK:
                _MEM["data"] = d
    if d and not refresh and now - float(d.get("fetched_at") or 0) < TTL_SEC:
        return d
    if refresh or not BACKGROUND:
        return _fetch_and_store(account) or d
    start_background_refresh(account)                   # 낡았거나 없음 — 받기는 뒤에서, 지금은 있는 것으로
    return d


def leaf_state(cid: str, *, account: str = "") -> str:
    """`leaf` · `not_leaf`(상위 카테고리) · `unknown_id`(트리에 없음) · `unknown`(트리를 못 받음)."""
    t = tree(account=account)
    if not t or not (t.get("leaves") or t.get("parents")):
        return "unknown"
    cid = str(cid or "").strip()
    if cid in (t.get("leaves") or {}):
        return "leaf"
    if cid in set(t.get("parents") or []):
        return "not_leaf"
    return "unknown_id"


def name_of(cid: str) -> str:
    t = tree() or {}
    return str((t.get("leaves") or {}).get(str(cid or ""), ""))


def search(q: str, limit: int = 30) -> List[Dict[str, str]]:
    """리프만 — 낱말(공백 구분)이 전부 전체 이름에 들어 있는 것. 짧은 이름 먼저."""
    t = tree() or {}
    words = [w for w in str(q or "").split() if w]
    if not words:
        return []
    hits = [(cid, whole) for cid, whole in (t.get("leaves") or {}).items() if all(w in whole for w in words)]
    hits.sort(key=lambda x: (len(x[1]), x[1]))
    return [{"id": cid, "name": whole} for cid, whole in hits[:limit]]


# ── Y7-C(오너 2026-10-08) 자동 추천 — 「그분 3클릭」 복원 ─────────────────────────────────────────────
#   네이버 커머스API엔 상품명 → 카테고리 추천 엔드포인트를 찾지 못했다(문서 목록: 전체·단건·하위 카테고리 조회,
#   카테고리별 속성·표준형 옵션, 카탈로그 조회뿐). 그래서 **쿠팡 카테고리 예측**(`categorization/predict`)이 돌려준
#   리프 이름을 네이버 리프 이름과 맞춰 본다. 확신(점수·2등과의 차이)이 모자라면 후보 3개를 보여 주고 1탭으로 고르게,
#   오너가 고른 결과는 상품명 낱말 → 리프로 기억한다(같은 류 다음 상품은 자동).
SUGGEST_KEY = "naver_cat_suggest"
LEARN_KEY = "naver_cat_learn:"
REASON_CANDIDATES = "category_candidates"
SOURCE_LABEL = {"manual": "지정", "learned": "자동(내가 고른 기록)", "pattern": "자동(상품명 사전)",
                "coupang": "자동(쿠팡 예측)"}


def _env_float(name: str, default: float) -> float:
    import os
    try:
        return float(os.getenv(name, "") or default)
    except ValueError:
        return default


def auto_min() -> float:
    """자동 지정 최소 점수(0~1). 기본 0.75 — 쿠팡 리프 이름과 네이버 리프 이름이 사실상 같을 때만."""
    return _env_float("NAVER_CATEGORY_AUTO_MIN", 0.75)


def sole_min() -> float:
    """후보가 사실상 하나뿐일 때(2등과 0.3 이상 차) 자동 지정 최소 점수 — 기본 0.6."""
    return _env_float("NAVER_CATEGORY_SOLE_MIN", 0.6)


def auto_margin() -> float:
    """1등과 2등 점수 차 최소 — 같은 이름 리프가 여러 갈래(여성/남성/아동)에 있으면 자동으로 정하지 않는다."""
    return _env_float("NAVER_CATEGORY_AUTO_MARGIN", 0.08)


_SEP = re.compile(r"[\s>/·,()\[\]_&+\-]+")
_HANJA_KANA = re.compile(r"[぀-ヿ一-鿿]")
_STOP = {"세트", "여성", "남성", "여자", "남자", "공용", "신상", "신상품", "봄", "여름", "가을", "겨울", "사계절", "정품",
         "해외직구", "무료배송", "빅사이즈", "프리사이즈", "사이즈", "패션", "스타일", "데일리", "인기", "고급", "용품", "상품"}


def _norm(s: str) -> str:
    return _SEP.sub("", str(s or ""))


def _bigrams(s: str) -> set:
    s = _norm(s)
    return {s[i:i + 2] for i in range(len(s) - 1)} or ({s} if s else set())


def _dice(a: str, b: str) -> float:
    A, B = _bigrams(a), _bigrams(b)
    return 2 * len(A & B) / (len(A) + len(B)) if A and B else 0.0


def tokens(title: str) -> List[str]:
    """상품명 낱말 — 한글·영문 2자 이상, 숫자·흔한 말(세트·여성·계절…) 제외, 순서 유지·중복 제거."""
    t = re.sub(r"^\s*\[[^\]]*\]\s*", "", str(title or ""))          # 「[해외직구] 」 같은 머리표
    out: List[str] = []
    for w in _SEP.split(t):
        w = w.strip()
        if len(w) < 2 or w.isdigit() or w in _STOP or re.fullmatch(r"[\d.]+\w{0,3}", w):
            continue
        if w not in out:
            out.append(w)
    return out


def score_leaf(cp_name: str, whole: str, title: str = "") -> float:
    """쿠팡 리프 이름 ↔ 네이버 리프(전체 이름) 점수 0~1.

    0.6 × 리프 이름 겹침(글자 2개씩 Dice) + 0.3 × 쿠팡 이름 낱말이 네이버 경로에 든 비율 + 0.1 × 상품명 낱말이 경로에 든 비율.
    """
    whole = str(whole or "")
    last = whole.split(">")[-1]
    nl, nc = _norm(last), _norm(cp_name)
    s_leaf = _dice(cp_name, last)
    if nl and nl == nc:
        s_leaf = 1.0
    elif len(nl) >= 2 and len(nc) >= 2 and (nl in nc or nc in nl):   # 「여성정장세트」 ⊃ 「정장세트」
        s_leaf = max(s_leaf, 0.85)
    cp_words = [w for w in _SEP.split(str(cp_name or "")) if len(w) >= 2]
    nw = _norm(whole)
    s_tok = (sum(1 for w in cp_words if w in nw) / len(cp_words)) if cp_words else 0.0
    cb = _bigrams(cp_name)                                         # 붙여 쓴 이름(「여성정장세트」)은 글자 2개씩 덮인 비율로
    if cb:
        s_tok = max(s_tok, len(cb & _bigrams(whole)) / len(cb))
    tw = [w for w in _SEP.split(re.sub(r"^\s*\[[^\]]*\]\s*", "", str(title or ""))) if len(w) >= 2 and not w.isdigit()][:8]
    s_title = (sum(1 for w in tw if w in nw) / len(tw)) if tw else 0.0
    # 갈래가 엇갈리면 깎는다 — 쿠팡 이름·상품명이 「여성」인데 네이버 경로가 남성(또는 반대), 아이 말이 없는데 유아동 갈래.
    said = str(cp_name or "") + " " + str(title or "")
    pen = 0.0
    if any(g in said for g in ("여성", "여자", "우먼")) and "남성" in whole and "여성" not in whole:
        pen += 0.3
    if any(g in said for g in ("남성", "남자", "맨즈")) and "여성" in whole and "남성" not in whole:
        pen += 0.3
    if any(k in whole for k in ("유아", "아동", "키즈")) and not any(k in said for k in ("유아", "아동", "키즈", "아기", "베이비", "주니어")):
        pen += 0.2
    return round(max(0.0, 0.6 * s_leaf + 0.3 * s_tok + 0.1 * s_title - pen), 4)


def rank(cp_name: str, title: str = "", *, limit: int = 3) -> List[Dict]:
    """네이버 리프 상위 `limit`개 `[{id, name, score}]` — 트리를 못 받았으면 빈 목록."""
    t = tree() or {}
    if not cp_name or not t.get("leaves"):
        return []
    scored = []
    for cid, whole in t["leaves"].items():
        sc = score_leaf(cp_name, whole, title)
        if sc > 0:
            scored.append((sc, len(whole), cid, whole))
    scored.sort(key=lambda x: (-x[0], x[1], x[3]))
    return [{"id": cid, "name": whole, "score": sc} for sc, _l, cid, whole in scored[:limit]]


def _predict_input(p: dict) -> Tuple[str, str]:
    """쿠팡 예측에 넣을 (상품명, 설명) — 한국어 상품명(등록 몸통의 「[해외직구] 」 머리표는 뗀다)과 설명.

    사전검증(`title_ko`)과 등록(`[해외직구] ` + 같은 이름)이 **같은 이름**이 되게 한다 — 그래야 기억해 둔 답을 같이 쓴다.
    설명은 한자·가나가 섞이면 뺀다(번역 전 원문 잡음)."""
    name = (str(p.get("title_ko") or "").strip()
            or re.sub(r"^\s*\[[^\]]*\]\s*", "", str(p.get("title") or "")).strip())
    raw = str(p.get("description_ko") or p.get("description") or p.get("description_html") or "")
    desc = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", raw)).strip()[:300]
    if _HANJA_KANA.search(desc):
        desc = ""
    return name, desc


def _suggest_cache_get(name: str) -> Optional[dict]:
    try:
        return (_store().state_get(SUGGEST_KEY) or {}).get(name)
    except Exception:
        return None


def _suggest_cache_put(name: str, row: dict) -> None:
    try:
        st = _store()
        cur = st.state_get(SUGGEST_KEY) or {}
        if len(cur) > 500:                                        # 오래된 것부터 버린다(넣은 순서)
            for k in list(cur)[: len(cur) - 400]:
                cur.pop(k, None)
        cur[name] = row
        st.state_set(SUGGEST_KEY, cur)
    except Exception as exc:                                      # noqa: BLE001
        logger.warning("[네이버 카테고리] 추천 기억 저장 실패: %s", exc)


def coupang_guess(p: dict) -> dict:
    """쿠팡 예측 `{id, name, why}` — 키가 없거나 실패하면 id·name 빈칸 + 사유."""
    name, desc = _predict_input(p)
    if not name:
        return {"id": "", "name": "", "why": "상품명이 없어요"}
    try:
        from src.channel_sync.coupang_uploader import make_uploader
        up, _acct = make_uploader()
        if not (up.access_key and up.secret_key):
            return {"id": "", "name": "", "why": "쿠팡 키가 없어 쿠팡 예측을 쓰지 못했어요"}
        r = up.predict(name, desc)
    except Exception as exc:                                      # noqa: BLE001
        return {"id": "", "name": "", "why": f"쿠팡 예측 오류 — {type(exc).__name__}: {str(exc)[:80]}"}
    if not r.get("name"):
        return {"id": r.get("id", ""), "name": "", "why": "쿠팡 예측이 카테고리 이름을 돌려주지 않았어요"
                + (f"({r.get('why')})" if r.get("why") else "")}
    return {"id": r.get("id", ""), "name": r["name"], "why": ""}


def suggest(product: dict) -> dict:
    """쿠팡 예측 다리 — `{id, name, score, coupang, candidates, why}`.

    id가 있으면 자동 지정(점수 ≥ auto_min · 2등과 차 ≥ auto_margin — 또는 사실상 단독 후보: 점수 ≥ sole_min · 차 ≥ 0.3),
    없으면 candidates(최대 3)로 고르게 한다.
    같은 상품명은 저장해 둔 답을 쓴다(사전검증·등록이 같은 답 — 쿠팡에 두 번 묻지 않는다). 트리를 못 받았으면 기억하지 않는다.
    """
    p = product or {}
    name, _desc = _predict_input(p)
    if not name:
        return {"id": "", "name": "", "score": 0.0, "coupang": "", "candidates": [], "why": "상품명이 없어요"}
    hit = _suggest_cache_get(name)
    if hit and (hit.get("id") or hit.get("candidates")):
        return dict(hit)
    if not (tree() or {}).get("leaves"):                          # 맞춰 볼 목록이 없으면 쿠팡에 묻지도 않는다
        return {"id": "", "name": "", "score": 0.0, "coupang": "", "candidates": [],
                "why": "네이버 카테고리 목록을 받지 못해 자동 추천을 못 했어요"}
    g = coupang_guess(p)
    out = {"id": "", "name": "", "score": 0.0, "coupang": g.get("name", ""), "coupang_id": g.get("id", ""),
           "candidates": [], "why": g.get("why", "")}
    if not g.get("name"):
        return out
    top = [c for c in rank(g["name"], name, limit=3) if c["score"] >= 0.25]   # 거의 안 닮은 후보는 보이지 않는다
    if not top:
        out["why"] = f"쿠팡 예측 「{g['name']}」와 닮은 네이버 카테고리가 없어요"
        return out
    second = top[1]["score"] if len(top) > 1 else 0.0
    gap = top[0]["score"] - second
    if (top[0]["score"] >= auto_min() and gap >= auto_margin()) or (top[0]["score"] >= sole_min() and gap >= 0.3):
        out.update(id=top[0]["id"], name=top[0]["name"], score=top[0]["score"])
    else:
        out["candidates"] = top
        out["why"] = (f"쿠팡 예측 「{g['name']}」와 딱 맞는 네이버 카테고리를 하나로 정하지 못했어요"
                      f"(1등 {top[0]['score']:.2f}" + (f" · 2등 {second:.2f}" if len(top) > 1 else "") + ")")
    _suggest_cache_put(name, out)
    logger.info("[네이버 카테고리] 쿠팡 예측 「%s」 → %s", g["name"],
                out["name"] or "후보 " + " / ".join(c["name"] for c in top))
    return out


# ── 학습: 오너가 고른 리프를 상품명 낱말에 붙여 둔다 ────────────────────────────────────────────────

def scope_for(product: Optional[dict] = None) -> str:
    """학습 범위 — 오너 서버 공유 마켓 사용자(관리자·가족)는 한 벌(`shared`), 그 밖은 셀러별(`s:<id>`)."""
    p = product or {}
    if p.get("cat_scope"):
        return str(p["cat_scope"])
    sid = ""
    try:
        from flask import has_request_context, session
        if has_request_context():
            from src.seller_console.market_pick import session_is_shared
            if session_is_shared():
                return "shared"
            sid = str(session.get("user_id") or session.get("user_email") or "")
    except Exception:
        pass
    return "s:" + (sid or str(p.get("seller_id") or "") or "default")


def learn(scope: str, title: str, cid: str) -> None:
    """상품명 낱말마다 이 리프 한 표. 같은 상품명 자체도 기억한다(다시 들어오면 그대로)."""
    cid = str(cid or "").strip()
    if not cid:
        return
    key = LEARN_KEY + str(scope or "s:default")
    try:
        st = _store()
        cur = st.state_get(key) or {}
        tok = cur.setdefault("tok", {})
        for w in tokens(title):
            row = tok.setdefault(w, {})
            row[cid] = int(row.get(cid) or 0) + 1
        exact = cur.setdefault("exact", {})
        exact[_norm(re.sub(r"^\s*\[[^\]]*\]\s*", "", str(title or "")))] = cid
        st.state_set(key, cur)
    except Exception as exc:                                      # noqa: BLE001
        logger.warning("[네이버 카테고리] 학습 저장 실패: %s", exc)


def learned(scope: str, title: str) -> str:
    """기억에서 리프 — 같은 상품명이면 그대로, 아니면 **낱말 2개 이상이 같은 리프**를 가리키고 다른 리프와 비기지 않을 때만."""
    try:
        cur = _store().state_get(LEARN_KEY + str(scope or "s:default")) or {}
    except Exception:
        return ""
    ex = (cur.get("exact") or {}).get(_norm(re.sub(r"^\s*\[[^\]]*\]\s*", "", str(title or ""))))
    if ex:
        return str(ex)
    votes: Dict[str, float] = {}
    for w in tokens(title):
        row = (cur.get("tok") or {}).get(w) or {}
        if not row:
            continue
        tot = sum(int(v) for v in row.values()) or 1
        for cid, n in row.items():                                # 여러 리프를 가리키는 낱말은 나눠서 센다
            votes[cid] = votes.get(cid, 0.0) + int(n) / tot
    if not votes:
        return ""
    best = sorted(votes.items(), key=lambda x: -x[1])
    if best[0][1] >= 2 and (len(best) == 1 or best[0][1] - best[1][1] >= 1):
        return best[0][0]
    return ""


def pick(product: dict) -> Tuple[str, str]:
    """`(leafCategoryId, 출처)` — 출처: manual(오너 지정) · learned(오너가 고른 기록) · pattern(정본 사전 매칭) ·
    coupang(쿠팡 예측 다리) · ""(못 정함). 등록·사전검증·카드가 **이 한 함수**로 정한다."""
    from src.uploaders.naver_uploader import NaverSmartStoreUploader as SS
    p = product or {}
    manual = str(p.get("naver_category_id") or "").strip()
    if manual:
        return manual, "manual"
    title = p.get("title_ko") or p.get("title") or ""
    hit = learned(scope_for(p), title)
    if hit:
        return hit, "learned"
    hit = SS.match_category(p.get("title") or p.get("title_ko") or "")
    if hit:
        return hit, "pattern"
    s = suggest(p)
    return (s["id"], "coupang") if s.get("id") else ("", "")


def describe(product: dict) -> dict:
    """카드·사전검증이 보일 한 줄 재료 `{id, name, source, label, candidates, why, change_url}`."""
    p = product or {}
    cid, src = pick(p)
    out = {"id": cid, "name": name_of(cid) if cid else "", "source": src, "label": SOURCE_LABEL.get(src, ""),
           "candidates": [], "why": "", "coupang": "", "change_url": picker_url(str(p.get("item_id") or ""))}
    if not cid:
        s = suggest(p)
        out.update(candidates=[{"id": c["id"], "name": c["name"]} for c in s.get("candidates") or []],
                   why=s.get("why", ""), coupang=s.get("coupang", ""))
    elif src == "coupang":
        s = suggest(p)
        out["coupang"] = s.get("coupang", "")
        out["name"] = out["name"] or s.get("name", "")
    return out


def hold(product: dict, *, account: str = "") -> Optional[Dict[str, str]]:
    """보류 `{code, line}` 또는 None. 판정 못 함(트리 없음)은 막지 않는다."""
    cid, src = pick(product)
    if not cid:
        s = suggest(product)
        if s.get("candidates"):
            return {"code": REASON_CANDIDATES,
                    "line": f"네이버 카테고리를 하나로 정하지 못했어요 — 아래 후보 {len(s['candidates'])}개 중 하나를 눌러 주세요"
                            + (f"(쿠팡 예측 「{s['coupang']}」)" if s.get("coupang") else ""),
                    "candidates": [{"id": c["id"], "name": c["name"]} for c in s["candidates"]]}
        return {"code": REASON_UNSET,
                "line": "네이버 카테고리를 정하지 못했어요 — 카테고리를 다시 지정하세요(카테고리 지정 →)"
                        + (f" · {s['why']}" if s.get("why") else "")}
    st = leaf_state(cid, account=account)
    if st == "not_leaf":
        return {"code": REASON_NOT_LEAF,
                "line": f"네이버 카테고리 {cid}는 하위 분류가 있는 상위 카테고리예요(리프 아님) — 카테고리를 다시 지정하세요(카테고리 지정 →)"}
    if st == "unknown_id":
        return {"code": REASON_NOT_LEAF,
                "line": f"네이버 카테고리 {cid}가 네이버 목록에 없어요 — 카테고리를 다시 지정하세요(카테고리 지정 →)"}
    return None


def reset() -> None:
    """테스트·진단용 — 메모리 캐시만 비운다(저장본은 그대로)."""
    with _LOCK:
        _MEM.update(at=0.0, data=None)
        _REFRESH.update(thread=None, last_fail=0.0, last_ok=0.0)


def boot_refresh() -> bool:
    """워커 부팅 직후 1회 — 저장본이 없거나 하루 지났으면 백그라운드로 받기 시작(요청은 기다리지 않는다)."""
    import os
    if not BACKGROUND or os.getenv("PYTEST_CURRENT_TEST"):
        return False
    try:
        d = _MEM["data"] or _store().state_get(STATE_KEY) or None
    except Exception:
        d = None
    if d and time.time() - float(d.get("fetched_at") or 0) < TTL_SEC:
        with _LOCK:
            _MEM["data"] = _MEM["data"] or d
        return False
    return start_background_refresh()


def picker_url(item_id: str) -> str:
    return f"/seller/collect/{item_id}/naver-category" if item_id else ""
