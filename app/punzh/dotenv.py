"""Host .env for local Docker, re-read by runserver without an image rebuild."""

import os
from pathlib import Path

# Baked into the image at build. Local compose bind-mounts the host file here.
DOTENV_PATH = Path("/.env")


def dotenv_should_overwrite():
    """True in the runserver worker, which inherits a stale environment."""
    return os.environ.get("RUN_MAIN") == "true"


def watch_dotenv(sender, **kwargs):
    """Ask the dev reloader to restart when the mounted .env changes."""
    if DOTENV_PATH.is_file():
        sender.extra_files.add(DOTENV_PATH)
