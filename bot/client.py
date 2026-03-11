import logging
import discord
from discord.ext import commands

log = logging.getLogger(__name__)


class MetechsBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True

        super().__init__(
            command_prefix="!",
            intents=intents,
            help_command=None,  # Disable default help; add custom later if needed
        )

    async def setup_hook(self) -> None:
        from bot.cogs.post_command import PostCog

        await self.add_cog(PostCog(self))
        log.info("[Bot] PostCog loaded.")

    async def on_ready(self) -> None:
        log.info(f"[Bot] Ready — logged in as {self.user} (ID: {self.user.id})")

    async def on_command_error(
        self, ctx: commands.Context, error: commands.CommandError
    ) -> None:
        if isinstance(error, commands.CommandNotFound):
            return  # Silently ignore unknown commands
        log.error(f"[Bot] Unhandled command error in '{ctx.command}': {error}")
        await ctx.reply(f"❌ An unexpected error occurred: `{error}`")
