# fix_part_of_edges.py
# Run once — creates PART_OF edges between your existing Zone nodes
# and the Region nodes seeded by 09b_seed_solar_flares.py

from neo4j import GraphDatabase
import os
from dotenv import load_dotenv

# Explicitly load backend/.env since we run from project root
# Script is in backend/pipelines/, .env is in backend/
dotenv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
load_dotenv(dotenv_path)

# Maps region → keywords to match against your Zone node names
# Adjust these to match how your zones are actually named in Neo4j
REGION_ZONE_KEYWORDS = {
    'West India': [
        'maharashtra', 'gujarat', 'rajasthan', 'dadra',
        'pune', 'mumbai', 'nashik', 'nagpur',
        'konkan', 'vidarbha', 'marathwada',
    ],
    'North India': [
        'punjab', 'haryana', 'uttar_pradesh', 'delhi',
        'himachal', 'uttarakhand', 'jammu', 'kashmir', 'ladakh',
    ],
    'South India': [
        'tamil_nadu', 'karnataka', 'andhra', 'telangana', 'kerala',
        'puducherry', 'lakshadweep', 'chennai', 'bangalore', 'hyderabad',
    ],
    'East India': [
        'west_bengal', 'odisha', 'bihar', 'jharkhand', 'sikkim',
        'kolkata', 'bhubaneswar',
    ],
    'Central India': [
        'madhya_pradesh', 'chhattisgarh',
        'bhopal', 'indore', 'raipur',
    ],
    'Northeast India': [
        'assam', 'manipur', 'meghalaya', 'nagaland',
        'mizoram', 'tripura', 'arunachal', 'northeast',
    ],
    'Islands': [
        'andaman', 'nicobar',
    ]
}

def fix_part_of_edges():
    driver = GraphDatabase.driver(
        os.getenv('NEO4J_URI'),
        auth=(
            os.getenv('NEO4J_USERNAME', os.getenv('NEO4J_USER', 'neo4j')),
            os.getenv('NEO4J_PASSWORD')
        )
    )

    with driver.session() as session:
        # First — Ensure Country node exists
        session.run("MERGE (c:Country {name: 'India'}) SET c.type='Country'")

        # 1. Connect Macro-Regions to Country
        print("Connecting Macro-Regions to India Country node...")
        macros = ['North India', 'South India', 'West India', 'East India', 'Central India', 'Northeast India']
        for m in macros:
            session.run("""
                MERGE (mr:Region {name: $name})
                SET mr.level = 'macro'
                WITH mr
                MATCH (c:Country {name: 'India'})
                MERGE (mr)-[:PART_OF]->(c)
            """, {'name': m})

        # 2. Connect Zones to State Regions (using keywords)
        print("\nCreating PART_OF edges (Zone -> State)...")
        # We'll use a simpler mapping for state-level regions
        STATE_MAPPING = {
            'Maharashtra': ['vidarbha', 'marathwada', 'pune', 'mumbai'],
            'Rajasthan': ['rajasthan'],
            'Punjab': ['punjab', 'haryana', 'delhi'],
            'Tamil Nadu': ['tamil_nadu', 'chennai'],
            'Karnataka': ['karnataka', 'bangalore'],
            'Andhra Pradesh': ['andhra', 'telangana', 'coast', 'sriharikota'],
            'West Bengal': ['west_bengal', 'sikkim', 'kolkata'],
        }

        for state, keywords in STATE_MAPPING.items():
            for kw in keywords:
                session.run("""
                    MATCH (z:Zone)
                    WHERE z.name CONTAINS $kw
                    MERGE (s:Region {name: $state})
                    SET s.level = 'state'
                    MERGE (z)-[:PART_OF]->(s)
                """, {'kw': kw, 'state': state})

        # 3. Connect State Regions to Macro Regions
        print("\nConnecting State Regions to Macro Regions...")
        STATE_TO_MACRO = {
            'Maharashtra': 'West India', 'Rajasthan': 'West India', 'Gujarat': 'West India',
            'Punjab': 'North India', 'Haryana': 'North India',
            'Tamil Nadu': 'South India', 'Karnataka': 'South India', 'Andhra Pradesh': 'South India',
            'West Bengal': 'East India', 'Orissa': 'East India',
        }
        for state, macro in STATE_TO_MACRO.items():
            session.run("""
                MATCH (s:Region {name: $state, level: 'state'})
                MATCH (m:Region {name: $macro, level: 'macro'})
                MERGE (s)-[:PART_OF]->(m)
            """, {'state': state, 'macro': macro})

        # Verify the full nationwide cross-domain path
        print("\nTesting Nationwide cross-domain path...")
        test = session.run("""
            MATCH (e:SolarEvent)-[:DISRUPTS]->(mr:Region)
                  <-[:PART_OF]-(sr:Region)<-[:PART_OF]-(z:Zone)
                  -[:SHOWS_CHANGE]->(c:LandCoverChange)
            RETURN e.date       AS date,
                   mr.name      AS macro,
                   sr.name      AS state,
                   z.name       AS zone,
                   c.type       AS change
            LIMIT 3
        """).data()

        if test:
            print(f"✅ Nationwide path working! {len(test)} results:")
            for row in test:
                print(f"   {row['date']} | {row['macro']} | {row['state']} | {row['zone']} | {row['change']}")
        else:
            print("⚠️ Path incomplete. Run 09_graphrag_seed.py first to seed all states.")

    driver.close()

    driver.close()

if __name__ == '__main__':
    fix_part_of_edges()