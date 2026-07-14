# Validated Run — 2026-07-14

Renders directly on GitHub (no download needed) — the source data is the same run as the interactive dashboard at [`sample-report/index.html`](sample-report/index.html), which has the response-time-over-time graphs if you want those instead.

This run adds a **warm-up phase** (200 untracked requests — 100 per path — via the test plan's `00 - Warm-up` Setup Thread Group) before the measured 500-per-path run, to let JIT compilation, connection establishment, and page cache reach steady state before anything is recorded. Compared to the [previous cold-start run](https://github.com/neo4j-field/neo4j-aws-privatelink-443/blob/f772c37/performance-testing/results/2026-07-13-validated-run.md), every percentile dropped substantially — most of the earlier latency was cold-start cost, not HAProxy or Neo4j.

## Setup

| | |
|---|---|
| Target | Single-instance deployment (`approach-3-lts-single-instance`), private IP `10.0.153.25` |
| Query | `MATCH (p:PerfTestPerson {id: $id}) RETURN p.id, p.name, p.email, p.city` — indexed point lookup, `id` randomized 1–10000 per request (see [`../queries.md`](../queries.md)) |
| Dataset | 10,000 `:PerfTestPerson` nodes seeded via [`../seed-data.cypher`](../seed-data.cypher) |
| Warm-up | 5 threads × 20 loops = 100 untracked requests per path, immediately before the measured run |
| Load profile | 10 threads, 5s ramp-up, 50 loops/thread = 500 measured requests per path (1000 total measured; 1200 total requests issued) |
| Tool | JMeter 5.6.3, [`../jmeter/HAProxy-vs-Direct-Neo4j.jmx`](../jmeter/HAProxy-vs-Direct-Neo4j.jmx) |

## Results

| Metric | Direct (`:7473`, HAProxy bypassed) | Via HAProxy (`:443`) | Delta |
|---|---:|---:|---:|
| Samples | 500 | 500 | 0 |
| Errors | 0 (0%) | 0 (0%) | 0 |
| Mean (ms) | 16.0 | 22.0 | +6.0 |
| Median (ms) | 10.0 | 11.0 | +1.0 |
| p90 (ms) | 23.0 | 26.0 | +3.0 |
| p95 (ms) | 31.0 | 70.7 | **+39.7** |
| p99 (ms) | 143.0 | 267.0 | **+124.0** |
| Min (ms) | 3 | 3 | 0 |
| Max (ms) | 397 | 810 | +413 |
| Throughput (req/s) | 98.3 | 94.7 | −3.6 |
| Received (KB/s) | 29.7 | 28.6 | −1.1 |
| Sent (KB/s) | 38.0 | 36.1 | −1.9 |

## Response-time distribution

| Bucket | Direct — count (%) | Via HAProxy — count (%) |
|---|---:|---:|
| 0–10ms | 210 (42.0%) | 212 (42.4%) |
| 10–25ms | 248 (49.6%) | 229 (45.8%) |
| 25–50ms | 24 (4.8%) | 27 (5.4%) |
| 50–100ms | 8 (1.6%) | 15 (3.0%) |
| 100–200ms | 7 (1.4%) | 10 (2.0%) |
| 200–500ms | 3 (0.6%) | 5 (1.0%) |
| 500–1000ms | 0 (0.0%) | 2 (0.4%) |
| >1000ms | 0 (0.0%) | 0 (0.0%) |

## Reading this run

With warm-up in place, the bulk of the distribution (≥87% of requests either way, under 25ms) is close between the two paths — a few milliseconds, consistent with HAProxy's TLS-bridging hop being CPU cost on loopback, not a network round trip. That part matches the earlier cold-start run's conclusion.

What's different this time: with cold-start noise removed, **HAProxy shows a small but now-consistent tail cost** — p95 and p99 are both meaningfully higher via HAProxy (not just noise in one direction like the previous run), and it's the only path with any samples over 500ms (2 of 500, both landing under 810ms). At 500 samples this is still a modest n for the tail specifically — worth a higher-concurrency re-run (`-JTHREADS=25 -JLOOPS=100` or more) to see whether that p95/p99 gap holds, shrinks, or grows under real load, since that's the number that actually matters for a customer's SLA conversation.

## Verdict (draft)

> With JIT/connection/cache warm-up applied, HAProxy's TLS-bridging hop added ~1-6ms at the median/mean level (noise-level, not customer-noticeable) but a more consistent ~40-124ms at p95/p99 — a real, if still modest, tail-latency cost. Recommend a higher-concurrency re-run before finalizing a number for the customer, since 500 samples is thin for characterizing the tail specifically.
