from __future__ import annotations

import logging
import signal
import time

from app.config import settings
from app.modules.highlight_generator.worker import MEDIA_HANDLERS
from app.platform.worker import process_one


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("nexus.highlight_media_worker")
running = True


def _stop(_signum, _frame) -> None:
    global running
    running = False


def main() -> None:
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    logger.info("Highlight media worker started with concurrency=1")
    while running:
        if not process_one(handlers=MEDIA_HANDLERS):
            time.sleep(max(0.1, settings.media_worker_poll_seconds))


if __name__ == "__main__":
    main()

