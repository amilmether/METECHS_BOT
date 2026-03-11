import asyncio
import logging

from discord.ext import commands

from services.downloader import download_short
from services.instagram import (
    create_reel_container,
    upload_video_resumable,
    poll_container_status,
    publish_container,
    get_media_permalink,
)
from services.caption import generate_caption, scrape_product_title
from services.website import post_product
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

        # With amazon_url: download, caption, container, upload, poll, publish, website = 7
        # Without amazon_url: download, container, upload, poll, publish, website = 6
        total_steps = 7 if amazon_url else 6
        status_msg = await ctx.reply(f"⏳ **[1/{total_steps}]** Downloading YouTube Short…")
        local_path: str | None = None
        caption: str = ""
        product_title: str = ""
        thumbnail_url: str = ""

        try:
            ensure_temp_dir()

            # ── 2. Download ────────────────────────────────────────────
            try:
                dl = await asyncio.to_thread(download_short, url)
                local_path = dl["path"]
                product_title = dl["title"]      # YouTube title — fallback if no Amazon URL
                thumbnail_url = dl["thumbnail_url"]
                log.info(f"[PostCog] Downloaded to: {local_path}")
            except Exception as exc:
                log.error(f"[PostCog] Download failed: {exc}")
                await status_msg.edit(content=f"❌ **Download failed.**\n```{exc}```")
                return

            step = 2

            # ── 3. AI caption (only when amazon_url provided) ──────────
            if amazon_url:
                await status_msg.edit(
                    content=f"⏳ **[{step}/{total_steps}]** Generating AI caption from Amazon product…"
                )
                try:
                    # Scrape title once — reused for caption AND website posting
                    product_title = await asyncio.to_thread(scrape_product_title, amazon_url)
                    caption = await asyncio.to_thread(generate_caption, amazon_url, product_title)
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
            step += 1

            # ── 8. Update website ──────────────────────────────────────
            await status_msg.edit(
                content=f"⏳ **[{step}/{total_steps}]** Updating website product listing…"
            )
            ig_permalink = ""
            website_product_id = "N/A"
            try:
                ig_permalink = await asyncio.to_thread(get_media_permalink, media_id)
                if amazon_url:
                    website_result = await asyncio.to_thread(
                        post_product,
                        product_title or "New Product",
                        amazon_url,
                        thumbnail_url,
                        ig_permalink,
                    )
                    website_product_id = website_result.get("id", "N/A")
                    log.info(f"[PostCog] Website updated — product ID: {website_product_id}")
                else:
                    log.info("[PostCog] No Amazon URL provided — skipping website post.")
            except Exception as exc:
                # Non-fatal: the Reel is already live — warn but don't fail hard
                log.error(f"[PostCog] Website update failed: {exc}")
                await status_msg.edit(
                    content=(
                        f"⚠️ **Reel published but website update failed.**\n"
                        f"📸 Instagram Media ID: `{media_id}`\n"
                        f"```{exc}```"
                    )
                )
                return

            caption_preview = (
                f"\n\n📝 **Caption preview:**\n>>> {caption[:300]}{'…' if len(caption) > 300 else ''}"
                if caption else ""
            )
            await status_msg.edit(
                content=(
                    f"✅ **Done!** Reel published & website updated.\n"
                    f"📸 Instagram Media ID: `{media_id}`\n"
                    f"🌐 Website Product ID: `{website_product_id}`\n"
                    f"🔗 {ig_permalink}"
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
