# Initial Request

> Update the haproxy configs in the 3 node cluster: a, b, and c. The change is: we need to use just 1 hostname `privatelink.neo4jfield.org` and just one port `443`, and not use `east-*.neo4jfield.org` for the bolt connection. Both HTTPS and Bolt should be using the same hostname, and the haproxy should follow the configuration similar to `config/approach-3-lts-single-instance/`.

## Why this was needed

Prior architecture used:
- `privatelink.neo4jfield.org:443` for HTTPS
- `east-a.neo4jfield.org:443`, `east-b.…`, `east-c.…` for per-node Bolt

This split-FQDN setup made Neo4j Browser cold-starts unreliable: the Browser SPA loads from the HTTPS FQDN, then opens a WebSocket Bolt connection to a *different* FQDN. Modern browsers run a synchronous CRL/CT validation cycle for each new origin on first visit; with Let's Encrypt no longer publishing OCSP URLs, that round-trip can take 60–120 seconds. During that window the JS Bolt driver gives up with "No routing servers available."

Routing both HTTPS and Bolt through the same hostname eliminates the cross-origin trust establishment: the SPA's HTTPS handshake warms the cert validation cache, and the Bolt WSS connection to the same hostname reuses cached trust immediately.

## Why approach-3 (TLS bridging), not approach-1 (SNI passthrough)

With one SNI value, HAProxy in pure SNI-passthrough mode cannot tell HTTPS apart from Bolt — the SNI is identical. ALPN-based routing helps partially (browsers offer `h2` for HTTPS, only `http/1.1` for WSS), but it's fragile if a browser ever negotiates HTTP/2 WebSocket (RFC 8441) or a client toggles its ALPN preferences.

TLS termination lets HAProxy peek the first decrypted bytes:
- `60 60 B0 17` (Bolt magic) → raw Bolt backend
- HTTP method bytes (`GET `, `POST `, …) → inner HTTP frontend, which routes WSS-Bolt vs HTTPS by `Upgrade: websocket` header

The single-instance approach-3 already proved this pattern. The cluster variant simply replicates the same HAProxy on every node and lets the NLB do cross-node distribution.
