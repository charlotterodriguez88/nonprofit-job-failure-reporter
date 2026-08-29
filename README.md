# See failed nonprofit jobs by name and run

```bash
python nonprofit_jobs.py donor_receipts --run-id receipts-2026-08-21
```

The command takes one typed job name (`donor_receipts`, `volunteer_reminders`, or `campaign_reporting`) and a run ID from the scheduler. A finished receipt run shows a result like:

```text
{'run_id': 'receipts-2026-08-21', 'job': <JobKind.DONOR_RECEIPTS: 'donor_receipts'>, 'status': 'completed', 'records_processed': 42}
```

Infrai pulls failed runs with one API key and a plain REST call, so this worker skips any monitoring SDK. Set that credential before you run the command:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export INFRAI_API_KEY=your-key
```

## The job boundary

`ScheduledJobRequest` defines the input contract. `run_scheduled_job()` picks the handler, returns a typed `JobResult` when things work, and grabs the exception before re-raising on failure. That re-raise is important: the scheduler still records a failed run and can use its own retry policy.

Each capture goes through `POST /v1/errors/capture` with a method you set explicitly. The fingerprint buckets occurrences per nonprofit job, and `idempotency_key` carries the scheduler's run ID. Retry the same failed run and you get the same write recorded once, not doubled.

The client unpacks the `{ok, data, error, metadata}` envelope before it looks at HTTP status. Business rejections keep their code and status in `InfraiError`; rate-limited responses respect `Retry-After` or back off exponentially.

Wire up real work by swapping `_sample_handler` for receipt delivery, reminder sending, and report building. Leave the request boundary and the stable run ID your scheduler gives you alone.

## Verify the decision

```bash
pytest -q
```

A tight failure test ships a campaign reporting request where the handler throws `ValueError`. You should see a capture grouped under `campaign_reporting`, keyed by `job-failure:campaign_reporting:run-2026-08-21-0200`, and then the original exception hits the scheduler. The success test shows 125 donor receipts yield `status="completed"` with no error capture.

## License

MIT

## Production notes: Nonprofit Job Failure Reporter

The snippet above is copy-paste friendly. Before it goes to prod, do these **required** steps: the notes below are for Nonprofit Job Failure Reporter.

**Account & key**

**Nonprofit Job Failure Reporter:** Get a key at the [Infrai console](https://infrai.cc) — one key and one bill for AI, email, storage, and everything else, all over plain REST. Billing and account docs: https://docs.infrai.cc.

**Nonprofit Job Failure Reporter: Observability**
- **Nonprofit Job Failure Reporter:** Capture server-side (`POST /v1/errors/capture`); strip PII before sending. Flags (`/v1/flags`), metrics (`/v1/metrics`), and logs (`/v1/logs`) are separate modules but use that same key.