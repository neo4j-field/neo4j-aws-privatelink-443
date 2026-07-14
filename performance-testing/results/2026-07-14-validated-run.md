# Validated Run — 2026-07-14 (resized instances, c5.4xlarge)

Renders directly on GitHub (no download needed) — the source data is the same run as the interactive dashboard at [`sample-report/index.html`](sample-report/index.html), which has the response-time-over-time graphs if you want those instead.

This run follows an instance resize — every East-region node (the 3-node cluster and the perf-test box) and the Central VPC test client moved from `t2.medium`/burstable to **`c5.4xlarge`** (16 vCPU, dedicated/non-burstable). It uses the same profile as the previous run superseded by this one (warm-up + 2,500 measured requests/path) so the two are directly comparable.

## Setup

| | |
|---|---|
| Target | Single-instance deployment (`approach-3-lts-single-instance`), private IP `10.0.153.25`, **c5.4xlarge** |
| Query | `MATCH (p:PerfTestPerson {id: $id}) RETURN p.id, p.name, p.email, p.city` — indexed point lookup, `id` randomized 1–10000 per request (see [`../queries.md`](../queries.md)) |
| Dataset | 10,000 `:PerfTestPerson` nodes seeded via [`../seed-data.cypher`](../seed-data.cypher) |
| Warm-up | 10 threads × 50 loops = 500 untracked requests per path, immediately before the measured run |
| Load profile | 25 threads, 10s ramp-up, 100 loops/thread = 2,500 measured requests per path (5,000 total measured; 6,000 total requests issued) |
| Tool | JMeter 5.6.3, [`../jmeter/HAProxy-vs-Direct-Neo4j.jmx`](../jmeter/HAProxy-vs-Direct-Neo4j.jmx), run via `-JWARMUP_THREADS=10 -JWARMUP_LOOPS=50 -JTHREADS=25 -JRAMPUP=10 -JLOOPS=100` |

**Methodology note (unchanged from before):** the JMeter client and Neo4j+HAProxy still run on the same EC2 instance here, so this isolates HAProxy's own cost rather than the customer's full PrivateLink path (see [Test topology](../README.md#test-topology)). Unlike the previous (`t2.medium`) run, though, same-box CPU contention is no longer a meaningful confound — `c5.4xlarge` has 16 dedicated vCPUs vs. `t2.medium`'s 2 burstable vCPUs, and the numbers below show it: absolute latency dropped by more than an order of magnitude.

## Results

| Metric | Direct (`:7473`, HAProxy bypassed) | Via HAProxy (`:443`) | Delta |
|---|---:|---:|---:|
| Samples | 2,500 | 2,500 | 0 |
| Errors | 0 (0%) | 0 (0%) | 0 |
| Mean (ms) | 2.51 | 2.64 | +0.13 |
| Median (ms) | 2 | 2 | 0 |
| p90 (ms) | 4 | 4 | 0 |
| p95 (ms) | 5 | 5 | 0 |
| p99 (ms) | 10 | 10 | 0 |
| Min (ms) | 1 | 1 | 0 |
| Max (ms) | 25 | 22 | −3 |
| Throughput (req/s) | 255.5 | 254.9 | −0.6 |
| Received (KB/s) | 77.3 | 77.1 | −0.2 |
| Sent (KB/s) | 98.8 | 97.3 | −1.5 |

![Percentile comparison — Direct vs HAProxy](chart-percentiles.png)

## Response-time distribution

| Bucket | Direct — count (%) | Via HAProxy — count (%) |
|---|---:|---:|
| 0–2ms | 304 (12.2%) | 171 (6.8%) |
| 2–5ms | 2044 (81.8%) | 2173 (86.9%) |
| 5–10ms | 121 (4.8%) | 125 (5.0%) |
| 10–15ms | 24 (1.0%) | 25 (1.0%) |
| 15–20ms | 6 (0.2%) | 4 (0.2%) |
| 20–25ms | 0 (0.0%) | 2 (0.1%) |
| 25–50ms | 1 (0.0%) | 0 (0.0%) |
| >50ms | 0 (0.0%) | 0 (0.0%) |

![Response-time distribution — Direct vs HAProxy](chart-distribution.png)

## Reading this run

On adequately-sized hardware, **HAProxy's overhead disappears into measurement noise.** p50 through p99 are identical between the two paths (2/4/5/10ms each); the only difference at all is a +0.13ms mean and a *lower* max for HAProxy (22ms vs 25ms — noise, not a real advantage). This is the cleanest possible outcome for the question this test exists to answer.

Compare this against the two earlier `t2.medium` runs (both superseded by this one): a [500-sample run](https://github.com/neo4j-field/neo4j-aws-privatelink-443/blob/51f46e3/performance-testing/results/2026-07-14-validated-run.md) and a [2,500-sample run](https://github.com/neo4j-field/neo4j-aws-privatelink-443/blob/d82492c/performance-testing/results/2026-07-14-validated-run.md) at the same profile as this one. Both showed real, growing tail-latency costs for HAProxy (+30ms to +124ms at p99). With the resize, that cost is gone. The likely explanation isn't that HAProxy got faster — it's that on the undersized `t2.medium`, HAProxy's extra CPU work (TLS termination + re-encryption) was competing for scarce, bursty CPU credits alongside Neo4j and the JMeter client itself; on `c5.4xlarge` there's enough dedicated CPU that this contention no longer shows up.

**Practical implication:** HAProxy's own architectural overhead is genuinely negligible on right-sized hardware. If a customer's production instances are sized comparably to (or larger than) `c5.4xlarge`, this result — not the earlier `t2.medium` runs — is the one to present. If a customer is evaluating this architecture on smaller/burstable instance types, the earlier undersized-hardware results are the more relevant caution.

## Verdict

> On `c5.4xlarge` (16 vCPU, non-burstable) with 2,500 samples per path, HAProxy's TLS-bridging hop is statistically indistinguishable from the direct baseline at every percentile measured (p50 through p99 identical; mean delta +0.13ms). HAProxy is a viable solution with no measurable performance cost on adequately-sized hardware. The caveat: this was measured with client and server on the same host, isolating HAProxy's own cost from PrivateLink/cross-VPC network cost — the two are additive for the customer's real path, but that PrivateLink cost is a separate, well-understood network hop, not something HAProxy itself adds.
