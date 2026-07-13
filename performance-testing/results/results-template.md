# Results — HAProxy vs Direct

Fill in after running the JMeter Aggregate Report (or Newman summary) for both paths against the same target, back-to-back, on the same network.

**Test date:** _____
**Target:** _____ (hostname/IP)
**Cypher statement used:** `RETURN 1 AS ok` (or: _____)
**Concurrency / iterations:** _____ threads, _____ loops (or Newman `-n` count)

| Metric | Direct (HAProxy bypassed, :7473) | Via HAProxy (:443) | Delta | Delta % |
|---|---|---|---|---|
| Samples | | | | |
| Error % | | | | |
| Average (ms) | | | | |
| Median (ms) | | | | |
| p90 (ms) | | | | |
| p95 (ms) | | | | |
| p99 (ms) | | | | |
| Min (ms) | | | | |
| Max (ms) | | | | |
| Throughput (req/sec) | | | | |

## How to interpret

- **Delta is the added cost of the TLS-terminate → re-encrypt → forward hop at HAProxy.** For a `RETURN 1` query, that delta is *only* transport overhead — no query-execution time is in the mix, so it isolates exactly what HAProxy costs.
- A few milliseconds of added average/median latency is typical and rarely noticeable to an application — HAProxy's TLS bridging happens on loopback (`127.0.0.1`), not over the network, so the added hop is CPU/context-switch cost, not a physical network round trip.
- Watch **p99 and max**, not just the average — if the tail blows out under concurrency while the average looks fine, that usually points to HAProxy `maxconn`/thread tuning or the instance running low on CPU, not to the architecture itself.
- **Error % must match (usually 0%) on both paths.** If HAProxy shows errors the direct path doesn't, that's a correctness problem to fix before drawing any conclusion about performance.
- Throughput (req/sec) should be comparable between the two paths at the same concurrency. A large throughput gap is a stronger signal than a small latency delta.

## Verdict template

> Across N samples at C concurrent threads, HAProxy added an average of **X ms** (Y%) of latency versus a direct connection to Neo4j, with p99 delta of **Z ms**. Error rate was 0% on both paths. This overhead is [negligible / acceptable / a concern] for [customer's stated use case].
