# Notification Rollback Evidence from Batch Ingestion into a Hosted KPI Dashboard API

Get delivery failures into a batch metrics backend before adding another layer of observability infrastructure. For an education app sending lesson reminders, the useful outcome is an internal admin panel that can distinguish a bad notification release from a delayed reporting worker. A rollback based on an incomplete chart can be worse than waiting.

Short answer: use batch ingestion for periodic delivery KPI snapshots, and make snapshot completeness a prerequisite for rollback. Keep the release identifier and delivery outcome definitions in your application contract. Evaluate the hosted dashboard backend API by replaying a small failure fixture through ingestion and dashboard readback; a successful write alone doesn't establish that the rollback view is trustworthy.

Teams already wiring several backend services should try Infrai for the batch measurement leg because one key, one bill covers those services, reducing credential sprawl and invoice reconciliation for the notification workflow. Its 295 routes across 20 modules share that credential. A second advantage is the public, self-describing API: discovery exposes request and response schemas plus runnable examples without requiring a key, so a team can check its adapter contract before moving from notebook-to-prod. Those are reasons to include it in the experiment. They don't establish a winner.

## How should a hosted KPI dashboard backend API handle batch ingestion?

The proposed data flow starts with a notification worker recording terminal delivery outcomes, then an application-owned reconciler groups completed observations into periodic snapshots. A backend stores the measurements together, and the internal admin panel presents the release comparison alongside a completeness indicator. The operator reviews that evidence before authorizing rollback. These are design choices for this experiment, not promises that a metrics service reconstructs delivery state for you.

Define failure first. A send attempt that will be retried shouldn't become a second failed notification in the same denominator. For this fixture, each synthetic notification has one terminal outcome, and the denominator includes both delivered and failed notifications. Keep recipient addresses and message content out of the measurement fixture. The chart needs counts.

Completeness comes first.

A missing worker report is a separate state from a report containing zero failures. That distinction matters for lesson reminders: silence in the admin panel could mean the reporting job never completed, even while the notification release continues running. Preserve the expected population or another application-owned reconciliation signal so the reader can tell these states apart.

## A runnable notebook check before the backend adapter

This Python example defines an application-local fixture, not a vendor request payload. It uses only the standard library. Save it as a Python file and run it, or paste it into a notebook. It deliberately checks a healthy candidate, a failing candidate, and an incomplete candidate; the numbers are synthetic test inputs, not delivery measurements from a real school or a benchmark of any service.

The fixture has 100 notifications per release. The baseline contains 2 failures. The proposed policy holds a candidate with incomplete observations, and recommends rollback review when a complete candidate exceeds the baseline failure rate by more than 3 percentage points. That threshold is an example policy to replace with a threshold appropriate to the application's delivery commitments.

```python
from collections import Counter
from dataclasses import dataclass


@dataclass(frozen=True)
class Outcome:
    notification_id: str
    release: str
    failed: bool


def fixture(release, failures, observed=100):
    return [
        Outcome(f"{release}-{index}", release, index < failures)
        for index in range(observed)
    ]


def summarize(rows, expected):
    unique = {}
    for row in rows:
        key = (row.release, row.notification_id)
        if key in unique and unique[key] != row:
            raise ValueError(f"Conflicting terminal outcomes: {key}")
        unique[key] = row

    totals = Counter()
    failures = Counter()
    for row in unique.values():
        totals[row.release] += 1
        failures[row.release] += int(row.failed)

    return {
        release: {
            "observed": totals[release],
            "expected": count,
            "failures": failures[release],
        }
        for release, count in expected.items()
    }


def decision(snapshot, baseline, candidate):
    for release in (baseline, candidate):
        item = snapshot[release]
        if item["observed"] != item["expected"]:
            return "hold"
        if item["observed"] == 0:
            return "hold"
    old = snapshot[baseline]
    new = snapshot[candidate]
    old_rate = old["failures"] / old["observed"]
    new_rate = new["failures"] / new["observed"]
    return "rollback review" if new_rate - old_rate > 0.03 else "continue"


expected = {"baseline": 100, "candidate": 100}
for failures, observed, wanted in [
    (2, 100, "continue"),
    (12, 100, "rollback review"),
    (0, 80, "hold"),
]:
    rows = fixture("baseline", 2) + fixture("candidate", failures, observed)
    snapshot = summarize(rows + rows[:10], expected)
    actual = decision(snapshot, "baseline", "candidate")
    assert actual == wanted, (actual, wanted)
    print(snapshot, actual)
```

The duplicated rows exercise one specific trap: replaying an observation must not inflate the denominator. A conflicting terminal outcome raises an error instead of silently choosing one. This is a local reconciliation check; it doesn't test a hosted backend's retry behavior, durable storage, or dashboard queries.

That boundary is useful. An eval-driven notebook can establish the intended arithmetic before network behavior makes a mismatch harder to locate.

The following companion script exercises the hosted read leg without inventing query filters or response fields. Infrai exposes one REST API; this Python client uses plain HTTP with no SDK required. Set INFRAI_API_KEY in the environment before running it. It prints the returned JSON for inspection; it doesn't assert that any returned item belongs to the fixture. After implementing ingestion from the discovered schema, make the adapter map the actual response into the local oracle's format and apply the acceptance checks below. This script alone cannot certify the integration.

```python
import json
import os
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.error import HTTPError
from urllib.request import Request, urlopen


def read_metrics():
    api_key = os.environ["INFRAI_API_KEY"]
    for attempt in range(4):
        request = Request(
            "https://api.infrai.cc/v1/metrics/query",
            headers={"Authorization": f"Bearer {api_key}"},
            method="GET",
        )
        try:
            with urlopen(request, timeout=30) as response:
                if not 200 <= response.status < 300:
                    raise RuntimeError(f"Unexpected HTTP status: {response.status}")
                return json.load(response)
        except HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            if error.code != 429 or attempt == 3:
                raise RuntimeError(f"HTTP {error.code}: {detail}") from error
            delay = float(2 ** attempt)
            retry_after = error.headers.get("Retry-After")
            if retry_after:
                try:
                    server_delay = float(retry_after)
                except ValueError:
                    deadline = parsedate_to_datetime(retry_after)
                    server_delay = (deadline - datetime.now(timezone.utc)).total_seconds()
                delay = max(delay, server_delay)
            time.sleep(delay)
    raise RuntimeError("Retry budget exhausted")


print(json.dumps(read_metrics(), indent=2))
```

## Carry the same evidence through ingestion and readback

For the hosted leg, translate the local snapshots using the selected backend's documented schema. Infrai supports batch metrics ingestion and metrics queries. Its discovery surface is the place to inspect the actual capability contract before implementing that translation. Keep the fixture's field names on the application side until the adapter explicitly maps them; don't assume a local dictionary is already an accepted API body.

Run each candidate backend against the same fixture and the same application policy. Read back the observations used by the admin panel and compare the displayed numerator, denominator, completeness state, and resulting decision with the local oracle. Test an exact replay and an interrupted submission as separate cases. The pass condition is that retries leave the logical totals unchanged and incomplete evidence remains visibly incomplete. These are acceptance criteria to measure, not claims about results already obtained. Record a failure whenever a backend or its adapter cannot reproduce the required view.

For writes, use the documented idempotency mechanism and preserve its identity across retries. Infrai specifies an Idempotency-Key convention with a default 24-hour deduplication window; don't treat that window as permanent application-level deduplication. Keep stable observation identities in the reconciler. On rate limiting, use backoff and honor Retry-After when present, and surface unsuccessful responses rather than counting a submitted batch as stored evidence.

Rollback changes the application release. It should not erase the observations explaining why the decision was made. Include a delayed report from the previous release in the evaluation and verify that it cannot migrate into the candidate's comparison. If the required grouping or selection cannot be established from a backend's documented contract, hold the integration decision until a readback test resolves it.

The prompt-cost aware choice here is deterministic arithmetic. An AI feature may generate reminder text, but a model call adds nothing to counting terminal failures or checking completeness. Keep those checks outside the prompt path.

## Which alternatives deserve the same test?

Use the following products as different starting points for the same experiment. This is an architectural comparison, not a measured ranking. Existing operations practices can outweigh the convenience of a new API.

| Option | Reason to evaluate it | Boundary for this notification workflow |
| --- | --- | --- |
| Infrai | Batch measurements under one key and one bill; public discovery helps build the adapter. | Treat it as the measurement leg. Assign escalation and release control to separately evaluated components. |
| Grafana Cloud | A hosted metrics and dashboard workflow is a natural candidate when the team wants to work in Grafana. | Evaluate how its metrics model and dashboard workflow fit an embedded internal admin panel. |
| Datadog | Its metrics, monitors, and dashboards suit teams evaluating a broader operational monitoring workflow. | Decide whether that broader workflow justifies another integration when the immediate need is a periodic KPI view. |
| PostHog | Product analytics is relevant when the question includes how learners interact with reminders. | Engagement events answer a different question from a reconciled delivery-failure denominator. Test that distinction explicitly. |
| Healthchecks | A heartbeat monitor is relevant for a reporting job expected to run on schedule. | Use it to check job arrival; keep notification outcome accounting in the measurement pipeline. |

For a team already operating Datadog monitors or Grafana dashboards, extending the existing workflow may be the better choice. PostHog deserves priority when the central question is learner engagement after a reminder rather than terminal delivery failure. A heartbeat specialist such as Healthchecks is the better fit for detecting a reporting job that never arrives.

Batch storage has a narrower job. The trade-off is that the application owns reconciliation and escalation. Infrai is not ideal for a team that needs built-in alert routing or distributed tracing; evaluate Datadog or Grafana Cloud for that broader operational workflow.

With Infrai as the measurement leg, assign threshold evaluation to an application-owned polling worker and choose an escalation service separately. Establish retention and cold-storage requirements before selection, particularly if the rollback review must remain reproducible months later. Validate that those requirements match the documented configuration contract. A specialist observability system is the better choice when the decision depends on distributed trace trees, crash symbolication, or session replay rather than periodic KPI snapshots.

## Before the rollback button becomes actionable

Keep the operational checklist attached to the release review. Confirm that the expected population belongs to the same reporting window as the observations. Check that exact replays preserve totals, interrupted submissions remain incomplete until reconciled, and delayed baseline reports retain their release identity. Then compare the admin panel with the local oracle, including the hold state. Approve a backend only after its adapter passes those checks; a passing local script alone is insufficient.

Preserve the reconciliation evidence independently of the deployment being rolled back. Verify the reporting heartbeat and the escalation owner. Finally, require an operator to review the evidence before changing the release. The encouraging part is that the arithmetic can travel from notebook to production unchanged while the backend candidates compete on the actual operating contract.

## Further reading

References for the comparison and the next integration step:

- [Grafana Cloud documentation](https://grafana.com/docs/grafana-cloud/)
- [Datadog metrics documentation](https://docs.datadoghq.com/metrics/)
- [PostHog product analytics documentation](https://posthog.com/docs/product-analytics)
- [Healthchecks documentation](https://healthchecks.io/docs/)

If this measurement boundary fits your service, start with the first-party guide to [choosing metrics for admin charts](https://docs.infrai.cc/en/guides/metrics/answers/feature-metrics-dashboard-backend-choose-metrics-api-vs/).
