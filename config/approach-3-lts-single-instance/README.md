# Approach 3 — Neo4j 5.x LTS, Single Instance, Single Hostname (TLS Bridging)

A minimal, single-instance Neo4j 5.26 LTS deployment behind HAProxy on port 443.
Differs from Approach 1 in two ways:

1. **Single hostname for everything** (`lts.neo4jfield.org:443`) — Browser SPA, raw Bolt drivers, and Bolt-over-WebSocket all reach the same FQDN/port.
2. **TLS bridging** at HAProxy (terminate + re-encrypt to Neo4j) instead of pure SNI passthrough.

## When to use this

- Single Neo4j Enterprise LTS instance (no clustering)
- One DNS name allowed for both HTTPS and Bolt
- Customer can accept HAProxy as a TLS terminator (HAProxy holds the private key on the same host as Neo4j)
- Cross-origin browser cold-start cert validation must NOT delay first connect

## Why single hostname (vs Approach 1's two)

When the Browser SPA loads from `https://lts.neo4jfield.org/browser/` and then opens
`wss://lts-bolt.neo4jfield.org:443` (different host), modern browsers run a
synchronous CRL/CT validation cycle for the new origin on first visit. With Let's
Encrypt no longer publishing OCSP URLs, that round-trip can take 60–120 seconds —
during which the JS Bolt driver gives up with "No routing servers available."

Routing both HTTPS and Bolt through a single hostname eliminates the cross-origin
trust establishment: the SPA's HTTPS handshake warms the cert validation cache,
and the Bolt WSS connection to the same hostname reuses cached trust immediately.

## Why TLS bridging (vs SNI passthrough)

In SNI passthrough mode, HAProxy can only route by the SNI in the unencrypted
ClientHello. With one SNI value, HAProxy cannot tell HTTPS from Bolt. ALPN-based
routing works partially (browsers offer `h2` for HTTPS, only `http/1.1` for WSS),
but it's fragile if a browser ever negotiates HTTP/2-WebSocket (RFC 8441) or a
client toggles its ALPN preferences.

TLS termination lets HAProxy peek at the first decrypted bytes:
- `60 60 B0 17` (Bolt magic) → raw Bolt backend
- HTTP method bytes (`GET `, `POST`, …) → inner HTTP frontend, which routes
  WSS-Bolt vs HTTPS by `Upgrade: websocket` header

## Files

| File | Purpose |
|---|---|
| `neo4j.conf` | Neo4j 5.26 LTS single-instance config. TLS REQUIRED on Bolt, HTTPS enabled. Bolt and HTTPS both advertised on `lts.neo4jfield.org:443`. |
| `haproxy.cfg` | Chained-frontend HAProxy: outer TLS-terminate + Bolt-magic detection, inner mode-http for HTTPS / WSS split. |

## Deploy outline

```bash
# Combine cert + key for HAProxy
cat privkey.pem fullchain.pem > /etc/haproxy/certs/combined.pem
chmod 600 /etc/haproxy/certs/combined.pem
chown haproxy:haproxy /etc/haproxy/certs/combined.pem

# Install configs
install -o neo4j -g neo4j -m 0640 neo4j.conf /etc/neo4j/neo4j.conf
install -o root  -g root  -m 0644 haproxy.cfg /etc/haproxy/haproxy.cfg

# SELinux: allow haproxy to connect to non-default backend ports
setsebool -P haproxy_connect_any on

# firewalld
firewall-cmd --permanent --add-service=ssh
firewall-cmd --permanent --add-service=https
firewall-cmd --reload

# Start
systemctl enable --now neo4j haproxy
```

## Trust boundary note

HAProxy and Neo4j run on the same EC2 host. Plaintext exists only in HAProxy's
process memory between the decrypt-from-client and re-encrypt-to-loopback steps;
no plaintext traverses any network interface. The private key lives at
`/etc/haproxy/certs/combined.pem` (mode 0600, owner `haproxy`).

If a customer requires "no intermediate sees plaintext," use Approach 1 (pure
SNI passthrough) and accept the cold-start glitch — or move to a single-port,
single-protocol architecture.
