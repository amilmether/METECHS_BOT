import os
import logging

import yt_dlp

from utils.cleanup import ensure_temp_dir

log = logging.getLogger(__name__)

TEMP_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "temp")


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
    # Optional: path to a Netscape-format cookies.txt exported from a browser.
    # Set YOUTUBE_COOKIES_FILE=/path/to/cookies.txt in your environment/Render env vars.
    cookies_file: str | None = os.getenv("YOUTUBE_COOKIES_FILE")

    ydl_opts: dict = {
        "format": (
            # 1st choice: best H.264 video + best m4a audio (no re-encode, fastest)
            "bestvideo[vcodec^=avc1]+bestaudio[ext=m4a]"
            # 2nd choice: best video any codec + best m4a audio (ffmpeg re-encodes video)
            "/bestvideo+bestaudio[ext=m4a]"
            # 3rd choice: best video + best audio any format
            "/bestvideo+bestaudio"
            # Last resort: best pre-merged single file
            "/best"
        ),
        "outtmpl": os.path.join(TEMP_DIR, "%(id)s.%(ext)s"),
        # Use mobile player clients to bypass YouTube bot-detection.
        # ios  → signed URLs, no cookies required, works for all public videos.
        # android and web are tried in order as fallbacks.
        "extractor_args": {
            "youtube": {
                "player_client": ["ios", "android", "web"],
            }
        },
        **(  # attach cookie file only when the path is set and the file exists
            {"cookiefile": cookies_file}
            if cookies_file and os.path.isfile(cookies_file)
            else {}
        ),
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
