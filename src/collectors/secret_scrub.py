"""SEC-1: 진단·스냅샷·page_diag에서 로그인 비밀(쿠키·토큰)을 지운다.

확장 `extensions/chrome-collector/kgp-scrub.js`와 **같은 키·같은 규칙**이다(계약 테스트가 대조).
실측: 티몰 진단 파일의 `pass.tmall.com/add?…cookie1=…&cookie2=…&_tb_token_=…`가 레포에 커밋됐다.

- `scrub_text` — 텍스트 전체에서 비밀 키의 값을 `***`로.
- `scrub_url` — 쿼리·해시를 지우고 상품 id 계열 키만 남긴다(page_diag용, 「경로까지만」).
- `scrub_line` — 문장 안의 주소를 `scrub_url`로 줄이고 남은 비밀도 가린다(errors 한 줄).
- `find_secrets` — 가려지지 않은 비밀 키 이름 목록(값은 돌려주지 않는다 — 로그에도 안 남긴다).
"""
from __future__ import annotations

import re
from typing import List

SECRET_KEYS = (
    "cookie", "cookie1", "cookie2", "cookie17", "sgcookie", "_tb_token_", "tb_token", "_l_g_", "sg", "csg",
    "unb", "wk_unb", "_nk_", "nk", "tracknick", "lgc", "lid", "nick", "uc1", "uc3", "uc4", "skt", "cookie14",
    "existshop", "sid", "sessionid", "session", "session_id", "session-id", "session-token", "x5sec",
    "token", "access_token", "refresh_token", "id_token", "auth", "authorization", "password", "passwd",
    "at-main", "sess-at-main", "x-main", "ubid-main", "dnk",
)
# 로그인 계정을 가리키는 값(닉네임·회원번호) — 이 값은 주소 밖(내비바 「닉네임」, JSON)에도 찍힌다.
#   그래서 값 자체를 모아 **문서 전체에서** 가린다.
_IDENT_PAIR_KEYS = frozenset({"lid", "lgc", "tracknick", "dnk", "_nk_", "nick", "unb", "usernick", "nickname", "loginid"})
_IDENT_JSON_RE = re.compile(r'"(nick|displayNick|userNumId|userNick|tracknick|loginId)"\s*:\s*"?([^",}\s]{5,64})')
# SEC-1-c(오너 1.5.158 world.taobao 진단): 목록·홈 마크업은 JSON이 아니라 **내비바 요소 텍스트**로 닉네임을 찍는다
#   (`site-nav-login-info-nick`, `site-nav-user-nick`). 클래스에 nick이 든 요소의 텍스트도 계정 값으로 모은다.
_IDENT_TAG_RE = re.compile(r'<[a-zA-Z][^>]*\bclass="[^"]*nick[^"]*"[^>]*>\s*([^<\s][^<]{3,62}?)\s*<', re.I)
_SET = frozenset(SECRET_KEYS)
_NAME_RE = re.compile(r"(cookie|token|session|passw)", re.I)
_PAIR_RE = re.compile(r"([?&]|&amp;|%26|\\u0026|;\s?)([A-Za-z0-9_\-]{1,40})=([^&;#\"'<>\s\\]*)")
_URL_RE = re.compile(r"https?://[^\s\"'<>)]+")
_KEEP = frozenset({"id", "itemid", "item_id", "goods_id", "offerid", "asin"})


def is_secret_key(key: str) -> bool:
    k = str(key or "").lower()
    return k in _SET or bool(_NAME_RE.search(k))


def _unq(v: str) -> str:
    try:
        from urllib.parse import unquote
        return unquote(v)
    except Exception:
        return v


def identity_values(text) -> List[str]:
    """문서에 찍힌 로그인 계정 값(닉네임·회원번호). 5자 이상만 — 짧으면 일반 단어와 부딪힌다."""
    s = str(text or "")
    vals = set()
    for m in _PAIR_RE.finditer(s):
        if m.group(2).lower() in _IDENT_PAIR_KEYS and m.group(3) and m.group(3) != "***":
            vals.update({m.group(3), _unq(m.group(3))})
    for m in _IDENT_JSON_RE.finditer(s):
        vals.add(m.group(2))
    for m in _IDENT_TAG_RE.finditer(s):
        vals.add(m.group(1).strip())
    return sorted((v for v in vals if len(v) >= 5 and "*" not in v), key=len, reverse=True)


def scrub_text(text):
    if text is None:
        return text
    idents = identity_values(text)

    def _sub(m):
        pre, key, val = m.group(1), m.group(2), m.group(3)
        if not val or val == "***" or not is_secret_key(key):
            return m.group(0)
        return f"{pre}{key}=***"

    out = _PAIR_RE.sub(_sub, str(text))
    for v in idents:
        out = out.replace(v, "***")
    return out


def scrub_url(url) -> str:
    s = str(url or "")
    if "#" in s:
        s = s.split("#", 1)[0]
    if "?" not in s:
        return s
    base, qs = s.split("?", 1)
    keep = [p for p in qs.split("&") if p.split("=", 1)[0].lower() in _KEEP]
    return base + ("?" + "&".join(keep) if keep else "")


def scrub_line(line) -> str:
    s = _URL_RE.sub(lambda m: scrub_url(m.group(0)), str(line if line is not None else ""))
    return scrub_text(s)


def find_secrets(text) -> List[str]:
    """가려지지 않은 비밀 키 이름(중복 제거). 값은 절대 돌려주지 않는다."""
    seen = []
    for m in _PAIR_RE.finditer(str(text or "")):
        key, val = m.group(2), m.group(3)
        if val and val != "***" and is_secret_key(key) and key not in seen:
            seen.append(key)
    if identity_values(text):
        seen.append("(계정 닉네임·회원번호)")
    return seen
