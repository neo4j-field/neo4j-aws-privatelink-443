# Neo4j PrivateLink Demo — Python Script

Demonstrates connecting to a 3-node Neo4j Enterprise cluster from a Consumer VPC
via AWS PrivateLink, with all traffic over port 443.

## Prerequisites

```bash
pip install neo4j
```

## Usage

```bash
export NEO4J_PASSWORD=<your-password>
python3 neo4j_privatelink_demo.py

# Optional overrides
export NEO4J_URI=neo4j+s://east-a.neo4jfield.org:443
export NEO4J_USER=neo4j
```

## What it demonstrates

| Section | What it shows |
|---------|---------------|
| 1. Cluster Servers | All 3 nodes visible via `SHOW SERVERS` — addresses resolve to port 443 |
| 2. Databases | All databases online on all 3 nodes, each node serving port 443 |
| 3. Cluster Roles | Per-database roles (Neo4j 5.x) via `SHOW DATABASES` |
| 4. Write | `MERGE` nodes — routed to current write primary by Bolt protocol |
| 5. Read | `MATCH` query — reads distributed across available nodes |
| 6. Routing Table | Live routing table from cluster: WRITE, READ, ROUTE entries — all on port 443 |
| 7. Summary | Entry point, port, TLS scheme, routing mechanism |
| 8. Cleanup | Deletes demo nodes — safe to re-run |

## Key points

- **URI scheme**: `neo4j+s://` — Bolt with TLS and cluster routing enabled
- **Port**: 443 end-to-end — PrivateLink → NLB → HAProxy (SNI routing) → Neo4j Bolt on 7687
- **SNI routing**: HAProxy on each Neo4j node reads the TLS SNI header to forward traffic to the correct Bolt backend — `east-a.neo4jfield.org` → Node A, `east-b` → Node B, `east-c` → Node C
- **Routing table**: All 3 addresses in the routing table use port 443 — the driver connects to each node directly without needing to know about 7687

## Sample output

```
$ python3 neo4j_privatelink_demo.py

Connecting to : neo4j+s://east-a.neo4jfield.org:443
User          : neo4j
Protocol      : neo4j+s:// (Bolt + TLS + routing, port 443)
✓ Connected successfully via PrivateLink on port 443


============================================================
  1. Cluster Servers (SHOW SERVERS)
============================================================
  Name                                 Address                              State      Health
  ------------------------------------ ------------------------------------ ---------- ----------
  0e6f049f-c7ab-4b22-96f3-0391534a9e2b east-a.neo4jfield.org:443            Enabled    Available
  96161561-216e-4369-af3b-35e9c08578e7 east-b.neo4jfield.org:443            Enabled    Available
  c9a9466f-5263-4883-8c75-8727ec5265aa east-c.neo4jfield.org:443            Enabled    Available

============================================================
  2. Databases (SHOW DATABASES)
============================================================
  Database     Status     Role                 Address
  ------------ ---------- -------------------- ------------------------------------
  neo4j        online     primary              east-a.neo4jfield.org:443
  neo4j        online     primary              east-b.neo4jfield.org:443
  neo4j        online     primary              east-c.neo4jfield.org:443
  storage      online     primary              east-a.neo4jfield.org:443
  storage      online     primary              east-b.neo4jfield.org:443
  storage      online     primary              east-c.neo4jfield.org:443
  system       online     primary              east-a.neo4jfield.org:443
  system       online     primary              east-b.neo4jfield.org:443
  system       online     primary              east-c.neo4jfield.org:443

============================================================
  3. Cluster Roles (from SHOW DATABASES — 'neo4j' database)
============================================================
  Address                              Role
  ------------------------------------ --------------------
  east-a.neo4jfield.org:443            primary
  east-b.neo4jfield.org:443            primary
  east-c.neo4jfield.org:443            primary

  Note: In Neo4j 5.x, cluster roles are per-database (not per-server).
  Writes route to the primary; reads can be served by any node.

============================================================
  4. Write — Create Sample Nodes (routed to leader)
============================================================
  Created 3 :PrivateLinkDemo nodes (MERGE — safe to re-run).

============================================================
  5. Read — Query Sample Nodes
============================================================
  ID     Name
  ------ --------------------
  1      Demo-Node-1
  2      Demo-Node-2
  3      Demo-Node-3

============================================================
  6. Routing Table Returned by Cluster
============================================================
  TTL: 300s
  WRITE      → east-c.neo4jfield.org:443
  READ       → east-a.neo4jfield.org:443, east-b.neo4jfield.org:443
  ROUTE      → east-b.neo4jfield.org:443, east-a.neo4jfield.org:443, east-c.neo4jfield.org:443

  All addresses above use port 443 — consumers reach each
  node via PrivateLink, SNI routing selects the right Bolt backend.

============================================================
  7. Connection Summary
============================================================
  Entry point   : neo4j+s://east-a.neo4jfield.org:443
  Port          : 443 (PrivateLink → NLB → HAProxy → Neo4j :7687)
  TLS           : neo4j+s:// — end-to-end encrypted
  Routing       : SNI-based at HAProxy; cluster routing via Bolt protocol

============================================================
  8. Cleanup
============================================================
  Deleted 3 demo nodes.

============================================================
  Demo Complete — All queries executed over PrivateLink on port 443
============================================================
```
