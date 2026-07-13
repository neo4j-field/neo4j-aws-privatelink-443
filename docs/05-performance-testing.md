# Performance Testing: Quantifying HAProxy's Overhead

Before adopting Approach 1 (HAProxy + NLB + PrivateLink), it's reasonable to ask: **how much latency does the extra TLS-terminate-and-forward hop actually add?**

Ready-to-run JMeter and Postman/Newman test scripts that answer this — by hitting Neo4j's HTTP Query API v2 once via HAProxy on `443` and once directly on `7473` (HAProxy bypassed), same query, same client, same network — live in [`performance-testing/`](../performance-testing/README.md).

See [`performance-testing/README.md`](../performance-testing/README.md) for tool choice (JMeter vs Postman), setup, how to establish a fair "HAProxy bypassed" baseline without permanently opening `7473` to the internet, and how to read/present the results.
