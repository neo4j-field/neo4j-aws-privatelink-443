# Validated Run — 2026-07-13

Renders directly on GitHub (no download needed) — the source data is the same run as the interactive dashboard at [`sample-report/index.html`](sample-report/index.html), which has the response-time-over-time graphs if you want those instead.

## Setup

| | |
|---|---|
| Target | Single-instance deployment (`approach-3-lts-single-instance`), private IP `10.0.153.25` |
| Query | `MATCH (p:PerfTestPerson {id: $id}) RETURN p.id, p.name, p.email, p.city` — indexed point lookup, `id` randomized 1–10000 per request (see [`../queries.md`](../queries.md)) |
| Dataset | 10,000 `:PerfTestPerson` nodes seeded via [`../seed-data.cypher`](../seed-data.cypher) |
| Load profile | 10 threads, 5s ramp-up, 50 loops/thread = 500 requests per path (1000 total) |
| Tool | JMeter 5.6.3, [`../jmeter/HAProxy-vs-Direct-Neo4j.jmx`](../jmeter/HAProxy-vs-Direct-Neo4j.jmx) |

## Results

| Metric | Direct (`:7473`, HAProxy bypassed) | Via HAProxy (`:443`) | Delta |
|---|---:|---:|---:|
| Samples | 500 | 500 | 0 |
| Errors | 0 (0%) | 0 (0%) | 0 |
| Mean (ms) | 58.0 | 60.5 | +2.5 |
| Median (ms) | 33.0 | 31.0 | −2.0 |
| p90 (ms) | 118.6 | 115.8 | −2.8 |
| p95 (ms) | 223.6 | 198.6 | −25.0 |
| p99 (ms) | 515.0 | 797.4 | **+282.4** |
| Min (ms) | 4 | 4 | 0 |
| Max (ms) | 838 | 1064 | +226 |
| Throughput (req/s) | 70.9 | 66.2 | −4.7 |
| Received (KB/s) | 21.5 | 20.0 | −1.5 |
| Sent (KB/s) | 27.4 | 25.3 | −2.1 |

## Response-time distribution

Where the p99 gap actually comes from — a handful of slow outliers, not a systemic shift:

| Bucket | Direct — count (%) | Via HAProxy — count (%) |
|---|---:|---:|
| 0–25ms | 171 (34.2%) | 197 (39.4%) |
| 25–50ms | 196 (39.2%) | 155 (31.0%) |
| 50–100ms | 74 (14.8%) | 91 (18.2%) |
| 100–200ms | 30 (6.0%) | 33 (6.6%) |
| 200–500ms | 23 (4.6%) | 15 (3.0%) |
| 500–1000ms | 6 (1.2%) | 7 (1.4%) |
| >1000ms | 0 (0%) | 2 (0.4%) |

The bulk of the distribution (0–200ms, ~94% of requests either way) tracks closely between the two paths — that's the real HAProxy cost, and it's noise-level. The p99 gap comes from 2 outliers over 1000ms on the HAProxy path that don't have a match on the direct path. At n=500 that's not enough to call a systemic effect yet; it's exactly the kind of thing a higher-concurrency, larger-n re-run (`-JTHREADS=25 -JLOOPS=100` or more) would either confirm as a real tail-latency cost or wash out as noise.

## Verdict (draft)

> Across 500 samples per path at 10 concurrent threads, HAProxy's TLS-bridging hop added no measurable overhead at the median/p90/p95 level (within ±3–25ms, noise for this sample size). The p99 tail was higher via HAProxy (797ms vs 515ms), driven by 2 outlier requests — worth a larger re-run before treating as a real cost, but not disqualifying on its own.
