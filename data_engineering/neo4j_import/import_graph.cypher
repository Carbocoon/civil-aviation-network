// Run with: cypher-shell -f import_graph.cypher
// Set :param nodes_file and :param edges_file to CSV files exported from ADS.
CREATE CONSTRAINT airport_code_unique IF NOT EXISTS
FOR (a:Airport) REQUIRE a.airport_code IS UNIQUE;
CREATE INDEX airport_code_lookup IF NOT EXISTS
FOR (a:Airport) ON (a.airport_code);

LOAD CSV WITH HEADERS FROM $nodes_file AS row
WITH row
WHERE trim(coalesce(row.airport_code, '')) <> ''
MERGE (a:Airport {airport_code: trim(row.airport_code)})
SET a.airport_name = row.airport_name,
    a.city = row.city,
    a.country = row.country,
    a.province = row.province,
    a.lat = CASE WHEN row.lat = '' THEN null ELSE toFloat(row.lat) END,
    a.lng = CASE WHEN row.lng = '' THEN null ELSE toFloat(row.lng) END,
    a.annual_throughput = CASE WHEN row.annual_throughput = '' THEN null ELSE toInteger(row.annual_throughput) END,
    a.designed_capacity = CASE WHEN row.designed_capacity = '' THEN null ELSE toInteger(row.designed_capacity) END,
    a.capacity_ratio = CASE WHEN row.capacity_ratio = '' THEN 0.0 ELSE toFloat(row.capacity_ratio) END,
    a.node_weight = CASE WHEN row.node_weight = '' THEN 1.0 ELSE toFloat(row.node_weight) END;

LOAD CSV WITH HEADERS FROM $edges_file AS row
WITH row
WHERE trim(coalesce(row.from_airport_code, '')) <> ''
  AND trim(coalesce(row.to_airport_code, '')) <> ''
MATCH (src:Airport {airport_code: trim(row.from_airport_code)})
MATCH (dst:Airport {airport_code: trim(row.to_airport_code)})
MERGE (src)-[r:ROUTE]->(dst)
SET r.edge_weight = toFloat(row.edge_weight),
    r.flight_count = toInteger(row.flight_count),
    r.route_throughput = toInteger(row.route_throughput);
