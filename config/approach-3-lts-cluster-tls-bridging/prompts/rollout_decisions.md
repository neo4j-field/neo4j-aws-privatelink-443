# Rollout Decisions

Decisions made during the cluster rollout (2026-05-07 / 2026-05-08). Documenting the *why* so future operators know which choices were intentional.

## 1. Each HAProxy fronts only its local Neo4j (no cross-node Bolt SNI routing)

In the prior SNI-passthrough config, each node's HAProxy held backends for *all three* nodes' Bolt ports (`east-a` → 10.0.5.82:7687, `east-b` → 10.0.26.126:7687, `east-c` → 10.0.47.163:7687). With single-FQDN TLS bridging, that is no longer needed: the NLB picks a node, that node's HAProxy decrypts and forwards to its own `127.0.0.1:7687`. Cross-node distribution is the NLB's job.

This simplifies the per-node config (no per-node bolt backend table to maintain) and matches the deployment pattern of approach-3 single-instance.

## 2. `server.default_advertised_address` left as `east-{a,b,c}.neo4jfield.org`

Considered and rejected: also flipping `default_advertised_address` to `privatelink.neo4jfield.org`. Reasoning to leave it alone:

- It's a fallback used only for connectors that don't have explicit `*.advertised_address` overrides. Both `bolt` and `https` have explicit overrides, so `default_advertised_address` is never reaching clients.
- `cluster.advertised_address`, `cluster.raft.advertised_address`, and `routing.advertised_address` are also explicitly set to private IPs.
- Changing it adds zero functional benefit and a non-zero risk of touching internal cluster routing in a way we'd discover only on the next rolling restart.

If someone later wants a tidier config with no east-* references at all, that's a follow-up — not a hard requirement.

## 3. Rollout strategy: A → B → C in sequence, no per-node validation

The cluster keeps quorum (2 of 3) during a single-node restart. Sequential rollout (rather than parallel) preserves quorum at every step. Per-node validation (cypher-shell + curl) was deemed unnecessary because:

- HAProxy `-c -f` validates the new config syntactically before reload.
- `systemctl reload haproxy` is non-disruptive — failed reload leaves the old process running.
- `systemctl restart neo4j` is the only disruptive step, and a failed restart only affects the node being touched (cluster keeps serving on the other two).

Backups of the pre-change configs are stamped with the rollout timestamp at:
- `/etc/haproxy/haproxy.cfg.bak.YYYYMMDD-HHMMSS`
- `/etc/neo4j/neo4j.conf.bak.YYYYMMDD-HHMMSS`

Rollback is `cp` from the timestamped backup + `systemctl reload haproxy && systemctl restart neo4j`.

## 4. SELinux: `setsebool -P haproxy_connect_any on`

The new HAProxy config introduces an inner frontend bound to `127.0.0.1:8444` and a PROXY-protocol handoff between frontends. The reference (approach-3 single-instance) README recommends this boolean to allow HAProxy to connect to non-default backend ports. Set defensively on all 3 nodes — no AVC denials observed, but this future-proofs the config against SELinux policy tightening.

## 5. Cert reuse: `/etc/haproxy/certs/neo4jfield.org.pem`

The reference config example in approach-3 single-instance uses a synthesized `combined.pem` (private key + fullchain). On these cluster nodes, `/etc/haproxy/certs/neo4jfield.org.pem` already contains the same content (private key + 2-cert chain) and is the file the prior SNI-passthrough config referenced. Reusing it avoids a cert-rotation step.

The cert is a wildcard `*.neo4jfield.org` issued by Let's Encrypt — covers `privatelink.neo4jfield.org` directly. Verified at rollout time:

```
subject=CN=neo4jfield.org
issuer=C=US, O=Let's Encrypt, CN=E8
ALPN protocol: http/1.1
Verify return code: 0 (ok)
```

## 6. Verification probes that ran clean on all 3 nodes

```bash
# TLS terminates correctly with the right cert and ALPN
echo | openssl s_client -connect 127.0.0.1:443 \
    -servername privatelink.neo4jfield.org -alpn http/1.1

# HTTPS endpoint reachable
curl -sk -o /dev/null -w 'HTTP %{http_code}\n' \
  --resolve privatelink.neo4jfield.org:443:127.0.0.1 \
  https://privatelink.neo4jfield.org/
# → HTTP 200

# Bolt magic split routes correctly to local Neo4j Bolt
printf '\x60\x60\xb0\x17\x00\x00\x00\x05\x00\x00\x00\x04\x00\x00\x00\x03\x00\x00\x00\x02' \
  | timeout 5 openssl s_client -connect 127.0.0.1:443 \
      -servername privatelink.neo4jfield.org -quiet \
  | xxd | head -1
# → 00000000: 0000 0005   (Bolt protocol version 5 handshake response)
```
