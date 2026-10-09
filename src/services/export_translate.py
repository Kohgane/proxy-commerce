"""R2(오너 2026-10-05 역직구) — 한국어 → 일본어 번역 체인(상품명·옵션·상세). Qoo10 재팬 등록 재료.

체인: Papago(NCP, source ko → target ja · 국내 번역과 **같은 하루 글자 상한**) → DeepL(target JA) → Azure(to=ja).
키가 하나도 없거나 전부 실패면 **원문(한국어) 유지 + translated=False + 사유**(가짜 번역 0). 값은 로그에 안 남긴다.
"""
from __future__ import annotations

import logging
from typing import Dict, List

logger = logging.getLogger(__name__)


def _papago(texts: List[str]) -> List[str]:
    import requests
    from src.utils.env import env_str
    from src.seller_console.ai import translator as T
    cid, secret = env_str("NCP_PAPAGO_CLIENT_ID"), env_str("NCP_PAPAGO_CLIENT_SECRET")
    if not (cid and secret):
        raise RuntimeError("키 없음(NCP_PAPAGO_CLIENT_ID/SECRET)")
    need = sum(len(t[:4900]) for t in texts)
    if not T._papago_take(need):
        raise RuntimeError(f"Papago 오늘 사용 상한({T.papago_daily_limit():,}자)")
    out = []
    for t in texts:
        if not t.strip():
            out.append(t)
            continue
        r = requests.post("https://papago.apigw.ntruss.com/nmt/v1/translation",
                          headers={"x-ncp-apigw-api-key-id": cid, "x-ncp-apigw-api-key": secret},
                          data={"source": "ko", "target": "ja", "text": t[:4900]}, timeout=10)
        r.raise_for_status()
        v = (((r.json() or {}).get("message") or {}).get("result") or {}).get("translatedText", "")
        if not v:
            raise RuntimeError("Papago 빈 응답")
        out.append(v)
    return out


def _deepl(texts: List[str]) -> List[str]:
    import requests
    from src.utils.env import env_str
    key = env_str("DEEPL_API_KEY")
    if not key:
        raise RuntimeError("키 없음(DEEPL_API_KEY)")
    url = "https://api-free.deepl.com/v2/translate" if key.endswith(":fx") else "https://api.deepl.com/v2/translate"
    r = requests.post(url, data={"auth_key": key, "text": texts, "source_lang": "KO", "target_lang": "JA"}, timeout=15)
    r.raise_for_status()
    tr = r.json().get("translations") or []
    if len(tr) != len(texts):
        raise RuntimeError(f"DeepL 응답 개수 어긋남({len(tr)}/{len(texts)})")
    return [x.get("text") or "" for x in tr]


def _azure(texts: List[str]) -> List[str]:
    import requests
    from src.utils.env import env_str
    key, region = env_str("AZURE_TRANSLATOR_KEY"), env_str("AZURE_TRANSLATOR_REGION")
    if not key:
        raise RuntimeError("키 없음(AZURE_TRANSLATOR_KEY)")
    h = {"Ocp-Apim-Subscription-Key": key, "Content-Type": "application/json"}
    if region:
        h["Ocp-Apim-Subscription-Region"] = region
    r = requests.post("https://api.cognitive.microsofttranslator.com/translate",
                      params={"api-version": "3.0", "from": "ko", "to": "ja"}, headers=h,
                      json=[{"Text": t} for t in texts], timeout=15)
    r.raise_for_status()
    return [((d.get("translations") or [{}])[0].get("text") or "") for d in r.json()]


CHAIN = (("papago", _papago), ("deepl", _deepl), ("azure", _azure))


def to_ja(texts: List[str]) -> Dict:
    """`{texts, translated, provider, attempts:[{provider, error}]}` — 실패면 원문 그대로 + translated=False."""
    texts = [str(t or "") for t in texts]
    attempts = []
    for name, fn in CHAIN:
        try:
            out = fn(texts)
            if any(o and o != t for o, t in zip(out, texts)):
                return {"texts": out, "translated": True, "provider": name, "attempts": attempts}
            attempts.append({"provider": name, "error": "원문 그대로 돌려줌"})
        except Exception as exc:                                # noqa: BLE001
            attempts.append({"provider": name, "error": f"{type(exc).__name__}: {str(exc)[:160]}"})
    logger.info("[수출 번역 ko→ja] 못 옮김 — %s", " · ".join(f"{a['provider']}: {a['error']}" for a in attempts)[:300])
    return {"texts": texts, "translated": False, "provider": "", "attempts": attempts}


def product_to_ja(product: Dict) -> Dict:
    """상품명·옵션 축/값·상세를 한 번에 → `{title_ja, options_ja, description_ja, translated, provider, attempts}`."""
    title = str(product.get("title_ko") or product.get("title") or "")
    desc = str(product.get("description_ko") or product.get("description") or "")
    opts = [o for o in (product.get("options") or []) if isinstance(o, dict)]
    flat = [title, desc]
    from src.collectors import option_ko as _ok
    _axn = [a["name_ko"] for a in _ok.options_view(product)]          # Y7-I: 축 이름은 한 함수(원문 열쇠)
    for i, o in enumerate(opts):
        flat.append(str((_axn[i] if i < len(_axn) else "") or o.get("name_ko") or o.get("name") or ""))
        vk = list(o.get("values_ko") or [])
        vals = [str(v.get("name") if isinstance(v, dict) else v) for v in (o.get("values") or [])]
        flat += [str(vk[i] if i < len(vk) and vk[i] else vals[i]) for i in range(len(vals))]
    r = to_ja(flat)
    t = r["texts"]
    i = 2
    options_ja = []
    for o in opts:
        n = len(o.get("values") or [])
        options_ja.append({"name": t[i], "values": t[i + 1:i + 1 + n]})
        i += 1 + n
    return {"title_ja": t[0], "description_ja": t[1], "options_ja": options_ja,
            "translated": r["translated"], "provider": r["provider"], "attempts": r["attempts"]}
