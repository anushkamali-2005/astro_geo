# 09_graphrag_seed.py
# Creates the first cross-domain knowledge graph connections
# Run once after Neo4j Aura instance is ready

from neo4j import GraphDatabase
import psycopg2
import pandas as pd
import os
from dotenv import load_dotenv

# Explicitly load backend/.env since we run from project root
dotenv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
load_dotenv(dotenv_path)

# ── Connect to Neo4j ─────────────────────────────────────────
driver = GraphDatabase.driver(
    os.getenv('NEO4J_URI'),
    auth=(
        os.getenv('NEO4J_USERNAME', os.getenv('NEO4J_USER', 'neo4j')),
        os.getenv('NEO4J_PASSWORD')
    )
)

# ── Connect to PostgreSQL ────────────────────────────────────
conn = psycopg2.connect(
    dbname=os.getenv('DB_NAME', 'astrogeo'),
    user=os.getenv('DB_USER'),
    password=os.getenv('DB_PASSWORD'),
    host=os.getenv('DB_HOST'),
    port=os.getenv('DB_PORT', '5432')
)


def create_constraints(session):
    """Create uniqueness constraints — run once."""
    session.run("CREATE CONSTRAINT IF NOT EXISTS "
                "FOR (z:Zone) REQUIRE z.name IS UNIQUE")
    session.run("CREATE CONSTRAINT IF NOT EXISTS "
                "FOR (r:Region) REQUIRE r.name IS UNIQUE")
    session.run("CREATE CONSTRAINT IF NOT EXISTS "
                "FOR (l:Country) REQUIRE l.name IS UNIQUE")
    session.run("CREATE CONSTRAINT IF NOT EXISTS "
                "FOR (a:Asteroid) REQUIRE a.designation IS UNIQUE")
    session.run("CREATE CONSTRAINT IF NOT EXISTS "
                "FOR (c:LandCoverChange) REQUIRE c.id IS UNIQUE")
    print("Constraints created.")


def seed_geographic_hierarchy(session):
    """
    Create Country, Macro-Region, and State-level Region nodes.
    Establishes: Country <- Macro-Region <- State-level Region <- Zone.
    """
    # 1. Create Country node
    session.run("""
        MERGE (c:Country {name: 'India'})
        SET c.latitude = 20.6,
            c.longitude = 78.9,
            c.type = 'Country'
    """)

    # 2. Create Macro-Region nodes
    macros = ['North India', 'South India', 'West India', 'East India', 'Central India', 'Northeast India']
    for m in macros:
        session.run("""
            MERGE (mr:Region {name: $name})
            SET mr.level = 'macro'
            WITH mr
            MATCH (c:Country {name: 'India'})
            MERGE (mr)-[:PART_OF]->(c)
        """, {'name': m})

    # 3. Extract State/Regions from ndvi_results and connect to Macro
    df = pd.read_sql("SELECT DISTINCT zone_name FROM ndvi_results", conn)
    
    # Mapping state to macro
    state_to_macro = {
        'Maharashtra': 'West India', 'Gujarat': 'West India', 'Rajasthan': 'West India',
        'Punjab': 'North India', 'Haryana': 'North India', 'Kashmir': 'North India',
        'Tamil Nadu': 'South India', 'Karnataka': 'South India', 'Kerala': 'South India',
        'Andhra Pradesh': 'South India', 'Telangana': 'South India',
        'West Bengal': 'East India', 'Bihar': 'East India', 'Odisha': 'East India',
        'Madhya Pradesh': 'Central India', 'Chhattisgarh': 'Central India',
        'Northeast India': 'Northeast India', 'Assam': 'Northeast India'
    }

    for _, row in df.iterrows():
        zone_raw = row['zone_name']
        region_name = zone_raw.split('_')[0].capitalize()
        
        # Normalization
        if region_name == 'Andhra': region_name = 'Andhra Pradesh'
        if region_name == 'Tamil': region_name = 'Tamil Nadu'
        if region_name == 'West': region_name = 'West Bengal'
        if region_name == 'Northeast': region_name = 'Northeast India'
        if region_name == 'Madhya': region_name = 'Madhya Pradesh'
        if region_name == 'Uttar': region_name = 'Uttar Pradesh'
        if region_name == 'Himachal': region_name = 'Himachal Pradesh'
        
        macro = state_to_macro.get(region_name, 'North India') # Fallback

        session.run("""
            MERGE (r:Region {name: $region_name})
            SET r.level = 'state'
            WITH r
            MATCH (mr:Region {name: $macro})
            MERGE (r)-[:PART_OF]->(mr)
        """, {'region_name': region_name, 'macro': macro})

    # 4. Handle Indian Ocean for Anomalies
    session.run("""
        MERGE (c:Country {name: 'Indian Ocean'})
        SET c.type = 'Water Body',
            c.latitude = 10.0,
            c.longitude = 75.0
    """)

    print(f"Standardized hierarchy (Country <- Macro <- State) created.")


def seed_zone_nodes(session):
    """
    Create Zone nodes from ndvi_results PostgreSQL table.
    One node per zone per year with NDVI statistics.
    """
    df = pd.read_sql("""
        SELECT
            n.zone_name,
            n.year,
            n.ndvi_mean,
            n.ndvi_min,
            n.ndvi_max,
            n.delta_total_mean,
            n.delta_recent_mean,
            n.change_class,
            n.change_class_label,
            n.confidence,
            n.verification_hash,
            a.states
        FROM ndvi_results n
        JOIN aoi_metadata a ON n.aoi_id = a.id
        ORDER BY zone_name, year
    """, conn)

    for _, row in df.iterrows():
        session.run("""
            MERGE (z:Zone {name: $zone_name})
            SET z.states = $states

            MERGE (o:NDVIObservation {
                id: $obs_id
            })
            SET o.year         = $year,
                o.ndvi_mean    = $ndvi_mean,
                o.ndvi_min     = $ndvi_min,
                o.ndvi_max     = $ndvi_max,
                o.delta_total  = $delta_total,
                o.delta_recent = $delta_recent,
                o.change_class = $change_class,
                o.change_label = $change_label,
                o.confidence   = $confidence,
                o.verified_hash= $hash

            MERGE (z)-[:HAS_OBSERVATION]->(o)
        """, {
            'zone_name':    row['zone_name'],
            'states':       row['states'],
            'obs_id':       f"{row['zone_name']}_{row['year']}",
            'year':         int(row['year']),
            'ndvi_mean':    float(row['ndvi_mean']),
            'ndvi_min':     float(row['ndvi_min']),
            'ndvi_max':     float(row['ndvi_max']),
            'delta_total':  float(row['delta_total_mean']),
            'delta_recent': float(row['delta_recent_mean']),
            'change_class': int(row['change_class']),
            'change_label': row['change_class_label'],
            'confidence':   float(row['confidence']),
            'hash':         row['verification_hash'],
        })

    print(f"Created Zone and NDVIObservation nodes — {len(df)} observations.")


def seed_change_edges(session):
    """
    Create LandCoverChange nodes and connect them to Zones.
    These represent detected changes with evidence.
    """
    df = pd.read_sql("""
        SELECT DISTINCT
            n.zone_name,
            n.change_class,
            n.change_class_label,
            n.delta_total_mean,
            n.confidence,
            n.verification_hash
        FROM ndvi_results n
        JOIN aoi_metadata a ON n.aoi_id = a.id
        WHERE n.year = 2024
        ORDER BY zone_name
    """, conn)

    for _, row in df.iterrows():
        session.run("""
            MERGE (z:Zone {name: $zone_name})
            MERGE (c:LandCoverChange {
                id: $change_id
            })
            SET c.type       = $change_type,
                c.magnitude  = $magnitude,
                c.confidence = $confidence,
                c.year       = 2024,
                c.hash       = $hash

            MERGE (z)-[:SHOWS_CHANGE {
                magnitude:  $magnitude,
                confidence: $confidence,
                year:       2024
            }]->(c)
        """, {
            'zone_name':   row['zone_name'],
            'change_id':   f"change_{row['zone_name']}_2024",
            'change_type': row['change_class_label'],
            'magnitude':   float(row['delta_total_mean']),
            'confidence':  float(row['confidence']),
            'hash':        row['verification_hash'],
        })

    print(f"Created {len(df)} LandCoverChange nodes with SHOWS_CHANGE edges.")


def seed_zone_location_edges(session):
    """
    Connect Zone nodes to Region nodes.
    This enables the hop: Zone -> Region -> Country.
    """
    df = pd.read_sql("SELECT DISTINCT zone_name FROM ndvi_results", conn)
    
    for _, row in df.iterrows():
        zone_raw = row['zone_name']
        region_name = zone_raw.split('_')[0].capitalize()
        
        # Normalization (must match seed_geographic_hierarchy)
        if region_name == 'Andhra': region_name = 'Andhra Pradesh'
        if region_name == 'Tamil': region_name = 'Tamil Nadu'
        if region_name == 'West': region_name = 'West Bengal'
        if region_name == 'Northeast': region_name = 'Northeast India'
        if region_name == 'Madhya': region_name = 'Madhya Pradesh'
        if region_name == 'Uttar': region_name = 'Uttar Pradesh'
        if region_name == 'Himachal': region_name = 'Himachal Pradesh'

        session.run("""
            MATCH (z:Zone {name: $zone})
            MATCH (r:Region {name: $region})
            MERGE (z)-[:PART_OF]->(r)
        """, {'zone': zone_raw, 'region': region_name})

    print(f"Created Hierarchy: Zone -> Region PART_OF edges for {len(df)} zones.")


def seed_asteroid_nodes(session):
    """
    Create Asteroid nodes from PostgreSQL asteroid ML table.
    Connect high-risk and anomalous asteroids to Location nodes
    via PASSED_OVER edges — the first cross-agent connection.
    """
    # Load high-risk asteroids with approach data
    try:
        asteroids = pd.read_sql("""
            SELECT
                asteroid_id AS des,
                risk_category,
                improved_risk_score,
                is_anomaly,
                anomaly_score,
                cluster,
                adaptive_risk_category,
                verification_hash
            FROM astronomy.asteroid_ml_predictions
            WHERE risk_category IN ('High', 'Medium')
            OR is_anomaly = true
            LIMIT 500
        """, conn)
    except Exception as e:
        print(f"Skipping seed_asteroid_nodes due to error: {e}")
        return

    for _, row in asteroids.iterrows():
        session.run("""
            MERGE (a:Asteroid {designation: $des})
            SET a.risk_category    = $risk_cat,
                a.risk_score       = $risk_score,
                a.is_anomaly       = $is_anomaly,
                a.anomaly_score    = $anomaly_score,
                a.cluster          = $cluster,
                a.adaptive_category= $adaptive_cat,
                a.verified_hash    = $hash
        """, {
            'des':         row['des'],
            'risk_cat':    row['risk_category'],
            'risk_score':  float(row['improved_risk_score']),
            'is_anomaly':  bool(row['is_anomaly']),
            'anomaly_score':float(row['anomaly_score']),
            'cluster':     int(row['cluster']),
            'adaptive_cat':row['adaptive_risk_category'],
            'hash':        row['verification_hash'],
        })

    print(f"Created {len(asteroids)} Asteroid nodes.")


def create_cross_agent_edges(session):
    """
    Connect high-risk asteroids to India Country node.
    This is the first real multi-hop GraphRAG connection.
    """
    # Connect high-risk asteroids to India Country
    session.run("""
        MATCH (a:Asteroid)
        WHERE a.risk_category = 'High' OR a.adaptive_category = 'High'
        MATCH (c:Country {name: 'India'})
        MERGE (a)-[:APPROACH_RISK {
            note: 'Planetary close approach — India (National)'
        }]->(c)
    """)

    # Connect anomalous asteroids to Indian Ocean
    session.run("""
        MATCH (a:Asteroid)
        WHERE a.is_anomaly = true
        MATCH (c:Country {name: 'Indian Ocean'})
        MERGE (a)-[:ANOMALOUS_PASS_NEAR]->(c)
    """)

    print("Cross-agent edges created — Astronomy ↔ Country connected.")


def verify_graph(session):
    """Print graph summary to confirm everything loaded."""
    counts = session.run("""
        MATCH (n)
        RETURN labels(n)[0] AS label, count(n) AS count
        ORDER BY count DESC
    """).data()

    print("\n" + "=" * 50)
    print("GRAPH SUMMARY")
    print("=" * 50)
    print("Nodes:")
    for row in counts:
        print(f"  {row['label']:<25}: {row['count']}")

    # Test the key cross-domain query with the new hierarchy:
    # Asteroid -> Country -> Region -> Zone -> LandCoverChange
    result = session.run("""
        MATCH (a:Asteroid)-[:APPROACH_RISK]->(c:Country {name: 'India'})
              <-[:PART_OF]-(r:Region)<-[:PART_OF]-(z:Zone)
              -[:SHOWS_CHANGE]->(lcc:LandCoverChange)
        WHERE lcc.type = 'vegetation_loss'
        RETURN a.designation AS asteroid,
               r.name        AS state,
               z.name        AS zone,
               lcc.confidence AS confidence
        LIMIT 5
    """).data()

    print("\nNationwide Cross-domain query result:")
    print("(High-risk Asteroids → India (National) → States → Zones)")
    if result:
        for row in result:
            print(f"  {row['asteroid']} → India → {row['state']}"
                  f" → {row['zone']} "
                  f"(confidence: {row['confidence']:.2f})")
    else:
        print("  No multi-hop results yet. Ensure hierarchy is correct.")

    print("=" * 50)


# ── Run everything ───────────────────────────────────────────
if __name__ == '__main__':
    print("Seeding AstroGeo knowledge graph...\n")

    with driver.session() as session:
        create_constraints(session)
        seed_geographic_hierarchy(session)
        seed_zone_nodes(session)
        seed_change_edges(session)
        seed_zone_location_edges(session)
        seed_asteroid_nodes(session)
        create_cross_agent_edges(session)
        verify_graph(session)

    driver.close()
    conn.close()
    print("\nDone. GraphRAG foundation is live.")
    print("Next: build LangGraph orchestration skeleton")