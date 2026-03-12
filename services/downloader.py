import base64
import os
import logging
import tempfile

import yt_dlp

from utils.cleanup import ensure_temp_dir

log = logging.getLogger(__name__)

TEMP_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "temp")

# Module-level cache so we only decode / write the temp file once per process.
_COOKIES_PATH: str | None = ""


def _get_cookies_path() -> str | None:
    """Return a path to a Netscape cookies.txt for yt-dlp, or None.

    Resolution order:
    1. ``YOUTUBE_COOKIES_FILE`` – direct path to an existing file.
    2. ``YOUTUBE_COOKIES_B64``  – base64-encoded cookies.txt content.
       Decoded and written to a temp file on first call, then cached.
    """
    global _COOKIES_PATH

    # Empty string = not yet resolved; None = resolved to "no cookies".
    if _COOKIES_PATH != "":
        return _COOKIES_PATH

    # 1. Direct file path
    direct = os.getenv("YOUTUBE_COOKIES_FILE")
    if direct and os.path.isfile(direct):
        _COOKIES_PATH = direct
        log.info("[Downloader] Using YouTube cookies from YOUTUBE_COOKIES_FILE")
        return _COOKIES_PATH

    # 2. Base64-encoded cookies stored in an env var (ideal for Render / Docker)
    b64 = os.getenv("YOUTUBE_COOKIES_B64")
    if b64:
        try:
            decoded = base64.b64decode(b64).decode("utf-8")
            tmp = tempfile.NamedTemporaryFile(
                mode="w", suffix=".txt", delete=False, prefix="yt_cookies_"
            )
            tmp.write(decoded)
            tmp.close()
            _COOKIES_PATH = tmp.name
            log.info(
                "[Downloader] YouTube cookies decoded from YOUTUBE_COOKIES_B64 → %s",
                _COOKIES_PATH,
            )
            return _COOKIES_PATH
        except Exception as exc:
            log.warning("[Downloader] Failed to decode YOUTUBE_COOKIES_B64: %s", exc)

    _COOKIES_PATH = None  # no cookies available
    return None


def download_short(url: str) -> str:
    """Download a YouTube Short to the temp directory.

    Parameters
    ----------
    url:
        YouTube Shorts URL (youtube.com/shorts/<id> or youtu.be/<id>).

    Returns
    -------
    dict
        Dictionary with keys:
        - ``path``: absolute path to the downloaded ``.mp4`` file.
        - ``video_id``: YouTube video ID string.
        - ``title``: video title.
        - ``thumbnail_url``: best available thumbnail URL.

    Raises
    ------
    yt_dlp.utils.DownloadError
        If yt-dlp cannot download the video (private, deleted, geo-blocked, etc.).
    FileNotFoundError
        If the expected output file is missing after a seemingly successful download.
    """
    ensure_temp_dir()

    # yt-dlp options — absolute best quality merged into MP4.
    # Strategy:
    #   - No resolution cap: grab the highest available resolution
    #   - Prefer H.264/AAC for direct Instagram compatibility (no re-encode)
    #   - Fall back to VP9/opus or any codec → ffmpeg re-encodes to H.264/AAC MP4
    #   - remux_video + convert_video ensure final container is always .mp4
    cookies_file: str | None = _get_cookies_path()

    # Player client strategy — NEVER use "web":
    #
    # Since mid-2024 YouTube requires a Proof-of-Origin (PO) token for the "web"
    # client on all datacenter IPs (AWS, Render, GCP, etc.). Even perfectly valid
    # browser cookies are rejected without a PO token, which is the source of the
    # "Sign in to confirm you're not a bot" error.
    #
    # tv_embedded and ios/android are exempt from the PO-token requirement and
    # work from any IP for all public videos — no cookies, no tokens needed.
    #
    # Cookies (if provided) are kept for age-restricted content only; they are
    # harmlessly ignored by clients that don't support them.
    player_clients = ["tv_embedded", "ios", "android", "mweb"]
    log.info("[Downloader] Using embedded/mobile clients (PO-token-free)")

    ydl_opts: dict = {
        "format": (
            # 1st choice: best H.264 video + best m4a audio (no re-encode, fastest)
            "bestvideo[vcodec^=avc1]+bestaudio[ext=m4a]"
            # 2nd choice: best video any codec + best m4a audio (ffmpeg re-encodes video)
            "/bestvideo+bestaudio[ext=m4a]"
            # 3rd choice: best video + best audio any format (DASH)
            "/bestvideo+bestaudio"
            # 4th choice: best pre-merged MP4 (HLS from ios/tv_embedded clients)
            "/best[ext=mp4]"
            # Last resort: absolutely anything available
            "/best"
        ),
        "outtmpl": os.path.join(TEMP_DIR, "%(id)s.%(ext)s"),
        "extractor_args": {
            "youtube": {
                "player_client": player_clients,
            }
        },
        # Only attach the cookie file when using the web client.
        **({"cookiefile": cookies_file} if cookies_file else {}),

        "merge_output_format": "mp4",
        "postprocessors": [
            {
                # Re-encode non-H.264 video to H.264 and audio to AAC
                # (required by Instagram Reels; no-op if already H.264/AAC)
                "key": "FFmpegVideoRemuxer",
                "preferedformat": "mp4",
            },
            {
                "key": "FFmpegVideoConvertor",
                "preferedformat": "mp4",
            },
        ],
        # Keep highest quality when re-encoding: CRF 18 (visually lossless)
        "postprocessor_args": {
            "ffmpeg": [
                "-c:v", "libx264",
                "-crf", "18",
                "-preset", "slow",
                "-c:a", "aac",
                "-b:a", "192k",
                "-movflags", "+faststart",
            ]
        },
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)

    # merge_output_format="mp4" guarantees a .mp4 output when ffmpeg is present.
    # Fall back to the reported ext in case the no-merge fallback was used.
    video_id: str = info.get("id", "video")
    output_path = os.path.join(TEMP_DIR, f"{video_id}.mp4")

    if not os.path.exists(output_path):
        # Fallback: check the ext yt-dlp reported (e.g. webm from the /best fallback)
        ext: str = info.get("ext", "mp4")
        output_path = os.path.join(TEMP_DIR, f"{video_id}.{ext}")

    if not os.path.exists(output_path):
        raise FileNotFoundError(
            f"Expected downloaded file not found for video id='{video_id}'. "
            "Check yt-dlp output and temp/ directory."
        )

    size = os.path.getsize(output_path)
    log.info(f"[Downloader] Saved: {output_path} ({size:,} bytes)")
    return {
        "path": output_path,
        "video_id": video_id,
        "title": info.get("title", ""),
        "thumbnail_url": (
            info.get("thumbnail")
            or f"https://img.youtube.com/vi/{video_id}/maxresdefault.jpg"
        ),
    }
