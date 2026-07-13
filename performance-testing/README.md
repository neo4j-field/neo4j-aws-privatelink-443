# Performance Testing — HAProxy vs Direct

Test scripts a customer can run themselves to answer one question: **how much latency does HAProxy add?**

Both tools here hit the same endpoint — Neo4j's [HTTP Query API v2](https://neo4j.com/docs/query-api/current/) (`POST /db/{database}/query/v2`) — once **via HAProxy on port 443** (the real client path in Approach 1 and Approach 3) and once **directly against Neo4j's native HTTPS port `7473`, with HAProxy bypassed** (the baseline). Same query, same client, same network — the only variable is whether HAProxy sits in the path. Whatever difference shows up in the results *is* HAProxy's cost.

This works unchanged whichever config variant is deployed ([`approach-1-haproxy`](../config/approach-1-haproxy/), [`approach-3-lts-single-instance`](../config/approach-3-lts-single-instance/), or [`approach-3-lts-cluster-tls-bridging`](../config/approach-3-lts-cluster-tls-bridging/)) — all of them front the same Neo4j HTTPS port `7473` with HAProxy on `443`.

> **Approach 2 (NES, no HAProxy) is out of scope here.** NES is Bolt-only with no HTTP surface, so it isn't reachable with JMeter/Postman's HTTP samplers — a fair comparison against NES needs a Bolt driver script (see [`examples/`](../examples/)), not an HTTP tool.

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

1. **Neo4j reachable on two paths from the test client:**
   - Via HAProxy: `https://<host>:443` (the normal client path)
   - Direct: `https://<host>:7473` — Neo4j's native HTTPS port, bypassing HAProxy entirely

   By design, this architecture only exposes `443` publicly — `7473` isn't meant to be reachable from outside. To get a real baseline without permanently weakening the security posture, pick **one**:

   - **SSH tunnel (recommended default)** — no security group changes at all:
     ```bash
     ssh -i <your-key>.pem -L 7473:localhost:7473 ec2-user@<node-public-ip>
     # then point the "direct" target at localhost:7473
     ```
     Best for correctness and for light/serial testing. Under heavy concurrency the tunnel itself adds a small amount of overhead, which slightly understates HAProxy's relative advantage — fine for a go/no-go read, but say so if reporting exact numbers back to the customer.
   - **Temporary security group rule** — add an inbound rule on the Neo4j EC2 instance(s) for `tcp/7473`, scoped to the test runner's specific IP only (never `0.0.0.0/0`), run the test, then remove the rule. More accurate for load testing at real concurrency since there's no extra tunnel hop.

2. **Neo4j credentials** with permission to run a read query (the test uses `RETURN 1 AS ok` by default — no schema or data access required).
3. **JMeter 5.5+** (for the `__base64Encode` function used in the Authorization header) and/or **Newman** (`npm install -g newman`) / Postman desktop app.
4. The current public IP or hostname of the target node. Public IPs on these EC2 instances **change on restart** — confirm the current one before each test run.

---

## Option A — JMeter

**File:** [`jmeter/HAProxy-vs-Direct-Neo4j.jmx`](jmeter/HAProxy-vs-Direct-Neo4j.jmx)

Two Thread Groups, each independently configurable, each writing its own `.jtl` results file:

| Thread Group | Target | Output |
|---|---|---|
| `01 - Baseline (Direct to Neo4j, HAProxy bypassed)` | `${DIRECT_HOST}:${DIRECT_PORT}` (default `localhost:7473` — set up the SSH tunnel above, or point at the node directly if using the SG method) | `results-direct.jtl` |
| `02 - Via HAProxy (port 443)` | `${VIA_HAPROXY_HOST}:${VIA_HAPROXY_PORT}` (default `3.83.100.223:443` — update to the current public IP or the PrivateLink hostname) | `results-haproxy.jtl` |

### Setup

1. Install JMeter: https://jmeter.apache.org/download_jmeter.cgi (or `brew install jmeter`).
2. Open `HAProxy-vs-Direct-Neo4j.jmx` in the JMeter GUI, or edit variables directly in the XML's "User Defined Variables" — either way, set:
   - `VIA_HAPROXY_HOST` / `VIA_HAPROXY_PORT` — the HAProxy path (usually just needs the current public IP / hostname)
   - `DIRECT_HOST` / `DIRECT_PORT` — the baseline path (`localhost:7473` if tunneling)
   - `NEO4J_USER` / `NEO4J_PASSWORD`
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
  -JVIA_HAPROXY_HOST=3.83.100.223 -JVIA_HAPROXY_PORT=443 \
  -JDIRECT_HOST=localhost -JDIRECT_PORT=7473 \
  -JNEO4J_PASSWORD='<password>' \
  -JTHREADS=25 -JRAMPUP=10 -JLOOPS=100 \
  -l results.jtl -e -o report/
```

---

## Option B — Postman / Newman

**Files:** [`postman/Neo4j-HAProxy-vs-Direct.postman_collection.json`](postman/Neo4j-HAProxy-vs-Direct.postman_collection.json), [`postman/via-haproxy.postman_environment.json`](postman/via-haproxy.postman_environment.json), [`postman/direct-baseline.postman_environment.json`](postman/direct-baseline.postman_environment.json)

One collection, one request — the two environments swap `baseUrl` between the HAProxy path (`:443`) and the direct baseline (`:7473`). Edit `baseUrl`, `neo4jUser`, and `neo4jPassword` in each environment file (or in the Postman UI) before running.

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

The JMeter plan above was run end-to-end against a live single-instance deployment (10 threads, 5s ramp-up, 50 loops = 500 requests per path, both paths hitting `localhost` on the same host so the only variable is the HAProxy hop itself):

| Metric | Direct (`:7473`) | Via HAProxy (`:443`) | Delta |
|---|---|---|---|
| Samples | 500 | 500 | 0 |
| Error % | 0% | 0% | 0 |
| Mean (ms) | 93.2 | 88.4 | -4.8 |
| Median (ms) | 73 | 69 | -4 |
| p90 (ms) | 172 | 169 | -3 |
| p95 (ms) | 234 | 248 | +14 |
| p99 (ms) | 470 | 394 | -76 |
| Throughput (req/s) | 59.8 | 60.4 | +0.7 |

HAProxy's TLS-bridging hop added **no measurable overhead** here — the deltas are within run-to-run noise (HAProxy even came out faster on several percentiles, which is just variance at this sample size, not a real advantage). Expected: HAProxy terminates and re-encrypts on loopback, not over the network, so its cost is a few CPU cycles per request, not a network round trip.

## Related

- [`docs/01-architecture.md`](../docs/01-architecture.md) — overall PrivateLink/HAProxy architecture
- [`docs/04-comparison.md`](../docs/04-comparison.md) — Approach 1 vs Approach 2 trade-offs
- [`examples/`](../examples/) — Python Bolt-driver demos (useful if a Bolt-level, not HTTP-level, comparison is ever needed)
