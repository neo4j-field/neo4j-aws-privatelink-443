# Approach 3 (Cluster Variant) — Neo4j 5.x LTS, 3-Node Cluster, Single Hostname (TLS Bridging)

A 3-node Neo4j 5.26 LTS Enterprise cluster behind HAProxy on port 443 — the cluster sibling of [`approach-3-lts-single-instance`](../approach-3-lts-single-instance/).

The single-instance approach proved that one FQDN + one port can carry **HTTPS, raw Bolt, and Bolt-over-WebSocket** when HAProxy peeks the first decrypted bytes after TLS termination. This directory extends that pattern to a clustered deployment.

## What changes vs. approach-3 single-instance

| | Single-instance (approach-3) | This (cluster variant) |
|---|---|---|
| Topology | One Neo4j host | Three Neo4j hosts (A, B, C across 3 AZs) |
| HAProxy placement | Co-located with the only Neo4j | Co-located with each Neo4j (per-node, identical config) |
| Cross-node distribution | N/A | NLB (port 443) in front of all 3 HAProxy instances |
| Bolt advertised address | `lts.neo4jfield.org:443` | `privatelink.neo4jfield.org:443` on every node |
| HTTPS advertised address | `lts.neo4jfield.org:443` | `privatelink.neo4jfield.org:443` on every node |
| Cluster discovery | N/A | V2_ONLY, LIST, private IPs `10.0.x.x:6000` |

Each node's HAProxy fronts only its **local** Neo4j on `127.0.0.1:7687` and `127.0.0.1:7473`. The NLB performs cross-node TCP load balancing on port 443; AWS PrivateLink exposes the NLB to the consumer VPC.

## What stays the same as approach-3 single-instance

- Outer HAProxy frontend on `:443` with `bind … ssl crt … alpn http/1.1`, mode `tcp`
- Bolt magic detection: `req.payload(0,4) -m bin "6060B017"` → raw Bolt backend (TCP, re-encrypted to local `127.0.0.1:7687`)
- Inner HTTP frontend on `127.0.0.1:8444` with `accept-proxy`, splitting WSS-Bolt (`Upgrade: websocket`) from plain HTTPS by header
- TLS-bridging (HAProxy terminates client TLS, re-encrypts to Neo4j on loopback) — no plaintext crosses any network interface
- `server.bolt.tls_level=REQUIRED`, `server.https.enabled=true`, `server.http.enabled=false`

## Why single hostname, even in a cluster

The Neo4j Browser SPA loads from `https://privatelink.neo4jfield.org/browser/` and then opens `wss://privatelink.neo4jfield.org/`. With a single origin, the WSS handshake reuses the cert-validation cache primed by the HTTPS load — eliminating the 60–120 s "No routing servers available" cold-start that occurs when Browser is on one FQDN and Bolt is on another (because Let's Encrypt no longer publishes OCSP URLs, browsers fall back to a slow CRL/CT round-trip on cross-origin first-connect).

In a cluster, all three nodes advertising the same `privatelink.neo4jfield.org:443` collapses the driver-side routing table to one logical endpoint. Cross-node distribution moves entirely to the NLB; Neo4j's server-side routing (`dbms.routing.enabled=true`) forwards writes from a follower to the leader transparently.

## Trade-offs to know before adopting

- **Driver-side load balancing is gone.** All three routing-table entries resolve to the same FQDN. The NLB does the spreading. Acceptable in most setups; if you need driver-aware leader pinning, prefer Approach 1 (per-node DNS via SNI passthrough).
- **HAProxy holds the private key on the same host as Neo4j.** Plaintext exists only in HAProxy's process memory between the decrypt-from-client and re-encrypt-to-loopback steps. If your threat model forbids any TLS terminator inside the data path, use Approach 1.
- **Each HAProxy fronts only its local Neo4j.** Failure of HAProxy on a node takes that node out of rotation at the NLB level — which is correct behavior, since the NLB health-check should mark it unhealthy.

## Files

| File | Purpose |
|---|---|
| `haproxy.cfg` | Identical HAProxy config installed on every cluster node — outer TLS-terminate + Bolt-magic detection, inner mode-http for HTTPS / WSS split. |
| `node-a/neo4j.conf` | Node A (us-east-1a). Cluster discovery via private IPs; bolt + https advertised on `privatelink.neo4jfield.org:443`. |
| `node-b/neo4j.conf` | Node B (us-east-1b). |
| `node-c/neo4j.conf` | Node C (us-east-1c). |
| `prompts/` | Design intent and rollout decisions — see `prompts/README.md`. |

## Deploy outline (per node)

```bash
# 1. Place cert (key + chain in one PEM, mode 0600 owned by haproxy)
sudo install -o haproxy -g haproxy -m 0600 your-bundle.pem /etc/haproxy/certs/neo4jfield.org.pem

# 2. Install HAProxy config (identical on all 3 nodes)
sudo install -o root -g root -m 0644 haproxy.cfg /etc/haproxy/haproxy.cfg
sudo haproxy -c -f /etc/haproxy/haproxy.cfg     # validate

# 3. Install per-node Neo4j config
sudo install -o neo4j -g neo4j -m 0640 node-a/neo4j.conf /etc/neo4j/neo4j.conf

# 4. SELinux: allow haproxy to connect to non-default backend ports
sudo setsebool -P haproxy_connect_any on

# 5. firewalld
sudo firewall-cmd --permanent --add-service=ssh
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload

# 6. Apply
sudo systemctl reload haproxy
sudo systemctl restart neo4j
```

Roll one node at a time; the cluster keeps quorum (2 of 3) during each restart.

## Verification

From any cluster node:

```bash
# TLS termination + cert presented for SNI
echo | openssl s_client -connect 127.0.0.1:443 \
    -servername privatelink.neo4jfield.org -alpn http/1.1 2>/dev/null \
  | grep -E 'subject=|issuer=|Verify return code'

# HTTPS path → Neo4j Browser SPA root
curl -sk -o /dev/null -w 'HTTP %{http_code}\n' \
  --resolve privatelink.neo4jfield.org:443:127.0.0.1 \
  https://privatelink.neo4jfield.org/

# Bolt magic split → expect a 4-byte version handshake response
printf '\x60\x60\xb0\x17\x00\x00\x00\x05\x00\x00\x00\x04\x00\x00\x00\x03\x00\x00\x00\x02' \
  | timeout 5 openssl s_client -connect 127.0.0.1:443 \
      -servername privatelink.neo4jfield.org -quiet 2>/dev/null \
  | xxd | head -1
```

Expected Bolt probe response begins `00 00 00 05` (Bolt protocol version 5).

## Trust boundary note

HAProxy and Neo4j run on the same EC2 host. Plaintext exists only in HAProxy's process memory between the decrypt-from-client and re-encrypt-to-loopback steps; no plaintext traverses any network interface. The private key lives at `/etc/haproxy/certs/neo4jfield.org.pem` (mode 0600, owner `haproxy`).

If a customer requires "no intermediate sees plaintext," use Approach 1 (pure SNI passthrough) and accept the cross-origin cold-start glitch — or move to a single-port, single-protocol architecture.
