"""src/discovery/scout.py — Discovery 봇 (Phase 135).

키워드 기반 트렌드 사이트 자동 발견.

소스:
- Pinterest 트렌드 (RSS/스크랩)
- Reddit 패션/요가 서브레딧 인기글 외부 링크

흐름:
1. DISCOVERY_KEYWORDS 읽기 (env + Sheets `discovery_keywords` 워크시트 합침)
2. 각 키워드별 검색 결과에서 새 도메인 추출
3. 이미 등록된 도메인은 skip
4. 새 도메인 발견 → Sheets `discovery_candidates`에 저장
5. 텔레그램 알림

ADAPTER_DRY_RUN=1 시 실제 HTTP 요청 없이 mock 동작.
"""
from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
_DRY_RUN = os.getenv("ADAPTER_DRY_RUN", "0") == "1"
_USER_AGENT = "KohganePercentiii/1.0 (+https://kohganepercentiii.com)"
_TIMEOUT = int(os.getenv("SCRAPER_TIMEOUT_SEC", "15"))

# 기본 키워드 (env 미설정 시)
_DEFAULT_KEYWORDS = [
    "yoga wear brand",
    "activewear brand",
    "streetwear brand",
    "porter bag",
    "japanese bag brand",
    "outdoor gear brand",
]

# 알려진 대형 플랫폼 (발견 제외)
_KNOWN_PLATFORMS = frozenset({
    "amazon.com", "amazon.co.jp", "rakuten.co.jp", "taobao.com", "tmall.com",
    "ebay.com", "aliexpress.com", "shopify.com", "instagram.com", "facebook.com",
    "twitter.com", "youtube.com", "reddit.com", "pinterest.com",
    "google.com", "wikipedia.org", "naver.com", "coupang.com",
})


def _extract_domain(url: str) -> Optional[str]:
    """URL → 도메인 (www. 제거). 유효하지 않으면 None."""
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return None
        host = parsed.netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        if not host or "." not in host:
            return None
        return host
    except Exception:
        return None


def _get_keywords_from_env() -> list:
    """환경변수에서 키워드 읽기."""
    raw = os.getenv("DISCOVERY_KEYWORDS", "")
    if not raw:
        return []
    return [k.strip() for k in raw.split(",") if k.strip()]


def _get_keywords_from_sheets() -> list:
    """Sheets `discovery_keywords` 워크시트에서 키워드 읽기."""
    if not _SHEET_ID or _DRY_RUN:
        return []
    try:
        from src.utils.sheets import open_sheet
        ws = open_sheet(_SHEET_ID, "discovery_keywords")
        records = ws.get_all_records()
        keywords = []
        for row in records:
            kw = row.get("keyword") or row.get("Keyword") or ""
            if kw.strip():
                keywords.append(kw.strip())
        return keywords
    except Exception as exc:
        logger.debug("discovery_keywords Sheets 읽기 실패: %s", exc)
        return []


def _get_registered_domains() -> set:
    """이미 등록된 도메인 목록 (Sheets `discovery_candidates` + 어댑터 목록)."""
    registered = set()
    # 어댑터 목록
    try:
        from src.collectors.dispatcher import supported_domains
        for d in supported_domains():
            registered.add(d.lower())
    except Exception:
        pass
    # Sheets 후보 목록
    if _SHEET_ID and not _DRY_RUN:
        try:
            from src.utils.sheets import open_sheet
            ws = open_sheet(_SHEET_ID, "discovery_candidates")
            records = ws.get_all_records()
            for row in records:
                d = row.get("domain", "").strip().lower()
                if d:
                    registered.add(d)
        except Exception:
            pass
    return registered


def _search_reddit(keyword: str) -> list:
    """Reddit JSON API에서 키워드 검색 → 외부 링크 추출."""
    if _DRY_RUN:
        return []
    urls = []
    try:
        import requests
        subreddits = ["r/femalefashionadvice", "r/malefashionadvice", "r/yoga", "r/streetwear", "r/Bags"]
        for sub in subreddits[:2]:  # 최대 2개 서브레딧
            api_url = f"https://www.reddit.com/{sub}/search.json?q={keyword}&sort=top&t=month&limit=10"
            resp = requests.get(api_url, headers={"User-Agent": _USER_AGENT}, timeout=_TIMEOUT)
            if resp.status_code != 200:
                continue
            data = resp.json()
            posts = data.get("data", {}).get("children", [])
            for post in posts:
                post_data = post.get("data", {})
                url = post_data.get("url", "")
                if url and not url.startswith("https://www.reddit.com"):
                    urls.append(url)
            time.sleep(1)  # Reddit rate limit 준수
    except Exception as exc:
        logger.debug("Reddit 검색 실패 (%s): %s", keyword, exc)
    return urls


def _save_candidate(domain: str, keyword: str, source: str) -> None:
    """새 후보 도메인을 Sheets에 저장."""
    if not _SHEET_ID or _DRY_RUN:
        return
    try:
        from src.utils.sheets import open_sheet
        ws = open_sheet(_SHEET_ID, "discovery_candidates")
        # 헤더 확인
        try:
            first = ws.row_values(1)
            if not first or first[0] != "domain":
                ws.insert_row(["domain", "keyword", "source", "status", "discovered_at"], index=1)
        except Exception:
            pass
        ws.append_row([
            domain,
            keyword,
            source,
            "pending",
            datetime.now(timezone.utc).isoformat(),
        ])
    except Exception as exc:
        logger.warning("후보 저장 실패 (%s): %s", domain, exc)


def _notify_telegram(msg: str) -> None:
    """텔레그램 알림 (실패 무시)."""
    try:
        from src.utils.telegram import send_message
        send_message(msg)
    except Exception:
        pass


def _update_candidate_status(domain: str, status: str) -> bool:
    """후보 도메인의 상태 업데이트."""
    if not _SHEET_ID:
        return False
    try:
        from src.utils.sheets import open_sheet
        ws = open_sheet(_SHEET_ID, "discovery_candidates")
        records = ws.get_all_records()
        for i, row in enumerate(records):
            if row.get("domain", "").strip().lower() == domain.lower():
                row_idx = i + 2  # 헤더 포함
                ws.update_cell(row_idx, 4, status)
                return True
    except Exception as exc:
        logger.warning("상태 업데이트 실패 (%s): %s", domain, exc)
    return False


class DiscoveryScout:
    """키워드 기반 트렌드 사이트 자동 발견 봇."""

    def run_once(self) -> list:
        """한 번 실행하여 신규 도메인 후보 발견.

        Returns:
            발견된 새 도메인 정보 목록 [{domain, keyword, source}]
        """
        # 키워드 수집 (Sheets 우선, env 폴백)
        sheets_keywords = _get_keywords_from_sheets()
        env_keywords = _get_keywords_from_env()
        # Sheets가 있으면 우선 사용, 없으면 env + 기본값
        if sheets_keywords:
            keywords = sheets_keywords
        else:
            keywords = env_keywords or _DEFAULT_KEYWORDS

        logger.info("Discovery 시작: 키워드 %d개", len(keywords))

        registered = _get_registered_domains()
        discovered = []

        for keyword in keywords:
            logger.info("키워드 탐색: %s", keyword)

            # Reddit 검색
            urls = _search_reddit(keyword)

            for url in urls:
                domain = _extract_domain(url)
                if not domain:
                    continue
                if domain in registered or domain in _KNOWN_PLATFORMS:
                    continue

                logger.info("신규 도메인 발견: %s (키워드: %s)", domain, keyword)
                _save_candidate(domain, keyword, source="reddit")
                registered.add(domain)

                entry = {"domain": domain, "keyword": keyword, "source": "reddit", "url": url}
                discovered.append(entry)

                # 텔레그램 알림
                msg = (
                    f"🔍 신규 사이트 발견: {domain}\n"
                    f"키워드: {keyword}\n"
                    f"소스: reddit\n"
                    f"등록: /seller/discovery"
                )
                _notify_telegram(msg)

        logger.info("Discovery 완료: %d개 신규 도메인", len(discovered))
        return discovered

    def get_candidates(self, status: str = "pending") -> list:
        """후보 도메인 목록 반환.

        Args:
            status: "pending" / "approved" / "rejected" / None (전체)
        """
        if not _SHEET_ID:
            return []
        try:
            from src.utils.sheets import open_sheet
            ws = open_sheet(_SHEET_ID, "discovery_candidates")
            records = ws.get_all_records()
            if status:
                return [r for r in records if r.get("status", "pending") == status]
            return records
        except Exception as exc:
            logger.warning("후보 목록 조회 실패: %s", exc)
            return []

    def approve(self, domain: str) -> bool:
        """도메인 승인 → 어댑터 후보로 승격."""
        success = _update_candidate_status(domain, "approved")
        if success:
            logger.info("도메인 승인: %s", domain)
            _notify_telegram(f"✅ 도메인 승인됨: {domain} — 어댑터 개발 예정")
        return success

    def reject(self, domain: str) -> bool:
        """도메인 거부."""
        success = _update_candidate_status(domain, "rejected")
        if success:
            logger.info("도메인 거부: %s", domain)
        return success

    def get_keywords(self) -> list:
        """현재 활성 키워드 목록 반환."""
        sheets_keywords = _get_keywords_from_sheets()
        env_keywords = _get_keywords_from_env()
        return sheets_keywords or env_keywords or _DEFAULT_KEYWORDS

    def add_keyword(self, keyword: str) -> bool:
        """Sheets에 키워드 추가."""
        if not _SHEET_ID:
            return False
        try:
            from src.utils.sheets import open_sheet
            ws = open_sheet(_SHEET_ID, "discovery_keywords")
            try:
                first = ws.row_values(1)
                if not first or first[0] != "keyword":
                    ws.insert_row(["keyword", "category", "created_at"], index=1)
            except Exception:
                pass
            ws.append_row([keyword, "", datetime.now(timezone.utc).isoformat()])
            return True
        except Exception as exc:
            logger.warning("키워드 추가 실패: %s", exc)
            return False

    def remove_keyword(self, keyword: str) -> bool:
        """Sheets에서 키워드 삭제."""
        if not _SHEET_ID:
            return False
        try:
            from src.utils.sheets import open_sheet
            ws = open_sheet(_SHEET_ID, "discovery_keywords")
            records = ws.get_all_records()
            for i, row in enumerate(records):
                if row.get("keyword", "").strip() == keyword.strip():
                    ws.delete_rows(i + 2)  # 헤더 포함
                    return True
        except Exception as exc:
            logger.warning("키워드 삭제 실패: %s", exc)
        return False
