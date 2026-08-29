from unittest.mock import Mock

import pytest

from nonprofit_jobs import JobKind, ScheduledJobRequest, run_scheduled_job


def request(job: JobKind = JobKind.DONOR_RECEIPTS) -> ScheduledJobRequest:
    return ScheduledJobRequest(
        run_id="run-2026-08-21-0200",
        job=job,
        scheduled_for="2026-08-21T02:00:00+00:00",
    )


def test_completed_receipt_run_reports_processed_count() -> None:
    client = Mock()
    result = run_scheduled_job(
        request(),
        {JobKind.DONOR_RECEIPTS: lambda _: 125},
        client,
    )

    assert result.status == "completed"
    assert result.records_processed == 125
    client.errors.capture.assert_not_called()


def test_failed_campaign_run_is_grouped_and_deduplicated_by_run() -> None:
    client = Mock()

    def fail(_: ScheduledJobRequest) -> int:
        raise ValueError("report window is empty")

    with pytest.raises(ValueError, match="report window is empty"):
        run_scheduled_job(
            request(JobKind.CAMPAIGN_REPORTING),
            {JobKind.CAMPAIGN_REPORTING: fail},
            client,
        )

    payload = client.errors.capture.call_args.kwargs
    assert payload["fingerprint"] == ["nonprofit-job", "campaign_reporting"]
    assert payload["idempotency_key"] == (
        "job-failure:campaign_reporting:run-2026-08-21-0200"
    )
    assert payload["context"]["scheduled_for"] == "2026-08-21T02:00:00+00:00"
    assert payload["exception"]["type"] == "ValueError"
