import os
import re
from urllib.parse import urlparse, urlencode, parse_qs, urlunparse

AFFILIATE_TAG = os.getenv("AMAZON_AFFILIATE_TAG", "metechs-21")

# Matches:
#   https://www.youtube.com/shorts/<id>
#   https://youtube.com/shorts/<id>
#   https://youtu.be/<id>          (short-link — may be a Short)
#   http:// variants of the above
#   Optional query string (?si=..., ?t=... etc.)
_YOUTUBE_SHORTS_RE = re.compile(
    r"^(https?://)?"
    r"(www\.)?"
    r"("
    r"youtube\.com/shorts/[\w-]+"   # Full /shorts/ path
    r"|youtu\.be/[\w-]+"            # Short-link form
    r")"
    r"([?&].*)?"                    # Optional query string
    r"$",
    re.IGNORECASE,
)


# Matches:
#   https://www.amazon.com/...
#   https://amazon.co.uk/...
#   https://amzn.to/<id>       (short link)
#   https://amzn.eu/<id>
#   http:// variants
_AMAZON_URL_RE = re.compile(
    r"^(https?://)?"
    r"("
    r"(www\.)?amazon\.(com|co\.uk|co\.jp|de|fr|it|es|ca|com\.au|com\.br|in|com\.mx|nl|se|pl|ae|sa)/"
    r"|amzn\.(to|eu|in)/"
    r")"
    r".+",
    re.IGNORECASE,
)


def validate_amazon_url(url: str) -> bool:
    """Return True if *url* looks like a valid Amazon product or affiliate link.

    Accepts:
    - ``https://www.amazon.com/<path>``
    - ``https://amzn.to/<id>``
    - International Amazon domains (co.uk, de, fr, etc.)
    """
    if not url or not isinstance(url, str):
        return False
    return bool(_AMAZON_URL_RE.match(url.strip()))


def ensure_affiliate_tag(url: str, tag: str | None = None) -> str:
    """Return *url* with the Amazon affiliate tag injected.

    The tag is read from the ``AMAZON_AFFILIATE_TAG`` environment variable
    at call time (so .env changes are picked up without a restart).
    Falls back to ``metechs-21`` if the variable is not set.

    - For full Amazon domain URLs: adds/replaces ``tag=`` in the query string.
    - For ``amzn.to`` / ``amzn.eu`` short links: appends ``?tag=<tag>``.
      (Short links redirect server-side; the tag survives the redirect.)
    - If the tag is already present and correct, the URL is returned unchanged.
    """
    if tag is None:
        tag = os.getenv("AMAZON_AFFILIATE_TAG", "metechs-21")
    url = url.strip()
    parsed = urlparse(url)
    host = parsed.netloc.lower().lstrip("www.")

    # For short links, just append the tag parameter
    if host in ("amzn.to", "amzn.eu", "amzn.in"):
        sep = "&" if parsed.query else "?"
        existing = parse_qs(parsed.query)
        if existing.get("tag", [""])[0] == tag:
            return url  # already tagged
        return f"{url}{sep}tag={tag}"

    # For full Amazon URLs, replace or add tag in query string
    params = parse_qs(parsed.query, keep_blank_values=True)
    if params.get("tag", [""])[0] == tag:
        return url  # already tagged
    params["tag"] = [tag]
    new_query = urlencode({k: v[0] for k, v in params.items()})
    tagged = urlunparse((
        parsed.scheme,
        parsed.netloc,
        parsed.path,
        parsed.params,
        new_query,
        "",          # strip fragment
    ))
    return tagged


def validate_youtube_url(url: str) -> bool:
    """Return True if *url* looks like a valid YouTube Shorts link.

    Accepts:
    - ``https://www.youtube.com/shorts/<id>``
    - ``https://youtu.be/<id>``
    - ``http://`` variants
    - URLs with query parameters (e.g. ``?si=...``)

    Parameters
    ----------
    url:
        The raw URL string provided by the Discord user.

    Returns
    -------
    bool
        ``True`` if the URL matches a known YouTube Shorts pattern.
    """
    if not url or not isinstance(url, str):
        return False
    return bool(_YOUTUBE_SHORTS_RE.match(url.strip()))
