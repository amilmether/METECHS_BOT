import os
import threading
import logging
from http.server import BaseHTTPRequestHandler, HTTPServer
from logging.handlers import RotatingFileHandler
from dotenv import load_dotenv
from bot.client import MetechsBot

load_dotenv()

_LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(_LOG_DIR, exist_ok=True)

_formatter = logging.Formatter(
    fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

_stream_handler = logging.StreamHandler()           # stdout → visible in Render logs
_stream_handler.setFormatter(_formatter)

_file_handler = RotatingFileHandler(              # rotating file, max 5 MB × 3 backups
    os.path.join(_LOG_DIR, "bot.log"),
    maxBytes=5 * 1024 * 1024,
    backupCount=3,
    encoding="utf-8",
)
_file_handler.setFormatter(_formatter)

logging.basicConfig(level=logging.INFO, handlers=[_stream_handler, _file_handler])

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Minimal HTTP health-check server
# Render (when deployed as a Web Service) requires at least one open port.
# This keeps the deployment alive; a Background Worker doesn't need this.
# ---------------------------------------------------------------------------
class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format: str, *args: object) -> None:  # suppress access logs
        pass


def _start_health_server() -> None:
    port = int(os.getenv("PORT", "8080"))
    server = HTTPServer(("0.0.0.0", port), _HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    log.info("Health-check server listening on port %d", port)


def main() -> None:
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError(
            "DISCORD_TOKEN is not set. Copy .env.example to .env and fill in your token."
        )

    _start_health_server()  # satisfy Render's port-scan when running as a Web Service
    bot = MetechsBot()
    log.info("Starting METECHS_BOT...")
    bot.run(token, log_handler=None)  # logging already configured above


if __name__ == "__main__":
    main()
