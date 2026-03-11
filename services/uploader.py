"""
uploader.py — Public URL bridge (reserved for URL-based upload strategy).

The bot currently uses Instagram's Resumable Upload API directly
(implemented in services/instagram.py), so this module is not active
in the default flow.

To switch to a URL-based strategy:
  1. Implement `get_public_url()` below to upload the local file to an
     external host (AWS S3, Cloudinary, Cloudflare R2, etc.) and return
     the resulting public URL.
  2. In services/instagram.py, change `create_reel_container()` to accept
     a `video_url` parameter and pass it instead of `upload_type=resumable`.
  3. Remove the `upload_video_resumable()` call from post_command.py.
"""


def get_public_url(local_path: str) -> str:
    """Return a publicly accessible URL for *local_path*.

    Not implemented by default — the resumable upload path is used instead.
    Implement this function if you prefer a URL-based upload strategy.

    Example implementation skeleton (Cloudinary):
        import cloudinary.uploader
        result = cloudinary.uploader.upload(local_path, resource_type="video")
        return result["secure_url"]
    """
    raise NotImplementedError(
        "URL-based upload strategy is not configured. "
        "Either implement get_public_url() with your preferred host "
        "(S3, Cloudinary, R2), or use the default resumable upload path."
    )
