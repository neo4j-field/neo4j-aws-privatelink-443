# Comparison: Approach 1 (HAProxy) vs Approach 2 (NES)

## Side-by-Side Summary

| | Approach 1 — HAProxy + NLB | Approach 2 — NES (No HAProxy) |
|---|---|---|
| **Client tool** | Any browser (Neo4j Browser) + any Bolt driver | Neo4j Enterprise Studio (NES) |
| **Access methods** | HTTPS (Browser) + Bolt | Bolt only |
| **HAProxy** | Required on Nodes A and B | Not required |
| **Number of NLBs** | 4 (1 HTTPS + 3 Bolt) | 3 (Bolt-only, with port mapping) |
| **Number of PrivateLink services** | 4 | 3 |
| **Port exposed to consumer** | 443 (all traffic) | 443 (Bolt only) |
| **Neo4j bolt advertised port** | 7687 | 443 |
| **NLB port mapping** | No (7687→7687) | Yes (443→7687) |
| **NES availability** | Not required | Required (EAP, soon GA) |
| **Operational complexity** | Higher (HAProxy process to manage) | Lower (no additional proxy) |
| **TLS termination** | HAProxy terminates, re-encrypts to Neo4j | NLB pass-through, Neo4j terminates |
| **Certificate placement** | Neo4j nodes + HAProxy `/etc/haproxy/certs/` | Neo4j nodes only |

---

## Approach 1 — HAProxy: Pros and Cons

### Pros

- **Full browser access:** Neo4j Browser (HTTPS on port 443) works out of the box for any user with a web browser — no special client software needed
- **Any Bolt driver:** Standard Neo4j drivers (Python, Java, JavaScript, .NET, Go) connect without modification
- **Mature tooling:** HAProxy is production-proven, widely understood, and has extensive documentation
- **SNI flexibility:** Additional backends (custom apps, monitoring dashboards) can be added to HAProxy with additional ACL rules — all on port 443
- **GA today:** No EAP access required — all components are production-ready

### Cons

- **Additional process:** HAProxy must be running and healthy on each node that fronts traffic; adds to the operational surface
- **Certificate in two places:** TLS certificate must be deployed both to Neo4j (`/var/lib/neo4j/certificates/`) and to HAProxy (`/etc/haproxy/certs/` as a `.pem` bundle) — certificate rotation involves two steps
- **Double TLS hop:** HAProxy terminates TLS from the client and re-opens a TLS connection to Neo4j (`ssl verify none`). While safe when co-located, this is an additional encryption/decryption step
- **4 NLBs:** Higher AWS cost (NLB pricing is per-hour per AZ) and more configuration to maintain
- **HAProxy version drift:** Must ensure HAProxy supports `ssl_fc_sni` (HAProxy 1.6+) and is kept patched

---

## Approach 2 — NES: Pros and Cons

### Pros

- **Simpler architecture:** No HAProxy process — fewer moving parts, fewer failure modes
- **Certificate in one place:** TLS is managed entirely by Neo4j; no HAProxy PEM bundle to maintain
- **NLB port mapping:** Clean and efficient — NLB handles 443→7687 translation natively without any application-level proxy
- **Richer client:** NES provides Bloom visualization and BI dashboards out of the box, beyond what Neo4j Browser offers
- **Fewer AWS resources:** 3 NLBs + 3 PrivateLink services instead of 4 each
- **Lower latency:** One less TLS termination hop in the data path

### Cons

- **NES is EAP (as of 2026):** Not yet GA — requires early access enrollment via Neo4j account team; production use should be evaluated against EAP terms
- **No web browser access:** Consumers cannot use the standard Neo4j Browser over HTTPS; NES must be installed in the consumer environment
- **Bolt-only:** Any tooling that uses the HTTPS API (e.g. custom health checks on `/db/neo4j/`) cannot use the PrivateLink endpoint — it only serves Bolt
- **Port 443 conflicts on Neo4j host:** If anything else needs to run on port 443 on the Neo4j EC2 instances (e.g. HAProxy for other services, Nginx), there is a port conflict since Neo4j itself now advertises on 443 (via NLB mapping)
- **NES requires deployment in consumer VPC:** Adds an installation and maintenance step on the consumer side

---

## Decision Guide

**Choose Approach 1 (HAProxy) if:**
- Consumers need Neo4j Browser access from a standard web browser
- You use standard Bolt drivers in application code (not NES)
- You want a production-ready, GA setup with no EAP dependencies
- You need to expose additional custom services on port 443 alongside Neo4j

**Choose Approach 2 (NES) if:**
- Consumers are willing to install NES in their environment
- You want to reduce infrastructure complexity (fewer NLBs, no HAProxy)
- You need the richer NES features (Bloom, dashboards) without a separate Bloom license deployment
- You are comfortable with EAP software and can engage with Neo4j's EAP program

---

## Cost Comparison (Indicative)

| Component | Approach 1 | Approach 2 |
|---|---|---|
| NLBs (per AZ-hour) | 4 NLBs | 3 NLBs |
| PrivateLink endpoint services | 4 | 3 |
| EC2 (HAProxy overhead) | Negligible (co-located, < 1% CPU at low load) | None |
| NES licensing | N/A | Check with Neo4j account team |

The AWS cost difference between 3 and 4 NLBs is small. The dominant cost driver in either approach is the Neo4j Enterprise license and the EC2 instances.
