"""Worker entry point: ``python -m app.worker`` (job runner plus scheduler)."""

from app.core.clock import SystemClock
from app.core.config import get_settings
from app.core.db import get_session_factory
from app.core.logging import configure_logging, get_logger
from app.handlers import load_handlers
from app.jobs.worker import Worker


def main() -> None:
    settings = get_settings()  # refuses to start on an unsafe production configuration
    configure_logging(settings)
    get_logger(__name__).info("startup", process="worker", **settings.public_dict())
    load_handlers()
    Worker(
        get_session_factory(),
        SystemClock(),
        concurrency=settings.worker_concurrency,
        poll_interval=settings.worker_poll_interval_seconds,
        lease_seconds=settings.job_lease_seconds,
    ).run_forever()


if __name__ == "__main__":
    main()
