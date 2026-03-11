import os
import logging

import requests

log = logging.getLogger(__name__)

_DEFAULT_API_URL = "https://metechs-store.vercel.app/api/products/public"

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    )
}


def _fetch_image_bytes(image_url: str) -> tuple[bytes, str]:
    """Download an image from *image_url* and return (bytes, filename)."""
    resp = requests.get(image_url, headers=_HEADERS, timeout=15)
    resp.raise_for_status()
    # Derive a filename from the URL; default to thumbnail.jpg
    fname = image_url.rstrip("/").split("/")[-1].split("?")[0] or "thumbnail.jpg"
    if "." not in fname:
        fname += ".jpg"
    return resp.content, fname


def post_product(
    name: str,
    affiliate_link: str,
    image_url: str,
    instagram_post_url: str = "",  # kept for signature compatibility, not sent
) -> dict:
    """Post a new product to the Metechs website API.

    Sends exactly three fields as multipart/form-data:
      - ``name``
      - ``link``
      - ``image`` (binary file downloaded from *image_url*)

    Parameters
    ----------
    name:
        Product name.
    affiliate_link:
        Amazon affiliate URL (sent as ``link``).
    image_url:
        URL of the thumbnail image to download and upload as ``image``.
    instagram_post_url:
        Unused — retained for caller compatibility.

    Returns
    -------
    dict
        Parsed JSON response, e.g. ``{"id": 10, "success": True, ...}``.
    """
    api_url = os.getenv("WEBSITE_API_URL", _DEFAULT_API_URL)

    if not affiliate_link:
        raise ValueError("affiliate_link is required (sent as 'link' field).")

    # Download thumbnail to send as a proper file upload
    try:
        img_bytes, img_filename = _fetch_image_bytes(image_url)
    except Exception as exc:
        raise RuntimeError(f"Failed to download thumbnail for upload: {exc}") from exc

    log.info(
        f"[Website] Posting '{name}' to {api_url} "
        f"(image: {img_filename}, {len(img_bytes):,} bytes)"
    )

    files = {
        "image": (img_filename, img_bytes, "image/jpeg"),
    }
    data = {
        "name": name,
        "link": affiliate_link,
    }

    resp = requests.post(api_url, data=data, files=files, timeout=30)

    if not resp.ok:
        raise RuntimeError(
            f"Website API error [{resp.status_code}]: {resp.text}"
        )

    result = resp.json()
    log.info(f"[Website] Product saved — API response: {result}")
    return result

