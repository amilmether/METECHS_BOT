import base64
import json
import os
import logging

import yt_dlp

from utils.cleanup import ensure_temp_dir

log = logging.getLogger(__name__)

TEMP_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "temp")

# yt-dlp cache dir used for OAuth2 token storage.
_CACHE_DIR = "/tmp/yt-dlp-cache"
_OAUTH2_TOKEN_PATH = os.path.join(_CACHE_DIR, "youtube-oauth2", "access_token_data.json")

# Module-level flag — set up once per process.
_OAUTH2_READY: bool | None = None  # None = not yet checked


def _setup_oauth2() -> bool:
    """Decode YOUTUBE_OAUTH2_TOKEN env var and write it to the yt-dlp cache.

    Returns True if the token is in place and yt-dlp should use OAuth2,
    False if the env var is absent (fall back to embedded/mobile clients).
    """
    global _OAUTH2_READY
    if _OAUTH2_READY is not None:
        return _OAUTH2_READY

    token_b64 = os.getenv("YOUTUBE_OAUTH2_TOKEN")
    if not token_b64:
        log.info("[Downloader] YOUTUBE_OAUTH2_TOKEN not set — using embedded/mobile clients")
        _OAUTH2_READY = False
        return False

    try:
        decoded = base64.b64decode(token_b64).decode("utf-8")
        json.loads(decoded)  # validate it's real JSON before writing
        os.makedirs(os.path.dirname(_OAUTH2_TOKEN_PATH), exist_ok=True)
        with open(_OAUTH2_TOKEN_PATH, "w") as fh:
            fh.write(decoded)
        log.info("[Downloader] YouTube OAuth2 token loaded from YOUTUBE_OAUTH2_TOKEN")
        _OAUTH2_READY = True
        return True
    except Exception as exc:
        log.warning("[Downloader] Failed to load YOUTUBE_OAUTH2_TOKEN: %s — falling back", exc)
        _OAUTH2_READY = False
        return False


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

    use_oauth2 = _setup_oauth2()

    # OAuth2: authenticates via a long-lived refresh token — works from any IP forever.
    # Fallback: tv_embedded/ios/android are PO-token-exempt for public videos,
    # but may be blocked on some datacenter IP ranges.
    if use_oauth2:
        extractor_args: dict = {"youtube": {"player_client": ["web"]}}
        auth_opts: dict = {
            "username": "oauth2",
            "password": "",
            "cachedir": _CACHE_DIR,
        }
        log.info("[Downloader] Using OAuth2 authentication")
    else:
        extractor_args = {"youtube": {"player_client": ["tv_embedded", "ios", "android", "mweb"]}}
        auth_opts = {}

    # yt-dlp options — absolute best quality merged into MP4.
    # Strategy:
    #   - No resolution cap: grab the highest available resolution
    #   - Prefer H.264/AAC for direct Instagram compatibility (no re-encode)
    #   - Fall back to VP9/opus or any codec → ffmpeg re-encodes to H.264/AAC MP4
    #   - remux_video + convert_video ensure final container is always .mp4
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
        "extractor_args": extractor_args,
        **auth_opts,
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
