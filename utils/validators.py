import re

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
