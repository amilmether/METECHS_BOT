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
from services.caption import generate_caption
from utils.cleanup import delete_temp_file, ensure_temp_dir
from utils.validators import validate_youtube_url, validate_amazon_url

log = logging.getLogger(__name__)

USAGE = (
    "`!post <youtube_shorts_url> [amazon_affiliate_url]`\n"
    "Examples:\n"
    "• `!post https://www.youtube.com/shorts/abc123`\n"
    "• `!post https://www.youtube.com/shorts/abc123 https://amzn.to/xyz`"
)


class PostCog(commands.Cog):
    """Handles the !post <youtube_shorts_url> [amazon_affiliate_url] command."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    # ------------------------------------------------------------------
    # Command
    # ------------------------------------------------------------------

    @commands.command(name="post")
    async def post(
        self,
        ctx: commands.Context,
        url: str = None,
        amazon_url: str = None,
    ) -> None:
        """Download a YouTube Short and publish it as an Instagram Reel.

        Usage: !post <youtube_shorts_url> [amazon_affiliate_url]
        """
        # ── 1. Input validation ────────────────────────────────────────
        if not url:
            await ctx.reply(f"❌ **Usage:** {USAGE}")
            return

        if not validate_youtube_url(url):
            await ctx.reply(
                "❌ **Invalid YouTube URL.** Please provide a valid YouTube Shorts link.\n"
                "Accepted formats:\n"
                "• `https://www.youtube.com/shorts/<id>`\n"
                "• `https://youtu.be/<id>`"
            )
            return

        if amazon_url and not validate_amazon_url(amazon_url):
            await ctx.reply(
                "❌ **Invalid Amazon URL.** Please provide a valid Amazon or amzn.to link."
            )
            return

        total_steps = 6 if amazon_url else 5
        status_msg = await ctx.reply("⏳ **[1/{total}]** Downloading YouTube Short…".replace("{total}", str(total_steps)))
        local_path: str | None = None
        caption: str = ""

        try:
            ensure_temp_dir()

            # ── 2. Download ────────────────────────────────────────────
            try:
                local_path = await asyncio.to_thread(download_short, url)
                log.info(f"[PostCog] Downloaded to: {local_path}")
            except Exception as exc:
                log.error(f"[PostCog] Download failed: {exc}")
                await status_msg.edit(content=f"❌ **Download failed.**\n```{exc}```")
                return

            # ── 3. AI caption (only when amazon_url provided) ──────────
            step = 2
            if amazon_url:
                await status_msg.edit(
                    content=f"⏳ **[{step}/{total_steps}]** Generating AI caption from Amazon product…"
                )
                try:
                    caption = await asyncio.to_thread(generate_caption, amazon_url)
                    log.info(f"[PostCog] Caption generated ({len(caption)} chars).")
                except Exception as exc:
                    log.error(f"[PostCog] Caption generation failed: {exc}")
                    await status_msg.edit(
                        content=f"❌ **Caption generation failed.**\n```{exc}```"
                    )
                    return
                step += 1

            # ── 4. Create Instagram container ──────────────────────────
            await status_msg.edit(
                content=f"⏳ **[{step}/{total_steps}]** Creating Instagram Reel container…"
            )
            try:
                container_id, upload_uri = await asyncio.to_thread(
                    create_reel_container, caption=caption
                )
                log.info(f"[PostCog] Container created: {container_id}")
            except Exception as exc:
                log.error(f"[PostCog] Container creation failed: {exc}")
                await status_msg.edit(
                    content=f"❌ **Instagram API error** (create container).\n```{exc}```"
                )
                return
            step += 1

            # ── 5. Upload video binary ─────────────────────────────────
            await status_msg.edit(
                content=f"⏳ **[{step}/{total_steps}]** Uploading video to Instagram…"
            )
            try:
                await asyncio.to_thread(upload_video_resumable, upload_uri, local_path)
                log.info("[PostCog] Video upload complete.")
            except Exception as exc:
                log.error(f"[PostCog] Video upload failed: {exc}")
                await status_msg.edit(content=f"❌ **Video upload failed.**\n```{exc}```")
                return
            step += 1

            # ── 6. Poll processing status ──────────────────────────────
            await status_msg.edit(
                content=f"⏳ **[{step}/{total_steps}]** Waiting for Instagram to process video…"
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
            step += 1

            # ── 7. Publish ─────────────────────────────────────────────
            await status_msg.edit(content=f"⏳ **[{step}/{total_steps}]** Publishing Reel…")
            try:
                media_id = await asyncio.to_thread(publish_container, container_id)
                log.info(f"[PostCog] Reel published: {media_id}")
            except Exception as exc:
                log.error(f"[PostCog] Publish failed: {exc}")
                await status_msg.edit(
                    content=f"❌ **Instagram publish failed.**\n```{exc}```"
                )
                return

            caption_preview = f"\n\n📝 **Caption preview:**\n>>> {caption[:300]}{'…' if len(caption) > 300 else ''}" if caption else ""
            await status_msg.edit(
                content=(
                    f"✅ **Reel published successfully!**\n"
                    f"📸 Instagram Media ID: `{media_id}`"
                    f"{caption_preview}"
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
            await ctx.reply(f"❌ **Usage:** {USAGE}")
        else:
            log.error(f"[PostCog] Command error: {error}")
            await ctx.reply(f"❌ **Command error:** `{error}`")
