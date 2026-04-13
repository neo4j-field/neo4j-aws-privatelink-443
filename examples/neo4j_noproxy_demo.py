#!/usr/bin/env python3
"""
Neo4j Bolt on Port 443 — Proof of Concept
==========================================
Proves that the Neo4j Bolt protocol is fully functional on port 443.
Standard Bolt drivers connect, authenticate, write, read, and clean up —
all over port 443 with full TLS certificate validation.

Required neo4j.conf settings
-----------------------------
Two settings must be aligned for port 443 to work end-to-end:

  # Tell Neo4j to advertise port 443 in routing tables and system metadata.
  # Clients use this address to connect.
  server.bolt.advertised_address = <hostname>:443

  # The actual port Neo4j listens on internally.
  # If a load balancer or NAT rule maps 443 → 7687, keep this as :7687.
  # If Neo4j binds directly to 443, set this to :443.
  server.bolt.listen_address = :7687

Driver scheme
-------------
  bolt+s:// — direct Bolt connection with TLS and full certificate validation.
  No routing (neo4j://) is needed when connecting to a single node.

Usage:
    export NEO4J_PASSWORD=<your-password>
    python3 neo4j_noproxy_demo.py

    # Optional overrides:
    export NEO4J_URI=bolt+s://bolt-noproxy.neo4jfield.org:443
    export NEO4J_USER=neo4j

Requirements:
    pip install neo4j
"""

import os
import sys
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, AuthError

# ── Connection settings ──────────────────────────────────────────────────────
# bolt+ssc:// = direct Bolt + TLS, skip cert validation
# No routing scheme (neo4j://) needed — this is a standalone server
URI      = os.getenv("NEO4J_URI",      "bolt+s://bolt-noproxy.neo4jfield.org:443")
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
    print(f"Protocol      : bolt+s:// (direct Bolt + TLS + cert validation, port 443, no HAProxy)")

    try:
        driver = GraphDatabase.driver(URI, auth=(USER, PASSWORD))
        driver.verify_connectivity()
        print("✓ Connected successfully — direct Bolt on port 443\n")
    except AuthError:
        print("ERROR: Authentication failed. Check NEO4J_PASSWORD.")
        sys.exit(1)
    except ServiceUnavailable as e:
        print(f"ERROR: Could not reach the server.\n  {e}")
        sys.exit(1)

    with driver.session(database="storage") as session:

        # ── 1. Server info ───────────────────────────────────────────────────
        section("1. Server Info")
        result = session.run(
            "CALL dbms.components() YIELD name, versions, edition "
            "RETURN name, versions[0] AS version, edition"
        )
        row = result.single()
        print(f"  Product  : {row['name']}")
        print(f"  Version  : {row['version']}")
        print(f"  Edition  : {row['edition']}")

        # ── 2. Databases ─────────────────────────────────────────────────────
        section("2. Databases (SHOW DATABASES)")
        result = session.run(
            "SHOW DATABASES YIELD name, currentStatus, role, address "
            "ORDER BY name"
        )
        rows = result.data()
        print(f"  {'Database':<12} {'Status':<10} {'Role':<20} {'Address'}")
        print(f"  {'-'*12} {'-'*10} {'-'*20} {'-'*40}")
        for r in rows:
            print(f"  {r['name']:<12} {r['currentStatus']:<10} {r['role']:<20} {r['address']}")

        # ── 3. Write sample nodes ────────────────────────────────────────────
        section("3. Write — Create Sample Nodes")
        session.run("MERGE (n:NoProxyDemo {id: 1, name: 'Demo-Node-1'})")
        session.run("MERGE (n:NoProxyDemo {id: 2, name: 'Demo-Node-2'})")
        session.run("MERGE (n:NoProxyDemo {id: 3, name: 'Demo-Node-3'})")
        print("  Created 3 :NoProxyDemo nodes (MERGE — safe to re-run).")

        # ── 4. Read them back ────────────────────────────────────────────────
        section("4. Read — Query Sample Nodes")
        result = session.run(
            "MATCH (n:NoProxyDemo) "
            "RETURN n.id AS id, n.name AS name "
            "ORDER BY n.id"
        )
        rows = result.data()
        print(f"  {'ID':<6} {'Name'}")
        print(f"  {'-'*6} {'-'*20}")
        for r in rows:
            print(f"  {r['id']:<6} {r['name']}")

        # ── 5. Connection summary ────────────────────────────────────────────
        section("5. Connection Summary")
        print(f"  Entry point   : {URI}")
        print(f"  Port          : 443 → Neo4j Bolt :7687 (NLB port mapping / iptables)")
        print(f"  TLS           : bolt+s:// — encrypted, full certificate validation")
        print(f"  HAProxy       : None — Neo4j receives Bolt directly")
        print(f"  Architecture  : Consumer → port 443 → NLB (443→7687) → Neo4j")

        # ── 6. Cleanup ───────────────────────────────────────────────────────
        section("6. Cleanup")
        result = session.run(
            "MATCH (n:NoProxyDemo) DELETE n RETURN count(n) AS deleted"
        )
        print(f"  Deleted {result.single()['deleted']} demo nodes.")

    driver.close()
    section("Demo Complete — Bolt reached Neo4j directly on port 443 (no HAProxy)")


if __name__ == "__main__":
    run_demo()
