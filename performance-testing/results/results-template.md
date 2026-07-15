# Results: Bolt HAProxy vs Direct

Fill in after running the JMeter Aggregate Report for both paths, back-to-back.

**Test date:** _____
**Direct target:** _____ (East node public IP : 7687)
**Via-HAProxy target:** privatelink.neo4jfield.org : 443 (PrivateLink, ca-central-1 → us-east-1)
**Test client:** _____ (Central VPC)
**Cypher statement used:** `MATCH (p:PerfTestPerson {id: $id}) RETURN p.id AS id, p.name AS name, p.email AS email, p.city AS city` (or: _____)
**Concurrency / iterations:** _____ threads, _____ loops

| Metric | Direct (Bolt 7687, public internet) | Via HAProxy (Bolt over 443, PrivateLink) | Delta | Delta % |
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

- **This delta is not HAProxy's cost alone.** It bundles HAProxy's TLS-terminate/demux/forward hop and the difference between raw public-internet routing and the PrivateLink/AWS backbone. The direct path leaves the AWS network entirely and comes back in over the internet, while the HAProxy path never leaves AWS's backbone. A large delta could come from either source, so don't attribute all of it to HAProxy. To isolate HAProxy alone, re-run both `DIRECT_HOST` and `VIA_HAPROXY_HOST` against a test client inside the East VPC instead.
- Watch **p99 and max**, not just the average. Internet-path variance (ISP routing, jitter) tends to show up in the tail first.
- **Error % must match (usually 0%) on both paths.** A gap here is a correctness/connectivity problem, not a performance finding, so check it before drawing any latency conclusion.
- Throughput (req/sec) should be comparable at the same concurrency. A large gap is a stronger signal than a small latency delta.
- If the Direct path requires opening `7687` to `0.0.0.0/0` on the East node Security Group, confirm that's still true (or re-scope it) before re-running, and close it back down afterward.

## Verdict template

> Across N samples at C concurrent threads, the direct public-internet Bolt path averaged **X ms**, versus **Y ms** via PrivateLink + HAProxy, a delta of **Z ms** (W%), with a p99 delta of **P ms**. Error rate was 0% on both paths. [Direct was faster / HAProxy+PrivateLink was faster / statistically indistinguishable], consistent with [transport overhead being dominated by internet routing variance / HAProxy's loopback hop / neither].
