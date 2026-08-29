"""Run nonprofit jobs and report exceptions with job-specific grouping."""

from __future__ import annotations

import argparse
import traceback
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Callable, Mapping

from infrai_client import InfraiClient


class JobKind(str, Enum):
    DONOR_RECEIPTS = "donor_receipts"
    VOLUNTEER_REMINDERS = "volunteer_reminders"
    CAMPAIGN_REPORTING = "campaign_reporting"


@dataclass(frozen=True)
class ScheduledJobRequest:
    run_id: str
    job: JobKind
    scheduled_for: str


@dataclass(frozen=True)
class JobResult:
    run_id: str
    job: JobKind
    status: str
    records_processed: int


JobHandler = Callable[[ScheduledJobRequest], int]


def run_scheduled_job(
    request: ScheduledJobRequest,
    handlers: Mapping[JobKind, JobHandler],
    client: InfraiClient,
) -> JobResult:
    """Dispatch one known job; capture and re-raise a handler exception."""
    handler = handlers[request.job]
    try:
        processed = handler(request)
    except Exception as exc:
        client.errors.capture(
            title=f"{request.job.value} scheduled run failed",
            message=f"{type(exc).__name__}: {exc}",
            exception={
                "type": type(exc).__name__,
                "value": str(exc),
                "stacktrace": traceback.format_exc(),
            },
            level="error",
            fingerprint=["nonprofit-job", request.job.value],
            context=asdict(request),
            service="nonprofit-scheduler",
            idempotency_key=f"job-failure:{request.job.value}:{request.run_id}",
        )
        raise

    return JobResult(request.run_id, request.job, "completed", processed)


def _sample_handler(request: ScheduledJobRequest) -> int:
    counts = {
        JobKind.DONOR_RECEIPTS: 42,
        JobKind.VOLUNTEER_REMINDERS: 18,
        JobKind.CAMPAIGN_REPORTING: 7,
    }
    return counts[request.job]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("job", choices=[kind.value for kind in JobKind])
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    request = ScheduledJobRequest(
        run_id=args.run_id,
        job=JobKind(args.job),
        scheduled_for=datetime.now(timezone.utc).isoformat(),
    )
    handlers = {kind: _sample_handler for kind in JobKind}
    result = run_scheduled_job(request, handlers, InfraiClient())
    print(asdict(result))


if __name__ == "__main__":
    main()
