"""F49-T 2부 스파이크 — Scrapling StealthyFetcher가 타오바오·티몰 **상세**를 여는지 1회 실측.

CC 컨테이너는 쇼핑 사이트로 나가는 송신이 막혀 여기서 못 잰다(2026-09-26 실측: 전부 CONNECT 거부).
**Render 셸 또는 Vultr 릴레이 VPS(158.247.231.248)**에서 한 번 돌린다:

    pip install scrapling && scrapling install          # 브라우저(camoufox) 내려받기 — 한 번
    python scripts/spike_taobao_stealthy.py

출력은 **원문 그대로**: HTTP 상태 · 최종 URL(리다이렉트) · 본문 앞 200자 · 로그인 벽 흔적.
판정 규칙(오너 2026-09-26): **여는 경우에만** 서버 경로 후보. 못 열면 이 출력(HTTP 코드·본문 앞 200자)을
볼트에 기록하고 **확장 경로를 유지**한다. 이 스크립트는 우리 앱 코드를 바꾸지 않는다.
"""
import json
import re
import sys

URLS = [
    "https://detail.tmall.com/item.htm?id=617129397971",
    "https://item.taobao.com/item.htm?id=617129397971",
]
WALL = re.compile(r"login|登录|登陆|滑动验证|安全验证|punish|verify", re.I)


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
                       title=(page.css_first("title").text if page.css_first("title") else ""))
        except Exception as exc:
            row.update(error=f"{type(exc).__name__}: {str(exc)[:300]}")
        out.append(row)
    print(json.dumps(out, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
