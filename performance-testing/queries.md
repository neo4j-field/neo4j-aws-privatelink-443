# Reference Queries

Run [`seed-data.cypher`](seed-data.cypher) once before using any of these — they all target the `:PerfTestPerson` dataset it creates (10,000 nodes, indexed on `id`, grouped into 20 synthetic cities with a `FOLLOWS` ring per city).

The JMeter plan defaults to the **point lookup** below, with `id` randomized per request (`1`–`10000`) so the test spreads across the dataset instead of hammering one cached node.

## Point lookup (default — indexed, ~O(1))

```json
{
  "statement": "MATCH (p:PerfTestPerson {id: $id}) RETURN p.id AS id, p.name AS name, p.email AS email, p.city AS city",
  "parameters": { "id": 4271 }
}
```

## Filtered scan (heavier — no index on `city`, forces a label scan + filter)

```json
{
  "statement": "MATCH (p:PerfTestPerson) WHERE p.city = $city RETURN p.name AS name, p.email AS email ORDER BY p.name LIMIT 25",
  "parameters": { "city": "Austin" }
}
```

## 1-hop traversal (exercises relationship expansion)

```json
{
  "statement": "MATCH (p:PerfTestPerson {id: $id})-[:FOLLOWS]->(f) RETURN p.name AS person, f.name AS follows",
  "parameters": { "id": 4271 }
}
```

To switch the JMeter plan to one of the heavier queries, override `CYPHER_STATEMENT` (and drop the `$id` parameter substitution if you switch to the filtered scan — see the `-JCYPHER_STATEMENT=...` example in the main [README](README.md)).
