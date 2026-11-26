"""Convert known marketplace thumbnail URLs to their full-size form."""

from __future__ import annotations

from urllib.parse import urlsplit, urlunsplit
import re


_AMAZON_TOKEN_RE = re.compile(
    r"\._(?:AC|SS|SX|CR)[A-Za-z0-9,_]*_\.",
    re.IGNORECASE,
)
_MARKET_SIZE_SUFFIX_RE = re.compile(
    r"_\d+x\d+(?:q\d+)?(?=\.(?:jpg|jpeg|png|webp)$)",
    re.IGNORECASE,
)
_ALICDN_SIZE_RE = re.compile(
    r"_\d+x\d+(?:q\d+)?(?:\.(?:jpg|jpeg|png|webp))?(?:_.webp)?$",
    re.IGNORECASE,
)
_WEBP_TAIL_RE = re.compile(r"_\.webp$|_webp$|_\.(?:jpg|jpeg|png)\.webp$", re.IGNORECASE)
_SHOPIFY_SIZE_RE = re.compile(
    r"_\d+(?:x\d*)?(?:@\d+x)?(?=\.(?:jpg|jpeg|png|webp)$)",
    re.IGNORECASE,
)
_ALIBABA_AT_RE = re.compile(
    r"@\d+w_\d+h(?:_[A-Za-z0-9]+)*(?:\.(?:jpg|jpeg|png|webp))?$",
    re.IGNORECASE,
)


def _remove_query_sizes(query: str, keys: set[str]) -> str:
    kept = []
    for part in query.split("&"):
        if not part:
            continue
        raw_key = part.split("=", 1)[0].replace("+", " ")
        if raw_key.lower() not in keys:
            kept.append(part)
    return "&".join(kept)


def _remove_alicdn_suffix(path: str) -> str:
    match = re.search(
        r"_(\d+x\d+(?:q\d+)?)(\.(?:jpg|jpeg|png|webp))?(?:_.webp)?$",
        path,
        re.IGNORECASE,
    )
    if not match:
        return path

    prefix = path[: match.start()]
    suffix_extension = match.group(2)
    if suffix_extension:
        # Preserve an extension when the thumbnail is the whole filename.
        if "." not in prefix.rsplit("/", 1)[-1]:
            return prefix + suffix_extension
    return prefix


def to_fullsize(url: str) -> str:
    """Best-effort, deterministic thumbnail-to-full-size URL conversion."""
    if not isinstance(url, str) or not url:
        return url

    try:
        parts = urlsplit(url)
    except (TypeError, ValueError):
        return url

    host = (parts.hostname or "").lower()
    if not host:
        return url

    path = parts.path

    if host == "m.media-amazon.com" or host.endswith(".media-amazon.com") or host.endswith(".amazon.com"):
        path = _AMAZON_TOKEN_RE.sub(".", path)
        return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))

    if host.endswith(".alicdn.com") or host in {
        "alicdn.com",
        "taobao.com",
        "tmall.com",
        "1688.com",
        "aliexpress.com",
        "ae01.alicdn.com",
    }:
        path = _ALIBABA_AT_RE.sub("", path)
        path = _remove_alicdn_suffix(path)
        path = _WEBP_TAIL_RE.sub("", path)
        return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))

    if host.endswith(".kwcdn.com") or "temu" in host:
        path = _MARKET_SIZE_SUFFIX_RE.sub("", path)
        path = _ALICDN_SIZE_RE.sub("", path)
        path = re.sub(r"_\d+x\d+(?:q\d+)?$", "", path)
        return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))

    if host.endswith(".rakuten.co.jp") or host.endswith(".rakuten.com"):
        query = _remove_query_sizes(parts.query, {"_ex"})
        return urlunsplit((parts.scheme, parts.netloc, path, query, parts.fragment))

    if host.endswith(".myshopify.com") or host.endswith("shopify.com") or host == "cdn.shopify.com":
        path = _SHOPIFY_SIZE_RE.sub("", path)
        query = _remove_query_sizes(parts.query, {"width", "height", "w", "h"})
        return urlunsplit((parts.scheme, parts.netloc, path, query, parts.fragment))

    if host.endswith(".1688.com") or host == "1688.com":
        path = _ALIBABA_AT_RE.sub("", path)
        path = _remove_alicdn_suffix(path)
        return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))

    return url
