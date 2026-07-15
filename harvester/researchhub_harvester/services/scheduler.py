"""Scheduling helpers for recurring connector harvests."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

from researchhub_harvester.config import HarvestConnectorDefinition
from researchhub_harvester.services.engine import HarvestEngine


class HarvestScheduler:
    """Register configured connector schedules with APScheduler."""

    def __init__(
        self,
        engine: HarvestEngine,
        scheduler: BackgroundScheduler | None = None,
        runner: Callable[[HarvestEngine, str], None] | None = None,
    ) -> None:
        self.engine = engine
        self.scheduler = scheduler or BackgroundScheduler(timezone="UTC")
        self.runner = runner or _run_connector_blocking

    def register_configured_jobs(self) -> int:
        """Register all enabled connectors that have schedule strings."""

        count = 0
        for definition in self.engine.config.enabled_connectors:
            if not definition.schedule:
                continue
            self.register_connector(definition)
            count += 1
        return count

    def register_connector(self, definition: HarvestConnectorDefinition) -> None:
        """Register one connector schedule."""

        trigger = build_trigger(definition.schedule)
        self.scheduler.add_job(
            self.runner,
            trigger=trigger,
            args=[self.engine, definition.code],
            id=f"harvest:{definition.code}",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
        )

    def start(self) -> None:
        """Start the scheduler."""

        self.scheduler.start()

    def shutdown(self) -> None:
        """Stop the scheduler."""

        self.scheduler.shutdown()


def build_trigger(schedule: str) -> Any:
    """Build an APScheduler trigger from a compact schedule string.

    Supported forms:
    - ``interval:3600``
    - ``interval:seconds=3600``
    - ``interval:minutes=30``
    - ``cron:*/15 * * * *``
    - ``@hourly`` and ``@daily``
    """

    value = schedule.strip()
    if value == "@hourly":
        return CronTrigger(minute=0, timezone="UTC")
    if value == "@daily":
        return CronTrigger(hour=0, minute=0, timezone="UTC")
    if value.startswith("interval:"):
        return _interval_trigger(value.removeprefix("interval:"))
    if value.startswith("cron:"):
        return _cron_trigger(value.removeprefix("cron:").strip())
    msg = f"Unsupported harvest schedule: {schedule}"
    raise ValueError(msg)


def _interval_trigger(value: str) -> IntervalTrigger:
    """Build an interval trigger from compact configuration."""

    if "=" not in value:
        return IntervalTrigger(seconds=int(value), timezone="UTC")
    key, raw_amount = value.split("=", 1)
    amount = int(raw_amount)
    if key not in {"seconds", "minutes", "hours", "days"}:
        msg = f"Unsupported interval unit: {key}"
        raise ValueError(msg)
    return IntervalTrigger(**{key: amount}, timezone="UTC")


def _cron_trigger(value: str) -> CronTrigger:
    """Build a cron trigger from five-part crontab syntax."""

    parts = value.split()
    if len(parts) != 5:
        msg = "cron schedule must contain five fields: minute hour day month day_of_week"
        raise ValueError(msg)
    minute, hour, day, month, day_of_week = parts
    return CronTrigger(
        minute=minute,
        hour=hour,
        day=day,
        month=month,
        day_of_week=day_of_week,
        timezone="UTC",
    )


def _run_connector_blocking(engine: HarvestEngine, connector_code: str) -> None:
    """Run one async connector job from APScheduler's sync worker thread."""

    asyncio.run(engine.run_connector(connector_code))

