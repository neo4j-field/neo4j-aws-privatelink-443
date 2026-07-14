// Seeds a small synthetic dataset so the performance test measures a real
// index lookup + property read, not just constant folding on "RETURN 1".
//
// Usage:
//   cypher-shell -a <host>:<port> -u neo4j -p <password> -f seed-data.cypher
//
// Safe to re-run: MERGE on `id` means re-running just no-ops on existing rows.
// Creates 10,000 :PerfTestPerson nodes across 20 synthetic "cities", each
// following the next node in its city (so a 1-hop traversal query is also
// available if you want one) -- see queries.md for ready-to-use statements.

CREATE CONSTRAINT perftest_person_id IF NOT EXISTS
FOR (p:PerfTestPerson) REQUIRE p.id IS UNIQUE;

UNWIND range(1, 10000) AS i
MERGE (p:PerfTestPerson {id: i})
SET p.name    = "Person-" + toString(i),
    p.email   = "person" + toString(i) + "@example.com",
    p.city    = ["Austin","Boston","Chicago","Denver","Seattle","Atlanta","Portland","Miami","Phoenix","Dallas",
                  "Raleigh","Columbus","Detroit","Nashville","Orlando","Tampa","Sacramento","SanDiego","Cleveland","StLouis"][i % 20],
    p.company = "Company-" + toString(i % 500);

// One light FOLLOWS relationship per node, within the same city, so a
// 1-hop traversal query has real (if small) fan-out to walk.
MATCH (p:PerfTestPerson)
WITH p ORDER BY p.city, p.id
WITH p.city AS city, collect(p) AS people
UNWIND range(0, size(people) - 1) AS idx
WITH people[idx] AS a, people[(idx + 1) % size(people)] AS b
MERGE (a)-[:FOLLOWS]->(b);

// Sanity check
MATCH (p:PerfTestPerson) RETURN count(p) AS personCount;
