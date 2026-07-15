# Validated Run: 2026-07-15 (Bolt, cross-region)

First validated run of the Bolt variant of this test: real Bolt protocol, direct public-internet vs. PrivateLink + HAProxy, client genuinely in a different region from the cluster.

## Setup

| | |
|---|---|
| Direct target | Node A, `3.235.109.212` (us-east-1a), Bolt `:7687`, public internet, HAProxy bypassed |
| Via-HAProxy target | `privatelink.neo4jfield.org:443`, existing PrivateLink connection, HAProxy demuxes on the Bolt magic bytes to loopback `:7687` |
| Test client | `neo4j-nes-server-1`, **ca-central-1** (Central VPC), `c5.4xlarge` |
| Query | `MATCH (p:PerfTestPerson {id: $id}) RETURN p.id AS id, p.name AS name, p.email AS email, p.city AS city`, indexed point lookup, `id` randomized 1 to 10000 per request |
| Dataset | 10,000 `:PerfTestPerson` nodes seeded via [`../seed-data.cypher`](../seed-data.cypher) |
| Warm-up | 5 threads x 20 loops = 100 untracked requests per path, immediately before the measured run |
| Load profile | 10 threads, 5s ramp-up, 50 loops/thread = 500 measured requests per path (1,000 total measured) |
| Tool | JMeter 5.6.3 + `neo4j-java-driver` 5.26.0 via JSR223 Sampler, [`../jmeter/Bolt-HAProxy-vs-Direct.jmx`](../jmeter/Bolt-HAProxy-vs-Direct.jmx), run with defaults |

**Methodology note:** unlike the [HTTP variant's validated run](2026-07-14-validated-run.md), the client here genuinely sits in a different AWS region (ca-central-1) from the cluster (us-east-1), and the Direct path leaves the AWS network entirely over the public internet rather than staying on the same box or the same VPC. This measures the real customer choice (expose Bolt directly to the internet vs. go through PrivateLink + HAProxy), not HAProxy's isolated cost. See [the README's note on isolating variables](../README.md#a-note-on-isolating-variables) for what a same-VPC run would isolate instead.

## Results

| Metric | Direct (Bolt `:7687`, public internet) | Via HAProxy (Bolt over `:443`, PrivateLink) | Delta |
|---|---:|---:|---:|
| Samples | 500 | 500 | 0 |
| Errors | 0 (0%) | 0 (0%) | 0 |
| Mean (ms) | 30.6 | 35.6 | +5.0 |
| Median (ms) | 30.0 | 36.0 | +6.0 |
| p90 (ms) | 33.0 | 37.0 | +4.0 |
| p95 (ms) | 34.0 | 37.0 | +3.0 |
| p99 (ms) | 34.0 | 39.0 | +5.0 |
| Min (ms) | 28.0 | 34.0 | +6.0 |
| Max (ms) | 37.0 | 39.0 | +2.0 |
| Throughput (req/s) | 83.3 | 80.1 | −3.2 |

## Reading this run

The direct public-internet path was consistently faster than PrivateLink + HAProxy, by a tight margin (3 to 6ms) that holds steady from the minimum through p99. That shape, a uniform shift rather than a blown-out tail, points to a fixed per-request cost rather than network jitter: the PrivateLink + HAProxy path pays for an extra TLS handshake at HAProxy plus a loopback re-encrypt to Neo4j's Bolt port, on top of whatever the PrivateLink hop itself costs. The direct path pays neither.

This is a different result from the [HTTP variant's `c5.4xlarge` run](2026-07-14-validated-run.md), which found HAProxy's overhead statistically indistinguishable from direct. The difference isn't necessarily protocol (Bolt vs HTTP), it's topology: that run isolated HAProxy's cost by keeping both paths on the same box. This run instead compares two different network paths end to end (public internet vs PrivateLink), so the delta here includes more than HAProxy alone.

**Practical implication:** if the question is "does HAProxy itself add meaningful latency," the [HTTP same-box run](2026-07-14-validated-run.md) is the more direct answer (no), and a same-VPC Bolt run would give the equivalent answer for Bolt specifically. If the question is "should we expose Bolt directly to the internet instead of using PrivateLink," this run says the two are close (single-digit milliseconds apart at this concurrency), which likely won't be the deciding factor versus PrivateLink's security posture (no public exposure, no `0.0.0.0/0` security group rule to maintain).

## Verdict

> Across 500 samples per path at 10 concurrent threads, from a genuinely cross-region client (ca-central-1 to us-east-1), the direct public-internet Bolt path averaged 30.6ms versus 35.6ms via PrivateLink + HAProxy, a delta of 5.0ms (+16%), with a p99 delta of 5.0ms. Error rate was 0% on both paths. Direct was consistently faster by a small, uniform margin, consistent with the added TLS-terminate-and-loopback-reencrypt hop at HAProxy rather than network jitter. This is a single run at modest concurrency (10 threads); re-run at higher concurrency (25+ threads, matching the HTTP variant's validated profile) before treating ~5ms as a stable number to quote to a customer, and treat the `0.0.0.0/0` security group rule used for the Direct path here as a test-only configuration to close afterward, not a recommended production posture.
