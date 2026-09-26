"""F49-T 2부 스파이크 — Scrapling StealthyFetcher가 타오바오·티몰 **상세**를 여는지 1회 실측.

CC 컨테이너는 쇼핑 사이트로 나가는 송신이 막혀 여기서 못 잰다(2026-09-26 실측: 전부 CONNECT 거부).
**Render 셸 또는 Vultr 릴레이 VPS(158.247.231.248)**에서 한 번 돌린다:

    pip install scrapling && scrapling install          # 브라우저(camoufox) 내려받기 — 한 번
    python scripts/spike_taobao_stealthy.py

출력은 **원문 그대로**: HTTP 상태 · 최종 URL(리다이렉트) · 본문 앞 200자 · 로그인 벽 흔적.
판정 규칙(오너 2026-09-26): **여는 경우에만** 서버 경로 후보. 못 열면 이 출력(HTTP 코드·본문 앞 200자)을
볼트에 기록하고 **확장 경로를 유지**한다. 이 스크립트는 우리 앱 코드를 바꾸지 않는다.

**실측 결과(오너 Vultr 2026-09-26 10:30Z, Scrapling 0.4.15):** 티몰·타오바오 둘 다 최종 URL
`login.taobao.com/havanaone/login/login.htm?...`(200, 로그인 페이지) → **서버 경로 없음 · 확장 경로 유지.**
Scrapling 채택 범위 = 서버가 여는 사이트(Amazon·Rakuten·1688 등)의 어댑티브 셀렉터만.
"""
import json
import re
import sys

URLS = [
    "https://detail.tmall.com/item.htm?id=617129397971",
    "https://item.taobao.com/item.htm?id=617129397971",
]
WALL = re.compile(r"login|登录|登陆|滑动验证|安全验证|punish|verify", re.I)


def _title(body: str) -> str:
    m = re.search(r"<title[^>]*>(.*?)</title>", body or "", re.S | re.I)
    return re.sub(r"\s+", " ", m.group(1)).strip()[:120] if m else ""


def main():
    try:
        from scrapling.fetchers import StealthyFetcher
    except Exception as exc:                       # pragma: no cover
        print(json.dumps({"ok": False, "error": f"scrapling 없음: {type(exc).__name__}: {exc}"}, ensure_ascii=False))
        return 2
    out = []
    for u in URLS:
        row = {"url": u}
        try:
            page = StealthyFetcher.fetch(u, headless=True, network_idle=True, timeout=60000)
            body = page.html_content or ""
            row.update(status=getattr(page, "status", None), final_url=getattr(page, "url", ""),
                       body_head=body[:200], body_len=len(body),
                       wall_hits=sorted(set(m.group(0) for m in WALL.finditer(body[:20000])))[:6],
                       # Scrapling 0.4.15 Response엔 css_first가 없다(오너 Vultr 실측 AttributeError) —
                       #   API에 기대지 않고 본문에서 <title>만 읽는다.
                       title=_title(body))
        except Exception as exc:
            row.update(error=f"{type(exc).__name__}: {str(exc)[:300]}")
        out.append(row)
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
