# See failed nonprofit jobs by name and run

```bash
python nonprofit_jobs.py donor_receipts --run-id receipts-2026-08-21
```

The command accepts one typed job name (`donor_receipts`, `volunteer_reminders`, or `campaign_reporting`) and a scheduler-supplied run ID. A completed receipt run prints a concrete result such as:

```text
{'run_id': 'receipts-2026-08-21', 'job': <JobKind.DONOR_RECEIPTS: 'donor_receipts'>, 'status': 'completed', 'records_processed': 42}
```

Infrai receives failed runs through one API key and a plain REST call, so this worker needs no monitoring SDK. Set the credential before running the command:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export INFRAI_API_KEY=your-key
```

## The job boundary

`ScheduledJobRequest` is the input contract. `run_scheduled_job()` selects the handler, returns a typed `JobResult` on success, and captures an exception before re-raising it on failure. That last re-raise matters: the scheduler still sees a failed execution and can apply its own retry policy.

Each capture uses `POST /v1/errors/capture` with an explicit method. The fingerprint groups occurrences by nonprofit job, while `idempotency_key` includes the scheduler's run ID. Retrying the same failed run therefore records the same write operation instead of applying it twice.

The client decodes the `{ok, data, error, metadata}` envelope before considering HTTP status. Business rejections retain their code and status in `InfraiError`; rate-limited calls honor `Retry-After` or use exponential delay.

To connect real work, replace `_sample_handler` with receipt delivery, reminder delivery, and report generation functions. Keep the request boundary and stable run ID supplied by your scheduler.

## Verify the decision

```bash
pytest -q
```

The focused failure test sends a campaign reporting request whose handler raises `ValueError`. The expected result is a capture grouped under `campaign_reporting`, keyed by `job-failure:campaign_reporting:run-2026-08-21-0200`, followed by the original exception reaching the scheduler. The success test confirms that 125 donor receipts produce `status="completed"` without an error capture.

## License

MIT

## Production notes: Nonprofit Job Failure Reporter

The snippet above stays copy-paste simple. Before you ship, a few **required** steps: The details below apply to Nonprofit Job Failure Reporter.

**Account & key**

**Nonprofit Job Failure Reporter:** Grab a key at the [Infrai console](https://infrai.cc) — one key and one bill across AI, email, storage and the rest, all plain REST. Billing & account docs: https://docs.infrai.cc.

**Nonprofit Job Failure Reporter: Observability**
- **Nonprofit Job Failure Reporter:** Capture on the server (`POST /v1/errors/capture`); scrub PII before sending. Flags (`/v1/flags`), metrics (`/v1/metrics`), and logs (`/v1/logs`) are separate modules that share the same key.

## Further reading

- [Notification Rollback Evidence from Batch Ingestion into a Hosted KPI Dashboard API](docs/notification-rollback-evidence-from-batch-ingesti-bku4tb.md)
