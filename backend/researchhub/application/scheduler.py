"""APScheduler entrypoint for recurring connector harvesting."""

import asyncio
import time
from pathlib import Path

from researchhub_harvester.config import load_harvest_config
from researchhub_harvester.services.engine import HarvestEngine, aggregate_reports
from researchhub_harvester.services.scheduler import HarvestScheduler

from researchhub.application.harvest_store import SQLAlchemyHarvestStore
from researchhub.core.config import get_settings
from researchhub.core.logging import configure_logging, get_logger


def main() -> None:
    """Start the scheduler process and register configured harvest jobs."""

    settings = get_settings()
    configure_logging(settings.log_level)
    logger = get_logger(__name__)
    config_path = Path(settings.harvest_config_path or "")
    if not config_path.exists():
        logger.warning("harvest_config_missing", path=str(config_path))
        return

    engine_config = load_harvest_config(config_path)
    engine = HarvestEngine(engine_config, store=SQLAlchemyHarvestStore())
    scheduler = HarvestScheduler(engine)
    scheduled = scheduler.register_configured_jobs()
    scheduler.start()
    logger.info("scheduler_started", scheduled_jobs=scheduled)
    try:
        while True:
            time.sleep(30)
    finally:
        scheduler.shutdown()


async def run_once_from_config(config_path: str | Path) -> dict[str, object]:
    """Run every enabled connector from a JSON config once and return a report."""

    engine = HarvestEngine(load_harvest_config(config_path), store=SQLAlchemyHarvestStore())
    reports = await engine.run_all()
    return aggregate_reports(reports)


def run_once(config_path: str | Path) -> dict[str, object]:
    """Synchronous wrapper for one-off harvest execution."""

    return asyncio.run(run_once_from_config(config_path))


if __name__ == "__main__":
    main()
