from urllib.parse import urlsplit, urlunsplit

ALI_HOSTS = {
    "ae01.alicdn.com",
    "ae-pic-a1.aliexpress-media.com",
}

def _host(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower()
    except (TypeError, ValueError):
        return ""


def to_fullsize(url: str) -> str:
    """Convert only CDN thumbnail forms verified to reach a full-size image."""
    if url is None or not isinstance(url, str) or not url.strip():
        return ""

    host = _host(url)
    if not host:
        return url

    if host in ALI_HOSTS:
        import re

        parts = urlsplit(url)
        path = parts.path
        path = re.sub(
            r"\.jpg_(?:\d+x\d+(?:q\d+)?)\.jpg(?:_\.(?:jpg|jpeg|png|webp|avif))?$",
            ".jpg",
            path,
        )
        if path != parts.path:
            return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))
        return url
    if host == "img.kwcdn.com":
        import re

        parts = urlsplit(url)
        query = parts.query
        if re.search(r"(?:^|[/?&])(?:imageView2|imageMogr2)(?:[/&]|$)", "/" + query):
            return urlunsplit((parts.scheme, parts.netloc, parts.path, "", parts.fragment))
        return url

    return url
