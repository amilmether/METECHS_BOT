import os
import logging

log = logging.getLogger(__name__)

# Resolved at import time so all modules agree on the same path
TEMP_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "temp")


def ensure_temp_dir() -> None:
    """Create the temp directory if it does not already exist."""
    os.makedirs(TEMP_DIR, exist_ok=True)


def delete_temp_file(path: str) -> None:
    """Delete the file at *path*.

    Designed to be called from a ``finally`` block — never raises.
    Logs a warning if the deletion fails (e.g. permissions, already gone).

    Parameters
    ----------
    path:
        Absolute path to the file to delete. No-ops if *path* is falsy
        or the file does not exist.
    """
    if not path:
        return
    try:
        if os.path.exists(path):
            os.remove(path)
            log.info(f"[Cleanup] Deleted temp file: {path}")
        else:
            log.debug(f"[Cleanup] Temp file already gone: {path}")
    except OSError as exc:
        log.warning(f"[Cleanup] Could not delete temp file {path}: {exc}")
