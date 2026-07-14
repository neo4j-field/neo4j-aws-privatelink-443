# Performance Testing — HAProxy vs Direct

Test scripts a customer can run themselves to answer one question: **how much latency does HAProxy add?**

Both tools here hit the same endpoint — Neo4j's [HTTP Query API v2](https://neo4j.com/docs/query-api/current/) (`POST /db/{database}/query/v2`) — once **via HAProxy on port 443** (the real client path in Approach 1 and Approach 3) and once **directly against Neo4j's native HTTPS port `7473`, with HAProxy bypassed** (the baseline). Same query, same client, same network — the only variable is whether HAProxy sits in the path. Whatever difference shows up in the results *is* HAProxy's cost.

This works unchanged whichever config variant is deployed ([`approach-1-haproxy`](../config/approach-1-haproxy/), [`approach-3-lts-single-instance`](../config/approach-3-lts-single-instance/), or [`approach-3-lts-cluster-tls-bridging`](../config/approach-3-lts-cluster-tls-bridging/)) — all of them front the same Neo4j HTTPS port `7473` with HAProxy on `443`.

> **Approach 2 (NES, no HAProxy) is out of scope here.** NES is Bolt-only with no HTTP surface, so it isn't reachable with JMeter/Postman's HTTP samplers — a fair comparison against NES needs a Bolt driver script (see [`examples/`](../examples/)), not an HTTP tool.

> **Bolt also works on 443 in Approaches 1 and 3 — this test doesn't cover that path.** HAProxy demuxes by peeking the first few bytes after TLS termination: Bolt's magic handshake (`60 60 B0 17`) routes to the Bolt backend, anything else routes to HTTPS — so a `bolt+s://` or `neo4j+s://` driver connecting on port 443 from the Central VPC works transparently, same port, same HAProxy. JMeter/Postman's HTTP samplers can't drive that path (no HTTP request is involved); it's already validated in [`examples/neo4j_privatelink_demo.py`](../examples/neo4j_privatelink_demo.py). If you want a JMeter-style load comparison for Bolt specifically, that needs a driver-based load generator (e.g. a small Python/Java script spinning up N sessions), not JMeter/Postman — ask if that's wanted and it can be added alongside this.

---

## Test data

Both tools default to a real indexed point lookup against a small synthetic dataset, not `RETURN 1`. Seed it once before running either tool:

```bash
cypher-shell -a bolt+ssc://<host>:7687 -u neo4j -p '<password>' -f seed-data.cypher
```

This creates 10,000 `:PerfTestPerson` nodes (unique-constrained on `id`, grouped into 20 synthetic cities with a `FOLLOWS` ring per city) — see [`seed-data.cypher`](seed-data.cypher). The default query in both tools is:

```cypher
MATCH (p:PerfTestPerson {id: $id}) RETURN p.id AS id, p.name AS name, p.email AS email, p.city AS city
```

with `id` randomized per request (1–10000) so load spreads across the dataset instead of hammering one page-cached node. Two heavier alternatives (a non-indexed filtered scan, and a 1-hop relationship traversal) are in [`queries.md`](queries.md) if you want the comparison under more realistic query cost.

---

## Tool choice

| | **JMeter** (recommended primary) | **Postman / Newman** (quick check) |
|---|---|---|
| Best for | Concurrent load, percentile latency (p90/p95/p99), throughput | Fast sanity check, no install if the customer already has Postman |
| Output | Aggregate Report / HTML Dashboard with full percentile breakdown | CLI summary with average/min/max response time |
| Setup effort | Install JMeter (Java-based) | Install Newman (`npm install -g newman`), or use Postman desktop app directly |
| Why | Purpose-built for exactly this: N concurrent virtual users, statistically meaningful latency distribution under load | Easiest to hand to someone non-technical, or to run once from a laptop with zero setup if they already have Postman |

**Use JMeter for the number that goes in front of a customer** (percentiles under realistic concurrency). Use Postman/Newman if you just want a fast "is this even in the right ballpark" check, or if the customer's team is more comfortable in Postman than JMeter.

---

## Prerequisites

1. **A test-runner host with the right tools installed.** [`setup-test-runner.sh`](setup-test-runner.sh) installs Java, Node.js/npm, Newman, and JMeter 5.6.3 on a fresh RHEL/Amazon Linux host — run it on whatever machine will actually issue the requests (a bastion in the same VPC as Neo4j, or the customer's own workstation for Postman).

2. **Neo4j reachable on two paths from that test-runner host:**
   - Via HAProxy: `https://<host>:443` (the normal client path)
   - Direct: `https://<host>:7473` — Neo4j's native HTTPS port, bypassing HAProxy entirely

   **If the test runner is inside the same VPC as Neo4j** (e.g. another EC2 instance, or JMeter running on the Neo4j box itself), the private IP works for both paths with no security group changes at all — that's the default in both tool configs here (`10.0.153.25`, this deployment's current private IP; update to whatever yours is). This is the recommended setup: it's a real path through the NIC (not a `localhost`-only loopback shortcut) without touching a security group.

   **If the test runner is outside the VPC** (customer's laptop, a box in a different VPC without a private route), `7473` isn't reachable by design — only `443` is meant to be exposed. To still get a fair "HAProxy bypassed" baseline, pick one:
   - **SSH tunnel** — `ssh -i <key>.pem -L 7473:localhost:7473 ec2-user@<node-public-ip>`, then point the "direct" target at `localhost:7473`. No security group changes, but the tunnel itself adds a small amount of overhead under heavy concurrency.
   - **Temporary security group rule** — inbound `tcp/7473` scoped to the test runner's specific IP only (never `0.0.0.0/0`), removed after the test. More accurate at real concurrency since there's no tunnel hop.

3. **Test data seeded** (see [Test data](#test-data) above) and **Neo4j credentials** with read access to it.
4. The current IP/hostname of the target node — public IPs on these EC2 instances **change on restart**, confirm before each run.

---

## Option A — JMeter

**File:** [`jmeter/HAProxy-vs-Direct-Neo4j.jmx`](jmeter/HAProxy-vs-Direct-Neo4j.jmx)

Two Thread Groups, each independently configurable, each writing its own `.jtl` results file:

| Thread Group | Target | Output |
|---|---|---|
| `01 - Baseline (Direct to Neo4j, HAProxy bypassed)` | `${DIRECT_HOST}:${DIRECT_PORT}` (default `10.0.153.25:7473` — this deployment's private IP; substitute yours, or `localhost` if tunneling from outside the VPC) | `results-direct.jtl` |
| `02 - Via HAProxy (port 443)` | `${VIA_HAPROXY_HOST}:${VIA_HAPROXY_PORT}` (default `10.0.153.25:443` — substitute the current private IP, public IP, or PrivateLink hostname depending on where the test runner sits) | `results-haproxy.jtl` |

Auth is handled by a native JMeter **HTTP Authorization Manager** (not a hand-built header), so it works out of the box with any JMeter 5.x — no special function support required.

### Setup

1. Run [`setup-test-runner.sh`](setup-test-runner.sh), or install JMeter yourself: https://jmeter.apache.org/download_jmeter.cgi (`brew install jmeter` on macOS).
2. Seed the test data (see [Test data](#test-data)).
3. Open `HAProxy-vs-Direct-Neo4j.jmx` in the JMeter GUI, or edit variables directly in the XML's "User Defined Variables" — either way, set:
   - `VIA_HAPROXY_HOST` / `VIA_HAPROXY_PORT` — the HAProxy path
   - `DIRECT_HOST` / `DIRECT_PORT` — the baseline path
   - `NEO4J_USER` / `NEO4J_PASSWORD`
   - `SEED_MAX_ID` — must match however many `:PerfTestPerson` rows `seed-data.cypher` created (default 10000)
   - `THREADS` / `RAMPUP` / `LOOPS` — concurrency profile (defaults: 10 threads, 5s ramp-up, 50 loops each = 500 requests per path)

### Run

GUI (for a first look / debugging):
```bash
jmeter -t jmeter/HAProxy-vs-Direct-Neo4j.jmx
```

Non-GUI with an HTML dashboard report (what to actually hand a customer):
```bash
cd performance-testing/jmeter
jmeter -n -t HAProxy-vs-Direct-Neo4j.jmx -l results.jtl -e -o report/
open report/index.html   # macOS; xdg-open on Linux
```

The dashboard's **Statistics** table gives min/max/average/p90/p95/p99 and throughput per Thread Group — read the `01 - Baseline` row against the `02 - Via HAProxy` row directly.

### Override variables from the command line (no GUI editing needed)

```bash
jmeter -n -t HAProxy-vs-Direct-Neo4j.jmx \
  -JVIA_HAPROXY_HOST=10.0.153.25 -JVIA_HAPROXY_PORT=443 \
  -JDIRECT_HOST=10.0.153.25 -JDIRECT_PORT=7473 \
  -JNEO4J_PASSWORD='<password>' \
  -JTHREADS=25 -JRAMPUP=10 -JLOOPS=100 \
  -l results.jtl -e -o report/
```

All variables (including `CYPHER_STATEMENT` and `SEED_MAX_ID`) are wired through `${__P(name,default)}`, so every `-JNAME=value` above genuinely overrides the default — confirmed by running with `-JTHREADS=3 -JLOOPS=5` and checking the actual request count matched (30, not the default 1000).

---

## Option B — Postman / Newman

**Files:** [`postman/Neo4j-HAProxy-vs-Direct.postman_collection.json`](postman/Neo4j-HAProxy-vs-Direct.postman_collection.json), [`postman/via-haproxy.postman_environment.json`](postman/via-haproxy.postman_environment.json), [`postman/direct-baseline.postman_environment.json`](postman/direct-baseline.postman_environment.json)

One collection, one request — the two environments swap `baseUrl` between the HAProxy path (`:443`) and the direct baseline (`:7473`). Edit `baseUrl`, `neo4jUser`, `neo4jPassword`, and `seedMaxId` in each environment file (or in the Postman UI) before running. A pre-request script randomizes `id` (1–`seedMaxId`) on every call so, like the JMeter plan, it spreads reads across the seeded dataset instead of hitting one cached row.

### Quick check in the Postman app

1. Import the collection and both environment files.
2. Select the **direct-baseline** environment, open the request, hit **Send** a few times, note the response time shown in the Postman UI.
3. Switch to the **via-haproxy** environment, repeat.
4. For something more statistically meaningful, use the **Collection Runner** with 50–100 iterations against each environment and compare the average response time it reports.

### At the command line with Newman (repeatable, scriptable)

```bash
npm install -g newman
cd performance-testing/postman

newman run Neo4j-HAProxy-vs-Direct.postman_collection.json \
  -e direct-baseline.postman_environment.json -n 50

newman run Neo4j-HAProxy-vs-Direct.postman_collection.json \
  -e via-haproxy.postman_environment.json -n 50
```

Or run both back-to-back and see the comparison directly:
```bash
./run-comparison.sh 50
```

---

## Recording and presenting results

Use [`results/results-template.md`](results/results-template.md) to record the two runs side by side (direct vs via-HAProxy) and fill in the delta. It includes a short guide on what the numbers actually mean — worth reading before sending anything to a customer, since the headline number they'll ask about is p99, not the average.

### Validated example run

The JMeter plan was run end-to-end against a live single-instance deployment with the real dataset seeded (10 threads, 5s ramp-up, 50 loops = 500 requests per path, both paths hitting the instance's private IP so the only variable is the HAProxy hop itself) — actual indexed point lookups against `:PerfTestPerson`, not `RETURN 1`:

| Metric | Direct (`:7473`) | Via HAProxy (`:443`) | Delta |
|---|---|---|---|
| Samples | 500 | 500 | 0 |
| Error % | 0% | 0% | 0 |
| Mean (ms) | 58.0 | 60.5 | +2.5 |
| Median (ms) | 33 | 31 | -2 |
| p90 (ms) | 118.6 | 115.8 | -2.8 |
| p95 (ms) | 223.6 | 198.6 | -25 |
| p99 (ms) | 515.0 | 797.4 | +282.4 |
| Throughput (req/s) | 70.9 | 66.2 | -4.7 |

The full interactive HTML dashboard from this run is checked in at [`results/sample-report/index.html`](results/sample-report/index.html) — open it directly for the response-time graphs, per-percentile breakdown, and error table.

Mean/median/p90 are within noise, same as the `RETURN 1` run. The one number worth flagging: **p99 is meaningfully higher via HAProxy in this run** (797ms vs 515ms). At only 500 samples that's ~5 slow requests driving the whole delta, so it's not yet a confident signal — either way, this is exactly the kind of result the note in [`results/results-template.md`](results/results-template.md) warns about: watch p99, don't stop at the average, and don't treat one 500-sample run at 10 threads as conclusive. Re-run at higher concurrency (`-JTHREADS=25 -JLOOPS=100` or more) before drawing a real conclusion for a customer.

## Related

- [`seed-data.cypher`](seed-data.cypher) — creates the `:PerfTestPerson` test dataset both tools query against
- [`queries.md`](queries.md) — the default point-lookup query plus two heavier alternatives (filtered scan, 1-hop traversal)
- [`setup-test-runner.sh`](setup-test-runner.sh) — installs Java/Node/Newman/JMeter on a fresh test-runner host
- [`results/sample-report/index.html`](results/sample-report/index.html) — full HTML dashboard from the validated example run above
- [`docs/01-architecture.md`](../docs/01-architecture.md) — overall PrivateLink/HAProxy architecture
- [`docs/04-comparison.md`](../docs/04-comparison.md) — Approach 1 vs Approach 2 trade-offs
- [`examples/`](../examples/) — Python Bolt-driver demos (useful if a Bolt-level, not HTTP-level, comparison is ever needed)
