import logging
import time

from lookout.config import get_settings

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    logger.info("worker started")

    while True:
        time.sleep(settings.worker_poll_seconds)


if __name__ == "__main__":
    main()
