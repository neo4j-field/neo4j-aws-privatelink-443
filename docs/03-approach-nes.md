# Approach 2 — Neo4j Enterprise Studio (NES), No HAProxy

## Overview

**Neo4j Enterprise Studio (NES)** is a unified client application — currently in Early Access Program (EAP), soon to be Generally Available — that combines:

- **Neo4j Browser** — query interface and result visualization
- **Bloom** — graph exploration and visualization
- **Dashboards** — BI-style charts and panels built on graph data

NES is installed **inside the Consumer VPC** (on an EC2 instance, container, or desktop client). It connects to Neo4j exclusively via the **Bolt protocol** over **port 443**, which means:

- No HAProxy required in the Provider VPC
- No HTTPS (port 7473) endpoint needed from the consumer side
- Fewer NLBs and PrivateLink endpoint services to manage
- Simpler architecture

---

## How Port 443 Bolt Works Without HAProxy

In Approach 1, HAProxy multiplexes both HTTPS and Bolt over port 443 using SNI. In Approach 2, there is no multiplexing — port 443 carries **Bolt traffic only**.

The key mechanism is **NLB port mapping**:

```
Consumer → port 443 → Interface Endpoint → PrivateLink → NLB (listener :443)
                                                                   ↓
                                                         Target group port :7687
                                                                   ↓
                                                         Neo4j Bolt on EC2 :7687
```

The NLB's listener is on TCP port 443, but the target group forwards to Neo4j's Bolt port 7687. This lets consumers connect on port 443 while Neo4j continues listening on its standard port internally.

Neo4j's `server.bolt.advertised_address` is set to port 443 so that the routing table returned to NES contains `:443` addresses — which is what consumers will actually connect to via PrivateLink.

---

## Part 1 — Neo4j Configuration

### 1.1 Install and Certificate Setup

Same as Approach 1 — see [Approach 1, Parts 1.1 and 1.2](02-approach-haproxy.md#11-install-neo4j-enterprise-on-each-node).

### 1.2 Configure neo4j.conf

Copy the appropriate sample configuration:

| Node | Sample config |
|---|---|
| Node A (us-east-1a) | [`config/approach-2-nes/node-a/neo4j.conf`](../config/approach-2-nes/node-a/neo4j.conf) |
| Node B (us-east-1b) | [`config/approach-2-nes/node-b/neo4j.conf`](../config/approach-2-nes/node-b/neo4j.conf) |
| Node C (us-east-1c) | [`config/approach-2-nes/node-c/neo4j.conf`](../config/approach-2-nes/node-c/neo4j.conf) |

**Key difference from Approach 1:**

| Setting | Approach 1 | Approach 2 (NES) |
|---|---|---|
| `server.bolt.advertised_address` | `east-a.neo4jfield.org:7687` | `east-a.neo4jfield.org:443` |
| `server.https.advertised_address` | `privatelink.neo4jfield.org:7473` | `east-a.neo4jfield.org:7473` (internal) |
| HAProxy | Required | Not needed |
| NLB port mapping | Not needed (direct pass-through) | Listener :443 → Target :7687 |

> **Why advertise bolt on :443?** When a Neo4j driver (or NES) connects and calls the routing procedure, Neo4j returns a routing table listing all cluster members with their bolt addresses. If those addresses use port 7687 but consumers can only reach them on port 443 (via PrivateLink), the driver will fail to connect to the per-node addresses. Setting `server.bolt.advertised_address` to port 443 ensures the routing table matches what consumers can actually reach.

### 1.3 Start the Cluster

```bash
sudo neo4j start
sudo neo4j status
```

Verify cluster:
```cypher
SHOW SERVERS
```

---

## Part 2 — AWS Network Load Balancers (Approach 2)

You need **3 NLBs**, one per Neo4j node — but with **port mapping** (listener 443 → target 7687):

| NLB Name | AZ | Target IP | Listener Port | Target Port |
|---|---|---|---|---|
| `nlb-neo4j-bolt-a` | us-east-1a | `10.0.5.82` | **443** | **7687** |
| `nlb-neo4j-bolt-b` | us-east-1b | `10.0.26.126` | **443** | **7687** |
| `nlb-neo4j-bolt-c` | us-east-1c | `10.0.47.163` | **443** | **7687** |

> **Note the difference:** In Approach 1, the Bolt NLBs use listener 7687 → target 7687 (no port mapping). In Approach 2, the listener is 443 → target 7687, because consumers connect on port 443.

**Health check:** TCP port 7687 (the actual Neo4j Bolt port, not 443, since 443 is only the listener).

---

## Part 3 — AWS PrivateLink Endpoint Services (Approach 2)

Create **3 endpoint services** (one per NLB) — no HTTPS service needed:

| Service Name | NLB | Private DNS Name | Purpose |
|---|---|---|---|
| `svc-neo4j-bolt-a` | `nlb-neo4j-bolt-a` | `east-a.neo4jfield.org` | Node A Bolt on 443 |
| `svc-neo4j-bolt-b` | `nlb-neo4j-bolt-b` | `east-b.neo4jfield.org` | Node B Bolt on 443 |
| `svc-neo4j-bolt-c` | `nlb-neo4j-bolt-c` | `east-c.neo4jfield.org` | Node C Bolt on 443 |

Domain verification and allow-principals setup is the same as Approach 1 — see [Approach 1, Part 4.3 and 4.4](02-approach-haproxy.md#43-verify-the-private-dns-name).

---

## Part 4 — Route 53 Private Hosted Zone (Provider VPC)

Same PHZ records as Approach 1 — the cluster nodes still need to resolve each other's hostnames within the Provider VPC.

| Record | Type | Value |
|---|---|---|
| `east-a.neo4jfield.org` | A | `10.0.5.82` |
| `east-b.neo4jfield.org` | A | `10.0.26.126` |
| `east-c.neo4jfield.org` | A | `10.0.47.163` |

> No `privatelink.neo4jfield.org` record needed in Approach 2 (no shared HAProxy entry point).

**Critical:** Associate this PHZ **only with the Provider VPC** — never with the Consumer VPC.

---

## Part 5 — Consumer VPC: Interface Endpoints

Create **3 Interface Endpoints** (one per endpoint service):

| Endpoint | Service | Private DNS | Port |
|---|---|---|---|
| `ep-neo4j-bolt-a` | `svc-neo4j-bolt-a` | `east-a.neo4jfield.org` | 443 |
| `ep-neo4j-bolt-b` | `svc-neo4j-bolt-b` | `east-b.neo4jfield.org` | 443 |
| `ep-neo4j-bolt-c` | `svc-neo4j-bolt-c` | `east-c.neo4jfield.org` | 443 |

For each endpoint:
- Enable private DNS name: **Yes**
- Subnets: **at least 2 subnets in different AZs** (for high availability — see [Approach 1 explanation](02-approach-haproxy.md#61-create-interface-endpoints))
- Security group: allow TCP 443 inbound from the NES host / app CIDR

Accept the endpoint connections on the provider side if acceptance is required.

---

## Part 6 — Install NES in the Consumer VPC

> **EAP Notice:** Neo4j Enterprise Studio (NES) is currently in Early Access Program. Contact your Neo4j account team for access and installation packages.

NES can be installed as:
- A desktop application (Windows/macOS)
- A containerized service within the Consumer VPC (recommended for shared team access)

### 6.1 Connect NES to the Cluster

Once installed, configure NES to connect to the Neo4j cluster:

- **Connection URL:** `neo4j+s://east-a.neo4jfield.org:443`
- **Username:** `neo4j`
- **Password:** `<your password>`

NES will perform the initial Bolt handshake on port 443, retrieve the routing table (which also lists port 443 addresses for all nodes), and then connect to individual nodes as needed.

### 6.2 What NES Provides

| Feature | Description |
|---|---|
| **Query Interface** | Cypher editor with result table and graph views |
| **Bloom** | Graph exploration and pattern-based visualization |
| **Dashboards** | Build BI-style charts and panels from Cypher queries |
| **Multi-database** | Browse and query across all databases in the cluster |

### 6.3 Verify Connectivity

From the NES host in the Consumer VPC:

```bash
# Test that port 443 reaches each node via PrivateLink
nc -zv east-a.neo4jfield.org 443
nc -zv east-b.neo4jfield.org 443
nc -zv east-c.neo4jfield.org 443
```

After NES connects, run in the query interface:

```cypher
SHOW SERVERS
```
Expected: 3 servers, all `Enabled` and `Available`.

---

## Part 7 — Troubleshooting

### NES cannot connect on port 443

1. Verify Interface Endpoints are in `available` state (not `pending acceptance`)
2. Check security groups — the endpoint ENI must allow TCP 443 from the NES host
3. Verify DNS resolves to ENI IPs (not Provider VPC private IPs):
   ```bash
   dig east-a.neo4jfield.org
   # Should return an ENI IP like 192.168.x.x, not 10.0.x.x
   ```

### Driver routing table uses wrong port

**Symptom:** After initial connection, the driver fails to connect to individual nodes

**Cause:** `server.bolt.advertised_address` is set to `:7687` (Approach 1 config) instead of `:443` (Approach 2 config)

**Fix:** Update each node's `neo4j.conf`:
```properties
# Node A
server.bolt.advertised_address=east-a.neo4jfield.org:443
# Node B
server.bolt.advertised_address=east-b.neo4jfield.org:443
# Node C
server.bolt.advertised_address=east-c.neo4jfield.org:443
```
Then restart: `sudo neo4j restart`
