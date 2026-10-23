"""Host .env bind-mounted in dev and prod; read again when the process starts."""

import os
from pathlib import Path

# Baked into the image at build. Compose bind-mounts the host file over this path.
DOTENV_PATH = Path("/.env")


def dotenv_should_overwrite():
    """True in the runserver worker, which inherits a stale environment."""
    return os.environ.get("RUN_MAIN") == "true"


def watch_dotenv(sender, **kwargs):
    """Ask the dev reloader to restart when the mounted .env changes."""
    if DOTENV_PATH.is_file():
        sender.extra_files.add(DOTENV_PATH)
