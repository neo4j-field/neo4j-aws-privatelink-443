#!/usr/bin/env python3
"""
Neo4j Cluster Connection Demo — AWS PrivateLink over Port 443
=============================================================
Demonstrates connecting to a 3-node Neo4j Enterprise cluster from
a Consumer VPC via AWS PrivateLink, with all traffic over port 443.

SNI-based routing at the HAProxy layer:
  privatelink.neo4jfield.org:443  → Neo4j HTTPS (Browser only)
  east-a.neo4jfield.org:443       → Neo4j Bolt on Node A
  east-b.neo4jfield.org:443       → Neo4j Bolt on Node B
  east-c.neo4jfield.org:443       → Neo4j Bolt on Node C

The driver uses neo4j+s://east-a.neo4jfield.org:443 as the initial
contact point. It fetches the routing table (which lists all 3 nodes
on port 443), then routes reads and writes across the cluster — all
still over port 443 through PrivateLink.

Usage:
    export NEO4J_PASSWORD=<your-password>
    python3 neo4j_privatelink_demo.py

    # Optional overrides:
    export NEO4J_URI=neo4j+s://east-a.neo4jfield.org:443
    export NEO4J_USER=neo4j

Requirements:
    pip install neo4j
"""

import os
import sys
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, AuthError

# ── Connection settings ──────────────────────────────────────────────────────
# neo4j+s:// = Bolt with TLS, with routing (cluster-aware)
# Use east-a/b/c.neo4jfield.org:443 for Bolt — HAProxy routes by SNI to Bolt backend
# Use privatelink.neo4jfield.org:443 only for Neo4j Browser (HTTPS)
URI      = os.getenv("NEO4J_URI",      "neo4j+s://east-a.neo4jfield.org:443")
USER     = os.getenv("NEO4J_USER",     "neo4j")
PASSWORD = os.getenv("NEO4J_PASSWORD", "")

if not PASSWORD:
    print("ERROR: Set the NEO4J_PASSWORD environment variable before running.")
    print("  export NEO4J_PASSWORD=<your-password>")
    sys.exit(1)


def section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def run_demo():
    print(f"\nConnecting to : {URI}")
    print(f"User          : {USER}")
    print(f"Protocol      : neo4j+s:// (Bolt + TLS + routing, port 443)")

    try:
        driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
        driver.verify_connectivity()
        print("✓ Connected successfully via PrivateLink on port 443\n")
    except AuthError:
        print("ERROR: Authentication failed. Check NEO4J_PASSWORD.")
        sys.exit(1)
    except ServiceUnavailable as e:
        print(f"ERROR: Could not reach the cluster.\n  {e}")
        sys.exit(1)

    with driver.session(database="neo4j") as session:

        # ── 1. Cluster health ────────────────────────────────────────────────
        section("1. Cluster Servers (SHOW SERVERS)")
        result = session.run(
            "SHOW SERVERS YIELD name, address, state, health"
        )
        rows = result.data()
        print(f"  {'Name':<36} {'Address':<36} {'State':<10} {'Health'}")
        print(f"  {'-'*36} {'-'*36} {'-'*10} {'-'*10}")
        for r in rows:
            print(f"  {r['name']:<36} {r['address']:<36} {r['state']:<10} {r['health']}")

        # ── 2. Databases ─────────────────────────────────────────────────────
        section("2. Databases (SHOW DATABASES)")
        result = session.run(
            "SHOW DATABASES YIELD name, currentStatus, role, address "
            "ORDER BY name, address"
        )
        rows = result.data()
        print(f"  {'Database':<12} {'Status':<10} {'Role':<20} {'Address'}")
        print(f"  {'-'*12} {'-'*10} {'-'*20} {'-'*36}")
        for r in rows:
            print(f"  {r['name']:<12} {r['currentStatus']:<10} {r['role']:<20} {r['address']}")

        # ── 3. Cluster role per node (Neo4j 5.x: roles are per-database) ────────
        section("3. Cluster Roles (from SHOW DATABASES — 'neo4j' database)")
        result = session.run(
            "SHOW DATABASES YIELD name, address, role "
            "WHERE name = 'neo4j' "
            "RETURN address, role ORDER BY address"
        )
        rows = result.data()
        print(f"  {'Address':<36} {'Role'}")
        print(f"  {'-'*36} {'-'*20}")
        for r in rows:
            print(f"  {r['address']:<36} {r['role']}")
        print()
        print("  Note: In Neo4j 5.x, cluster roles are per-database (not per-server).")
        print("  Writes route to the primary; reads can be served by any node.")

        # ── 4. Create sample nodes (write — goes to leader) ──────────────────
        section("4. Write — Create Sample Nodes (routed to leader)")
        session.run("MERGE (n:PrivateLinkDemo {id: 1, name: 'Demo-Node-1'})")
        session.run("MERGE (n:PrivateLinkDemo {id: 2, name: 'Demo-Node-2'})")
        session.run("MERGE (n:PrivateLinkDemo {id: 3, name: 'Demo-Node-3'})")
        print("  Created 3 :PrivateLinkDemo nodes (MERGE — safe to re-run).")

        # ── 5. Read them back ────────────────────────────────────────────────
        section("5. Read — Query Sample Nodes")
        result = session.run(
            "MATCH (n:PrivateLinkDemo) "
            "RETURN n.id AS id, n.name AS name "
            "ORDER BY n.id"
        )
        rows = result.data()
        print(f"  {'ID':<6} {'Name'}")
        print(f"  {'-'*6} {'-'*20}")
        for r in rows:
            print(f"  {r['id']:<6} {r['name']}")

        # ── 6. Routing table ─────────────────────────────────────────────────
        section("6. Routing Table Returned by Cluster")
        result = session.run(
            "CALL dbms.routing.getRoutingTable({}, 'neo4j') "
            "YIELD ttl, servers"
        )
        row = result.single()
        print(f"  TTL: {row['ttl']}s")
        for entry in row['servers']:
            role    = entry['role']
            addrs   = ', '.join(entry['addresses'])
            print(f"  {role:<10} → {addrs}")
        print()
        print("  All addresses above use port 443 — consumers reach each")
        print("  node via PrivateLink, SNI routing selects the right Bolt backend.")

        # ── 7. Connection summary ────────────────────────────────────────────
        section("7. Connection Summary")
        print(f"  Entry point   : {URI}")
        print(f"  Port          : 443 (PrivateLink → NLB → HAProxy → Neo4j :7687)")
        print(f"  TLS           : neo4j+s:// — end-to-end encrypted")
        print(f"  Routing       : SNI-based at HAProxy; cluster routing via Bolt protocol")

        # ── 8. Cleanup ───────────────────────────────────────────────────────
        section("8. Cleanup")
        result = session.run(
            "MATCH (n:PrivateLinkDemo) DELETE n RETURN count(n) AS deleted"
        )
        print(f"  Deleted {result.single()['deleted']} demo nodes.")

    driver.close()
    section("Demo Complete — All queries executed over PrivateLink on port 443")


if __name__ == "__main__":
    run_demo()
