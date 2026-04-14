# Secure Neo4j Access Over Port 443: PrivateLink, HAProxy, and NLB

This repository provides a production-tested, step-by-step guide for exposing a **3-node Neo4j 5.x Enterprise cluster** across AWS VPCs using **AWS PrivateLink**, all traffic over **port 443 only**.

Two approaches are documented:

| | Approach 1: HAProxy + NLB + PrivateLink | Approach 2: NES (No HAProxy) + PrivateLink|
|---|---|---|
| Access | HTTPS (Browser) + Bolt | Bolt only (via NES) |
| HAProxy | Installed on each cluster node | Not needed |
| Client tooling | Any browser or driver | Neo4j Enterprise Studio (EAP) |
| Port | 443 for all traffic (https & bolt+s) | 443 for Bolt only |

---

## Architecture Diagram

![Neo4j AWS PrivateLink Architecture — Provider VPC (us-east-1) with 3-node cluster exposed via PrivateLink to Consumer VPC (ca-central-1)](screenshots/neo4j_aws_privatelink_architecture.png)

---

## Architecture at a Glance

```
Consumer VPC (client)
  └── App / NES / Browser
       └── DNS: privatelink.example.com → Interface Endpoint ENI
            └── AWS PrivateLink
                 └── Network Load Balancer (port 443)
                      └── HAProxy (Approach 1) or direct Neo4j Bolt (Approach 2)
                           └── Neo4j Cluster (3 nodes, 3 AZs)
```

```
Provider VPC (us-east-1)
  ├── Neo4j Node A (us-east-1a) — HAProxy + Neo4j
  ├── Neo4j Node B (us-east-1b) — HAProxy + Neo4j
  └── Neo4j Node C (us-east-1c) — HAProxy + Neo4j
```

---

## Table of Contents

1. [Architecture Details](docs/01-architecture.md)
2. [Approach 1 — HAProxy + NLB + PrivateLink](docs/02-approach-haproxy.md)
3. [Approach 2 — NES (Neo4j Enterprise Studio, no HAProxy)](docs/03-approach-nes.md)
4. [Comparison: Pros and Cons](docs/04-comparison.md)

---

## Sample Configuration Files

```
config/
├── approach-1-haproxy/
│   ├── node-a/
│   │   ├── neo4j.conf       # Node A (us-east-1a) — HAProxy approach
│   │   └── haproxy.cfg      # HAProxy config for Node A
│   ├── node-b/
│   │   ├── neo4j.conf       # Node B (us-east-1b) — HAProxy approach
│   │   └── haproxy.cfg      # HAProxy config for Node B
│   └── node-c/
│       ├── neo4j.conf       # Node C (us-east-1c) — HAProxy approach
│       └── haproxy.cfg      # HAProxy config for Node C
└── approach-2-nes/
    ├── node-a/
    │   └── neo4j.conf       # Node A — NES approach (bolt advertised on :443)
    ├── node-b/
    │   └── neo4j.conf       # Node B — NES approach
    └── node-c/
        └── neo4j.conf       # Node C — NES approach
```

> **Note:** Provider VPC node IPs (`10.0.x.x`) are illustrative examples — substitute your own IP ranges. Consumer VPC ENI IPs and hostnames reflect an actual deployment. No credentials, private keys, or certificates are included.

---

## Quick Reference: DNS Resolution by VPC

Two separate **Private Hosted Zones (PHZs)** implement split-horizon DNS — each VPC resolves the same hostnames to different IPs.

- **Provider VPC PHZ** (us-east-1) — associated with the Provider VPC only. Resolves hostnames to Neo4j node private IPs (`10.0.x.x`) for intra-cluster communication.
- **Consumer VPC PHZ** (ca-central-1) — associated with the Consumer VPC. Resolves hostnames to PrivateLink Interface Endpoint ENI IPs (`192.168.x.x`).

> **Important:** The Provider PHZ must **not** be associated with the Consumer VPC. If it were, Consumer VPC clients would resolve `east-*.neo4jfield.org` to the `10.0.x.x` node IPs directly — which are unreachable from the Consumer VPC — bypassing PrivateLink entirely.

| Hostname | Provider VPC PHZ (us-east-1) | Consumer VPC PHZ (ca-central-1) |
|---|---|---|
| `privatelink.neo4jfield.org` | `10.0.5.82` (HAProxy on Node A) | — |
| `east-a.neo4jfield.org` | `10.0.5.82` (Node A) | `192.168.2.74`, `192.168.3.26` |
| `east-b.neo4jfield.org` | `10.0.26.126` (Node B) | `192.168.2.74`, `192.168.3.26` |
| `east-c.neo4jfield.org` | `10.0.47.163` (Node C) | `192.168.2.74`, `192.168.3.26` |
| `studio.neo4jfield.org` | — | `192.168.1.43` |
| `bolt-noproxy.neo4jfield.org` | — | `3.82.20.139` |

> In the Consumer VPC, all `east-*.neo4jfield.org` hostnames resolve to the **same PrivateLink endpoint ENI IPs**. Per-node routing (to Node A, B, or C) is handled by **HAProxy via SNI inspection** on port 443 (Approach 1 only).

---

## Port Reference: Approach 1 — HAProxy + NLB + PrivateLink

| Port | Protocol | Component | Direction |
|---|---|---|---|
| 443 | TCP/TLS | HAProxy frontend | Consumer → NLB → HAProxy |
| 7473 | TCP/TLS | Neo4j HTTPS (Browser) | HAProxy → Neo4j (internal) |
| 7687 | TCP/TLS | Neo4j Bolt | HAProxy → Neo4j (internal) |

---

## Port Reference: Approach 2 — NES (No HAProxy) + PrivateLink

| Port | Protocol | Component | Direction |
|---|---|---|---|
| 443 | TCP/TLS | Neo4j Bolt (via NES) | Consumer → NLB → Neo4j |

---

## Port Reference: Internal Cluster Communication

| Port | Protocol | Component | Direction |
|---|---|---|---|
| 7688 | TCP | Neo4j Bolt Routing (intra-cluster) | Node → Node |
| 6000 | TCP | Cluster discovery (V2) | Node → Node |
| 7000 | TCP | RAFT consensus | Node → Node |

---

## Prerequisites

- AWS account with VPC admin permissions
- Neo4j Enterprise 5.x license (tested with 5.26)
- A registered domain (e.g. `neo4jfield.org`) with ability to add DNS records
- A wildcard or SAN TLS certificate and key for `*.your-domain.com`
- EC2 key pair for SSH access
- Neo4j installed on 3 EC2 instances (Amazon Linux 2023 recommended)

---

## Related Resources

- [Neo4j Operations Manual — Clustering](https://neo4j.com/docs/operations-manual/current/clustering/)
- [Neo4j Operations Manual — SSL/TLS](https://neo4j.com/docs/operations-manual/current/security/ssl-framework/)
- [AWS PrivateLink Documentation](https://docs.aws.amazon.com/vpc/latest/privatelink/)
- [HAProxy Documentation](https://www.haproxy.org/#docs)
