import asyncio
import logging

from discord.ext import commands

from services.downloader import download_short
from services.instagram import (
    create_reel_container,
    upload_video_resumable,
    poll_container_status,
    publish_container,
)
from utils.cleanup import delete_temp_file, ensure_temp_dir
from utils.validators import validate_youtube_url

log = logging.getLogger(__name__)


class PostCog(commands.Cog):
    """Handles the !post <youtube_shorts_url> command."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ------------------------------------------------------------------
    # Command
    # ------------------------------------------------------------------

    @commands.command(name="post")
    async def post(self, ctx: commands.Context, url: str = None) -> None:
        """Download a YouTube Short and publish it as an Instagram Reel.

        Usage: !post <youtube_shorts_url>
        """
        # ── 1. Input validation ────────────────────────────────────────
        if not url:
            await ctx.reply(
                "❌ **Usage:** `!post <youtube_shorts_url>`\n"
                "Example: `!post https://www.youtube.com/shorts/abc123`"
            )
            return

        if not validate_youtube_url(url):
            await ctx.reply(
                "❌ **Invalid URL.** Please provide a valid YouTube Shorts link.\n"
                "Accepted formats:\n"
                "• `https://www.youtube.com/shorts/<id>`\n"
                "• `https://youtu.be/<id>`"
            )
            return

        status_msg = await ctx.reply("⏳ **[1/5]** Downloading YouTube Short…")
        local_path: str | None = None

        try:
            ensure_temp_dir()

            # ── 2. Download ────────────────────────────────────────────
            try:
                local_path = await asyncio.to_thread(download_short, url)
                log.info(f"[PostCog] Downloaded to: {local_path}")
            except Exception as exc:
                log.error(f"[PostCog] Download failed: {exc}")
                await status_msg.edit(
                    content=f"❌ **Download failed.**\n```{exc}```"
                )
                return

            # ── 3. Create Instagram container ──────────────────────────
            await status_msg.edit(
                content="⏳ **[2/5]** Creating Instagram Reel container…"
            )
            try:
                container_id, upload_uri = await asyncio.to_thread(
                    create_reel_container, caption=""
                )
                log.info(f"[PostCog] Container created: {container_id}")
            except Exception as exc:
                log.error(f"[PostCog] Container creation failed: {exc}")
                await status_msg.edit(
                    content=f"❌ **Instagram API error** (create container).\n```{exc}```"
                )
                return

            # ── 4. Upload video binary ─────────────────────────────────
            await status_msg.edit(
                content="⏳ **[3/5]** Uploading video to Instagram…"
            )
            try:
                await asyncio.to_thread(upload_video_resumable, upload_uri, local_path)
                log.info("[PostCog] Video upload complete.")
            except Exception as exc:
                log.error(f"[PostCog] Video upload failed: {exc}")
                await status_msg.edit(
                    content=f"❌ **Video upload failed.**\n```{exc}```"
                )
                return

            # ── 5. Poll processing status ──────────────────────────────
            await status_msg.edit(
                content="⏳ **[4/5]** Waiting for Instagram to process video…"
            )
            try:
                await asyncio.to_thread(poll_container_status, container_id)
                log.info("[PostCog] Container status: FINISHED.")
            except TimeoutError:
                log.error("[PostCog] Container processing timed out.")
                await status_msg.edit(
                    content=(
                        "❌ **Instagram processing timed out.** "
                        "The container may still be processing — check your Instagram account."
                    )
                )
                return
            except Exception as exc:
                log.error(f"[PostCog] Container polling error: {exc}")
                await status_msg.edit(
                    content=f"❌ **Instagram processing error.**\n```{exc}```"
                )
                return

            # ── 6. Publish ─────────────────────────────────────────────
            await status_msg.edit(content="⏳ **[5/5]** Publishing Reel…")
            try:
                media_id = await asyncio.to_thread(publish_container, container_id)
                log.info(f"[PostCog] Reel published: {media_id}")
            except Exception as exc:
                log.error(f"[PostCog] Publish failed: {exc}")
                await status_msg.edit(
                    content=f"❌ **Instagram publish failed.**\n```{exc}```"
                )
                return

            await status_msg.edit(
                content=(
                    f"✅ **Reel published successfully!**\n"
                    f"📸 Instagram Media ID: `{media_id}`"
                )
            )

        except Exception as exc:
            log.exception(f"[PostCog] Unhandled error in !post: {exc}")
            await status_msg.edit(
                content="❌ **An unexpected error occurred.** Check the bot logs."
            )

        finally:
            # Always clean up temp file, regardless of success or failure
            if local_path:
                delete_temp_file(local_path)

    # ------------------------------------------------------------------
    # Error handler
    # ------------------------------------------------------------------

    @post.error
    async def post_error(
        self, ctx: commands.Context, error: commands.CommandError
    ) -> None:
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.reply(
                "❌ **Usage:** `!post <youtube_shorts_url>`\n"
                "Example: `!post https://www.youtube.com/shorts/abc123`"
            )
        else:
            log.error(f"[PostCog] Command error: {error}")
            await ctx.reply(f"❌ **Command error:** `{error}`")
