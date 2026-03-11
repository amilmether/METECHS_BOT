import os
import time
import logging

import requests

log = logging.getLogger(__name__)

GRAPH_API_BASE = "https://graph.facebook.com/v19.0"
UPLOAD_API_BASE = "https://rupload.facebook.com/ig-api-upload"


# ──────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────────────────────

def _credentials() -> tuple[str, str]:
    """Return (access_token, ig_user_id) from environment, raising if missing."""
    access_token = os.getenv("INSTAGRAM_ACCESS_TOKEN")
    ig_user_id = os.getenv("INSTAGRAM_BUSINESS_ID")
    if not access_token or not ig_user_id:
        raise RuntimeError(
            "INSTAGRAM_ACCESS_TOKEN and INSTAGRAM_BUSINESS_ID must be set in .env"
        )
    return access_token, ig_user_id


def _raise_for_api_error(resp: requests.Response, context: str) -> None:
    """Parse a Graph API JSON response and raise a descriptive RuntimeError."""
    try:
        data = resp.json()
    except ValueError:
        data = {}

    if resp.ok and "id" in data:
        return  # Success

    error = data.get("error", {})
    code = error.get("code", resp.status_code)
    message = error.get("message") or resp.text or "Unknown API error"

    if code == 9007:
        raise RuntimeError(
            "Instagram rate limit reached (100 published posts / 24 h). "
            "Try again later."
        )
    raise RuntimeError(f"{context} [{code}]: {message}")


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def create_reel_container(caption: str = "") -> tuple[str, str]:
    """Create a Reels media container using the resumable upload flow.

    Parameters
    ----------
    caption:
        Optional caption / description for the Reel.

    Returns
    -------
    tuple[str, str]
        ``(container_id, upload_uri)`` — the container ID and the endpoint
        to which the video binary should be uploaded.

    Raises
    ------
    RuntimeError
        On API error, missing credentials, or rate limit.
    """
    access_token, ig_user_id = _credentials()

    params = {
        "access_token": access_token,
        "media_type": "REELS",
        "upload_type": "resumable",
        "caption": caption,
    }

    resp = requests.post(f"{GRAPH_API_BASE}/{ig_user_id}/media", params=params)
    _raise_for_api_error(resp, "Container creation failed")

    data = resp.json()
    container_id: str = data["id"]
    # The Graph API returns an `uri` field for resumable uploads
    upload_uri: str = data.get("uri") or f"{UPLOAD_API_BASE}/{container_id}"

    log.info(f"[Instagram] Container created: {container_id}")
    return container_id, upload_uri


def upload_video_resumable(upload_uri: str, file_path: str) -> None:
    """Upload the local video file to Instagram via the resumable upload endpoint.

    Parameters
    ----------
    upload_uri:
        The upload endpoint returned by :func:`create_reel_container`.
    file_path:
        Absolute path to the local ``.mp4`` file to upload.

    Raises
    ------
    RuntimeError
        If the HTTP upload request fails.
    """
    access_token, _ = _credentials()
    file_size = os.path.getsize(file_path)

    headers = {
        "Authorization": f"OAuth {access_token}",
        "offset": "0",
        "file_size": str(file_size),
        "Content-Type": "application/octet-stream",
    }

    log.info(
        f"[Instagram] Uploading {os.path.basename(file_path)} "
        f"({file_size:,} bytes) → {upload_uri}"
    )

    with open(file_path, "rb") as fh:
        resp = requests.post(upload_uri, headers=headers, data=fh)

    if not resp.ok:
        raise RuntimeError(
            f"Video upload failed [{resp.status_code}]: {resp.text}"
        )

    log.info("[Instagram] Video upload complete.")


def poll_container_status(
    container_id: str,
    max_retries: int = 10,
    interval: int = 30,
) -> None:
    """Poll the container status until it reaches ``FINISHED``.

    Parameters
    ----------
    container_id:
        The media container ID returned by :func:`create_reel_container`.
    max_retries:
        Maximum number of polling attempts before raising :exc:`TimeoutError`.
        Default: 10 (5 minutes at 30-second intervals).
    interval:
        Seconds to wait between polls. Default: 30.

    Raises
    ------
    TimeoutError
        If ``FINISHED`` is not reached within ``max_retries`` attempts.
    RuntimeError
        If the container reaches ``ERROR`` or ``EXPIRED`` status, or if the
        API call itself fails.
    """
    access_token, _ = _credentials()

    for attempt in range(1, max_retries + 1):
        resp = requests.get(
            f"{GRAPH_API_BASE}/{container_id}",
            params={"fields": "status_code", "access_token": access_token},
        )

        if not resp.ok:
            error = resp.json().get("error", {})
            raise RuntimeError(
                f"Status poll failed [{resp.status_code}]: "
                f"{error.get('message', resp.text)}"
            )

        status: str = resp.json().get("status_code", "UNKNOWN")
        log.info(
            f"[Instagram] Container {container_id} → {status} "
            f"(attempt {attempt}/{max_retries})"
        )

        if status == "FINISHED":
            return
        if status == "ERROR":
            raise RuntimeError(
                f"Container {container_id} failed processing (status=ERROR). "
                "Check video format: MP4, H.264, AAC, 9:16, ≤90 s, ≤1 GB."
            )
        if status == "EXPIRED":
            raise RuntimeError(
                f"Container {container_id} expired before publishing (>24 h)."
            )

        if attempt < max_retries:
            time.sleep(interval)

    raise TimeoutError(
        f"Container {container_id} did not reach FINISHED after "
        f"{max_retries} attempts ({max_retries * interval // 60} min)."
    )


def publish_container(container_id: str) -> str:
    """Publish a finished media container as an Instagram Reel.

    Parameters
    ----------
    container_id:
        The media container ID whose status is ``FINISHED``.

    Returns
    -------
    str
        The published Instagram media ID.

    Raises
    ------
    RuntimeError
        On API error or rate limit.
    """
    access_token, ig_user_id = _credentials()

    params = {
        "access_token": access_token,
        "creation_id": container_id,
    }

    resp = requests.post(
        f"{GRAPH_API_BASE}/{ig_user_id}/media_publish", params=params
    )
    _raise_for_api_error(resp, "Publish failed")

    media_id: str = resp.json()["id"]
    log.info(f"[Instagram] Reel published — media ID: {media_id}")
    return media_id


def get_media_permalink(media_id: str) -> str:
    """Fetch the public permalink URL of a published Instagram media object.

    Parameters
    ----------
    media_id:
        The published Instagram media ID returned by :func:`publish_container`.

    Returns
    -------
    str
        The public ``https://www.instagram.com/reel/<code>/`` URL, or an
        empty string if the field is not available.

    Raises
    ------
    RuntimeError
        If the Graph API call fails.
    """
    access_token, _ = _credentials()

    resp = requests.get(
        f"{GRAPH_API_BASE}/{media_id}",
        params={"fields": "permalink", "access_token": access_token},
    )

    if not resp.ok:
        error = resp.json().get("error", {})
        raise RuntimeError(
            f"Could not fetch permalink [{resp.status_code}]: "
            f"{error.get('message', resp.text)}"
        )

    permalink: str = resp.json().get("permalink", "")
    log.info(f"[Instagram] Permalink: {permalink}")
    return permalink
