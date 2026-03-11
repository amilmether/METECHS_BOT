import os
import logging
from dotenv import load_dotenv
from bot.client import MetechsBot

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

log = logging.getLogger(__name__)


def main() -> None:
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError(
            "DISCORD_TOKEN is not set. Copy .env.example to .env and fill in your token."
        )

    bot = MetechsBot()
    log.info("Starting METECHS_BOT...")
    bot.run(token, log_handler=None)  # logging already configured above


if __name__ == "__main__":
    main()
