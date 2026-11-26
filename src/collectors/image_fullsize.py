from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


AMAZON_HOSTS = {
    "m.media-amazon.com",
    "images-na.ssl-images-amazon.com",
}

ALI_HOSTS = {
    "ae01.alicdn.com",
    "ae-pic-a1.aliexpress-media.com",
}

ALICDN_HOSTS = {
    "img.alicdn.com",
    "gw.alicdn.com",
    "cbu01.alicdn.com",
}


def _host(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower()
    except (TypeError, ValueError):
        return ""


def to_fullsize(url: str) -> str:
    """Remove known CDN thumbnail size directives without guessing at unknown forms."""
    if url is None or not isinstance(url, str) or not url.strip():
        return ""

    host = _host(url)
    if not host:
        return url

    if host in AMAZON_HOSTS:
        import re

        return re.sub(
            r"\._(?:AC|SS|SX|SY|US|UL|SL)[A-Za-z0-9]*(?:_[A-Za-z0-9]+)*_\.",
            ".",
            url,
        )

    if host in ALI_HOSTS:
        import re

        parts = urlsplit(url)
        path = parts.path
        path = re.sub(r"\.jpg_Q\d+.*$", ".jpg", path)
        path = re.sub(
            r"_(?:\d+x\d+(?:q\d+)?|q\d+)\.(?:jpg|jpeg|png|webp).*?$",
            "",
            path,
        )
        path = re.sub(r"_\.(?:jpg|jpeg|png|webp|avif).*?$", "", path)
        if path != parts.path:
            return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))
        return url

    if host == "cbu01.alicdn.com":
        import re

        parts = urlsplit(url)
        path = parts.path
        path = re.sub(r"\.(?:\d+x\d+|search|summ)\.(?:jpg|jpeg|png|webp)$", lambda m: "." + m.group(0).rsplit(".", 1)[1], path)
        path = re.sub(r"\.jpg_\.(?:jpg|jpeg|png|webp|avif)$", ".jpg", path)
        if path != parts.path:
            return urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))
        return url

    if host.endswith(".alicdn.com") or host == "alicdn.com":
        import re

        parts = urlsplit(url)
        path = parts.path
        path = re.sub(r"_q\d+\.(?:jpg|jpeg|png|webp).*?$", "", path)
        path = re.sub(
            r"_(?:\d+x\d+(?:q\d+)?|q\d+)\.(?:jpg|jpeg|png|webp).*?$",
            "",
            path,
        )
        path = re.sub(r"_\.(?:jpg|jpeg|png|webp|avif).*?$", "", path)
        if path != parts.path:
            result = urlunsplit((parts.scheme, parts.netloc, path, parts.query, parts.fragment))
        else:
            result = url

        if result.startswith("//"):
            return "https:" + result
        return result

    if host == "img.kwcdn.com":
        import re

        parts = urlsplit(url)
        query = parts.query
        if re.search(r"(?:^|[/?&])(?:imageView2|imageMogr2)(?:[/&]|$)", "/" + query):
            return urlunsplit((parts.scheme, parts.netloc, parts.path, "", parts.fragment))
        return url

    if host == "thumbnail.image.rakuten.co.jp":
        import re

        parts = urlsplit(url)
        params = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True) if key != "_ex"]
        path = re.sub(r"/@0_mall/", "/", parts.path)
        query = urlencode(params, doseq=True)
        if path != parts.path or query != parts.query:
            return urlunsplit((parts.scheme, parts.netloc, path, query, parts.fragment))
        return url

    if host == "cdn.shopify.com":
        import re

        parts = urlsplit(url)
        path = re.sub(
            r"_(?:\d+(?:x\d*)?|small)\.(?:jpg|jpeg|png|webp)$",
            lambda m: "." + m.group(0).rsplit(".", 1)[1],
            parts.path,
        )
        params = [
            (key, value)
            for key, value in parse_qsl(parts.query, keep_blank_values=True)
            if key.lower() not in {"width", "height"}
        ]
        query = urlencode(params, doseq=True)
        if path != parts.path or query != parts.query:
            return urlunsplit((parts.scheme, parts.netloc, path, query, parts.fragment))
        return url

    return url
