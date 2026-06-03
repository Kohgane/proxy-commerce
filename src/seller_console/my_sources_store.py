"""src/seller_console/my_sources_store.py — My Sources / 소싱처 등록소 저장소 (Phase 160+162)."""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
_WS_NAME = "my_sources"
_HEADERS = [
    "domain", "label", "note", "created_at", "last_used_at",
    "openness_status", "adapter_name", "last_collect_at", "last_collect_result",
]
_in_memory: dict[str, dict] = {}

# 대형 플랫폼 (전용 배지 표기 — 차단하지 않음)
_LARGE_PLATFORMS: frozenset[str] = frozenset({
    "coupang.com", "amazon.com", "amazon.co.jp", "amazon.co.uk",
    "amazon.de", "amazon.fr", "ebay.com", "aliexpress.com",
    "taobao.com", "tmall.com", "1688.com", "rakuten.co.jp",
    "smartstore.naver.com", "shopping.naver.com", "store.naver.com",
    "gmarket.co.kr", "auction.co.kr", "11st.co.kr", "wemakeprice.com",
    "tmon.co.kr", "zigzag.kr", "musinsa.com", "29cm.co.kr",
    "lotteon.com", "ssg.com",
})

# SSRF 방지: 사설 IP/로컬호스트
_PRIVATE_HOST_RE = re.compile(
    r"^(localhost|127\.|10\.|172\.(1[6-9]|2\d|3[01])\.|192\.168\.|::1|0\.0\.0\.0)",
    re.IGNORECASE,
)
_PROBE_USER_AGENT = "Mozilla/5.0 (compatible; KohganeBot/1.0; +https://kohganepercentiii.com)"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_domain(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    host = (parsed.netloc or parsed.path or "").strip().lower()
    if host.startswith("www."):
        host = host[4:]
    if ":" in host:
        host = host.split(":", 1)[0]
    return host if "." in host else ""


def _is_safe_probe_url(url: str) -> bool:
    """SSRF 방지: http/https, 사설 IP/로컬호스트 차단."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        host = parsed.hostname or ""
        if _PRIVATE_HOST_RE.match(host):
            return False
        return bool(host)
    except Exception:
        return False


def _detect_adapter_name(domain: str) -> str:
    """도메인에 맞는 어댑터 이름 반환."""
    if domain in _LARGE_PLATFORMS or any(domain.endswith(f".{d}") for d in _LARGE_PLATFORMS):
        return "large_platform"
    try:
        from src.seller_console.collectors.dispatcher import DOMAIN_MAP
        for d, klass in DOMAIN_MAP.items():
            if domain == d or domain.endswith(f".{d}"):
                return klass.__name__
    except Exception:
        pass
    return "generic_og"


def probe_collectability(domain_or_url: str, timeout: float = 5.0) -> dict:
    """도메인/URL 수집 가능성(개방성) 프로빙 (Phase 162).

    HEAD → 상태코드 확인. 필요 시 GET으로 OG/JSON-LD 존재 여부 판정.

    Returns:
        dict with keys:
            status: "open" | "partial" | "restricted"
            adapter_name: str
            detail: str (사람이 읽을 수 있는 요약)
            is_large_platform: bool
    """
    raw = (domain_or_url or "").strip()
    if not raw:
        return {"status": "partial", "adapter_name": "generic_og", "detail": "입력 없음", "is_large_platform": False}

    url = raw if "://" in raw else f"https://{raw}"
    domain = normalize_domain(url)

    is_large = domain in _LARGE_PLATFORMS or any(domain.endswith(f".{d}") for d in _LARGE_PLATFORMS)
    adapter = _detect_adapter_name(domain)

    if not _is_safe_probe_url(url):
        return {
            "status": "restricted",
            "adapter_name": adapter,
            "detail": "안전하지 않은 URL (내부 IP/비표준 스키마)",
            "is_large_platform": is_large,
        }

    try:
        import requests as req
        headers = {"User-Agent": _PROBE_USER_AGENT}

        # 1단계: HEAD 요청
        head_status = None
        try:
            r = req.head(url, headers=headers, timeout=timeout, allow_redirects=True)
            head_status = r.status_code
        except Exception:
            head_status = None

        if head_status in (401, 403):
            return {
                "status": "restricted",
                "adapter_name": adapter,
                "detail": f"접근 차단 (HTTP {head_status})",
                "is_large_platform": is_large,
            }

        if head_status is None:
            # HEAD 실패 → partial (연결 불가 or 타임아웃)
            return {
                "status": "partial",
                "adapter_name": adapter,
                "detail": "연결 불가 또는 타임아웃 (등록은 가능, 수집 결과 미보장)",
                "is_large_platform": is_large,
            }

        # 2단계: GET으로 OG/JSON-LD 탐지
        try:
            rg = req.get(url, headers=headers, timeout=timeout, allow_redirects=True)
            html = rg.text[:200_000]
            has_og = 'property="og:title"' in html or "property='og:title'" in html
            has_og = has_og or 'og:title' in html
            has_jsonld = '"@type"' in html and ('"Product"' in html or '"ItemPage"' in html or '"WebPage"' in html)
            has_og_image = 'og:image' in html

            if has_og or has_jsonld:
                detail = "OG 메타/JSON-LD 확인됨 — 수집 가능"
                return {
                    "status": "open",
                    "adapter_name": adapter,
                    "detail": detail,
                    "is_large_platform": is_large,
                }
            elif has_og_image or rg.status_code == 200:
                return {
                    "status": "partial",
                    "adapter_name": adapter,
                    "detail": "OG/JSON-LD 미확인 — 부분 수집 가능성",
                    "is_large_platform": is_large,
                }
            else:
                return {
                    "status": "restricted",
                    "adapter_name": adapter,
                    "detail": f"HTTP {rg.status_code} — 수집 어려움",
                    "is_large_platform": is_large,
                }
        except Exception as e:
            logger.debug("probe GET 실패 (%s): %s", domain, e)
            return {
                "status": "partial",
                "adapter_name": adapter,
                "detail": "GET 프로빙 실패 — 등록 허용, 수집 결과 미보장",
                "is_large_platform": is_large,
            }

    except Exception as exc:
        logger.debug("probe_collectability 실패 (%s): %s", domain, exc)
        return {
            "status": "partial",
            "adapter_name": adapter,
            "detail": "프로빙 오류 — 등록 허용",
            "is_large_platform": is_large,
        }


def _sheet():
    if not _SHEET_ID:
        return None
    try:
        from src.utils.sheets import open_sheet
        ws = open_sheet(_SHEET_ID, _WS_NAME)
        first = ws.row_values(1)
        if not first or first[0] != "domain":
            ws.insert_row(_HEADERS, index=1)
        return ws
    except Exception as exc:
        logger.debug("My Sources 워크시트 접근 실패: %s", exc)
        return None


def _sort_key(entry: dict) -> str:
    """알파벳순 정렬 키 — 표시 이름(label) 우선, 없으면 domain. 로케일 인지(casefold)."""
    name = (entry.get("label") or entry.get("domain") or "").strip()
    return name.casefold()


def list_sources() -> list[dict]:
    rows: list[dict] = []
    ws = _sheet()
    if ws is not None:
        try:
            rows = [r for r in ws.get_all_records() if (r.get("domain") or "").strip()]
        except Exception as exc:
            logger.debug("My Sources 목록 조회 실패: %s", exc)
            rows = []
    if not rows:
        rows = list(_in_memory.values())
    rows = [dict(r) for r in rows]
    # 알파벳순 정렬 (Phase 162): label 우선, 없으면 domain
    rows.sort(key=_sort_key)
    return rows


def add_source(
    value: str,
    label: str = "",
    note: str = "",
    openness_status: str = "",
    adapter_name: str = "",
    skip_probe: bool = False,
) -> dict:
    """소싱처 등록소에 소스 추가 (Phase 162: openness validation 포함).

    Args:
        value: 도메인 또는 URL
        label: 표시 이름 (비어있으면 domain 사용)
        note: 메모
        openness_status: 미지정 시 자동 프로빙
        adapter_name: 미지정 시 자동 감지
        skip_probe: True 이면 프로빙 건너뜀 (테스트용)
    """
    domain = normalize_domain(value)
    if not domain:
        raise ValueError("도메인 형식이 올바르지 않습니다.")

    now = _utc_now()

    if not openness_status and not skip_probe:
        probe = probe_collectability(value)
        openness_status = probe["status"]
        if not adapter_name:
            adapter_name = probe["adapter_name"]
    else:
        if not adapter_name:
            adapter_name = _detect_adapter_name(domain)

    entry = {
        "domain": domain,
        "label": (label or domain).strip()[:120],
        "note": (note or "").strip()[:300],
        "created_at": now,
        "last_used_at": now,
        "openness_status": openness_status or "partial",
        "adapter_name": adapter_name or "generic_og",
        "last_collect_at": "",
        "last_collect_result": "",
    }
    _in_memory[domain] = entry

    ws = _sheet()
    if ws is not None:
        try:
            records = ws.get_all_records()
            for idx, row in enumerate(records, start=2):
                if normalize_domain(row.get("domain", "")) == domain:
                    ws.update_cell(idx, 2, entry["label"])
                    ws.update_cell(idx, 3, entry["note"])
                    ws.update_cell(idx, 5, entry["last_used_at"])
                    ws.update_cell(idx, 6, entry["openness_status"])
                    ws.update_cell(idx, 7, entry["adapter_name"])
                    return entry
            ws.append_row([entry.get(h, "") for h in _HEADERS])
        except Exception as exc:
            logger.debug("My Sources 저장 실패 (sheet): %s", exc)
    return entry


def update_last_collect(value: str, result_summary: str) -> bool:
    """소싱처의 마지막 수집 결과 업데이트 (Phase 162)."""
    domain = normalize_domain(value)
    if not domain:
        return False
    now = _utc_now()
    entry = _in_memory.get(domain)
    if entry:
        entry["last_collect_at"] = now
        entry["last_collect_result"] = result_summary[:200]

    ws = _sheet()
    if ws is not None:
        try:
            records = ws.get_all_records()
            for idx, row in enumerate(records, start=2):
                if normalize_domain(row.get("domain", "")) == domain:
                    ws.update_cell(idx, 8, now)
                    ws.update_cell(idx, 9, result_summary[:200])
                    return True
        except Exception as exc:
            logger.debug("My Sources 수집 결과 업데이트 실패: %s", exc)
    return domain in _in_memory


def touch_source(value: str) -> bool:
    domain = normalize_domain(value)
    if not domain:
        return False
    entry = _in_memory.get(domain)
    now = _utc_now()
    if entry:
        entry["last_used_at"] = now

    ws = _sheet()
    if ws is not None:
        try:
            records = ws.get_all_records()
            for idx, row in enumerate(records, start=2):
                if normalize_domain(row.get("domain", "")) == domain:
                    ws.update_cell(idx, 5, now)
                    return True
        except Exception as exc:
            logger.debug("My Sources touch 실패 (sheet): %s", exc)
    return domain in _in_memory


def remove_source(value: str) -> bool:
    domain = normalize_domain(value)
    if not domain:
        return False
    removed = _in_memory.pop(domain, None) is not None

    ws = _sheet()
    if ws is not None:
        try:
            records = ws.get_all_records()
            for idx, row in enumerate(records, start=2):
                if normalize_domain(row.get("domain", "")) == domain:
                    ws.delete_rows(idx)
                    return True
        except Exception as exc:
            logger.debug("My Sources 삭제 실패 (sheet): %s", exc)
    return removed


# ---------------------------------------------------------------------------
# 하위 호환 API (Phase 160) — MySourcesStore 클래스 + SourceEntry + _MEM_STORE
# ---------------------------------------------------------------------------

# _MEM_STORE은 _in_memory의 별칭 (Phase 160 테스트 호환)
_MEM_STORE = _in_memory


class SourceEntry:
    """소싱처 엔트리 (Phase 160 호환 객체)."""

    __slots__ = ("domain", "label", "url_example", "added_at",
                 "openness_status", "adapter_name", "last_collect_at", "last_collect_result", "note")

    def __init__(self, domain: str, label: str = "", url_example: str = "",
                 added_at: str = "", openness_status: str = "partial",
                 adapter_name: str = "generic_og", last_collect_at: str = "",
                 last_collect_result: str = "", note: str = ""):
        self.domain = domain
        self.label = label or domain
        self.url_example = url_example
        self.added_at = added_at or _utc_now()
        self.openness_status = openness_status
        self.adapter_name = adapter_name
        self.last_collect_at = last_collect_at
        self.last_collect_result = last_collect_result
        self.note = note

    def to_dict(self) -> dict:
        return {
            "domain": self.domain,
            "label": self.label,
            "url_example": self.url_example,
            "added_at": self.added_at,
            "openness_status": self.openness_status,
            "adapter_name": self.adapter_name,
            "last_collect_at": self.last_collect_at,
            "last_collect_result": self.last_collect_result,
            "note": self.note,
        }


class MySourcesStore:
    """My Sources 저장소 클래스 래퍼 (Phase 160 API 호환)."""

    def add(self, value: str = "", *, domain: str = "", label: str = "",
            url_example: str = "", note: str = "", skip_probe: bool = False) -> "SourceEntry":
        target = value or domain
        entry_dict = add_source(target, label=label, note=note, skip_probe=skip_probe)
        return SourceEntry(
            domain=entry_dict["domain"],
            label=entry_dict["label"],
            url_example=url_example,
            added_at=entry_dict.get("created_at", ""),
            openness_status=entry_dict.get("openness_status", "partial"),
            adapter_name=entry_dict.get("adapter_name", "generic_og"),
            last_collect_at=entry_dict.get("last_collect_at", ""),
            last_collect_result=entry_dict.get("last_collect_result", ""),
            note=entry_dict.get("note", ""),
        )

    def remove(self, value: str = "", *, domain: str = "") -> bool:
        return remove_source(value or domain)

    def list(self) -> list:
        return [
            SourceEntry(
                domain=r["domain"],
                label=r.get("label", r["domain"]),
                added_at=r.get("created_at", ""),
                openness_status=r.get("openness_status", "partial"),
                adapter_name=r.get("adapter_name", "generic_og"),
                last_collect_at=r.get("last_collect_at", ""),
                last_collect_result=r.get("last_collect_result", ""),
                note=r.get("note", ""),
            )
            for r in list_sources()
        ]
