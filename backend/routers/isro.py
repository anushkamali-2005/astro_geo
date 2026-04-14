from fastapi import APIRouter, HTTPException
import httpx
import asyncio
from datetime import datetime
from backend.config import settings

router = APIRouter(prefix="/api/isro", tags=["ISRO Tracking"])

ISRO_FLEET = [
    {'id': 'CARTOSAT3',  'norad_id': 44804, 'name': 'Cartosat-3', 'type': 'Earth Observation'},
    {'id': 'GSAT24',     'norad_id': 52935, 'name': 'GSAT-24', 'type': 'Communication'},
    {'id': 'RISAT2B',    'norad_id': 44233, 'name': 'RISAT-2B', 'type': 'SAR'},
    {'id': 'EOS04',      'norad_id': 51656, 'name': 'EOS-04', 'type': 'SAR'},
    {'id': 'INSAT3DS',   'norad_id': 58988, 'name': 'INSAT-3DS', 'type': 'Meteorology'},
]

NAVIC_FLEET = [
    {'id': 'IRNSS-1A', 'norad_id': 39199, 'name': 'IRNSS-1A', 'type': 'Navigation'},
    {'id': 'IRNSS-1B', 'norad_id': 39635, 'name': 'IRNSS-1B', 'type': 'Navigation'},
    {'id': 'IRNSS-1C', 'norad_id': 40269, 'name': 'IRNSS-1C', 'type': 'Navigation'},
    {'id': 'IRNSS-1D', 'norad_id': 40547, 'name': 'IRNSS-1D', 'type': 'Navigation'},
    {'id': 'IRNSS-1E', 'norad_id': 41241, 'name': 'IRNSS-1E', 'type': 'Navigation'},
    {'id': 'IRNSS-1F', 'norad_id': 41384, 'name': 'IRNSS-1F', 'type': 'Navigation'},
    {'id': 'IRNSS-1G', 'norad_id': 41469, 'name': 'IRNSS-1G', 'type': 'Navigation'},
    {'id': 'IRNSS-1I', 'norad_id': 43286, 'name': 'IRNSS-1I', 'type': 'Navigation'},
    {'id': 'NVS-01',   'norad_id': 56644, 'name': 'NVS-01',   'type': 'Navigation'},
]

# Simple in-memory cache to prevent hammering N2YO API during re-renders
_cache = {
    "timestamp": None,
    "data": None
}
CACHE_TTL = 30  # seconds

async def fetch_satellite_position(client: httpx.AsyncClient, sat: dict):
    # Base observer coordinates (Sriharikota: 13.72, 80.23, 0m altitude)
    # 1 second of prediction is enough to get the instant "live" position
    url = (
        f"https://api.n2yo.com/rest/v1/satellite/positions/"
        f"{sat['norad_id']}/13.72/80.23/0/1/"
        f"?apiKey={settings.N2YO_API_KEY}"
    )
    
    try:
        response = await client.get(url, timeout=5.0)
        response.raise_for_status()
        data = response.json()
        
        if "positions" in data and len(data["positions"]) > 0:
            pos = data["positions"][0]
            
            # Simple AI health score simulation (realistic static boundaries based on mission age)
            base_health = 98 if sat['id'] == 'INSAT3DS' else (95 if sat['id'] == 'Cartosat3' else 85)
            health = min(100, max(0, base_health + (hash(sat['name']) % 10)))
            
            return {
                "id": sat["id"],
                "norad_id": sat["norad_id"],
                "name": sat["name"],
                "type": sat["type"],
                "latitude": pos["satlatitude"],
                "longitude": pos["satlongitude"],
                "altitude_km": pos["sataltitude"],
                "azimuth": pos["azimuth"],
                "elevation": pos["elevation"],
                "eclipsed": pos["eclipsed"],
                "timestamp": pos["timestamp"],
                "health": health
            }
    except Exception as e:
        print(f"[ISRO Fleet] Failed to fetch {sat['name']}: {e}")
        
    return None

@router.get("/fleet")
async def get_isro_fleet():
    """
    Fetches live positions for the active ISRO tracking fleet.
    Uses N2YO API with a 30-second TTL cache to avoid rate limits.
    """
    global _cache
    now = datetime.now()
    
    # Return cached if valid
    if _cache["data"] and _cache["timestamp"] and (now - _cache["timestamp"]).total_seconds() < CACHE_TTL:
        return _cache["data"]
        
    async with httpx.AsyncClient() as client:
        # Fetch all satellites concurrently
        tasks = [fetch_satellite_position(client, sat) for sat in ISRO_FLEET]
        results = await asyncio.gather(*tasks)
        
    # Filter out failures
    valid_results = [r for r in results if r is not None]
    
    # Sort for consistent display (EO/SAR first, then Comm)
    valid_results.sort(key=lambda x: (x['altitude_km'], x['name']))
    
    if valid_results:
        _cache["timestamp"] = now
        _cache["data"] = valid_results
        
    return valid_results

_navic_cache = {
    "timestamp": None,
    "data": None
}

@router.get("/navic")
async def get_navic_fleet():
    """
    Fetches live positions for the active NavIC constellation.
    Uses N2YO API with a 30-second TTL cache to avoid rate limits.
    """
    global _navic_cache
    now = datetime.now()
    
    # Return cached if valid
    if _navic_cache["data"] and _navic_cache["timestamp"] and (now - _navic_cache["timestamp"]).total_seconds() < CACHE_TTL:
        return _navic_cache["data"]
        
    async with httpx.AsyncClient() as client:
        # Fetch all satellites concurrently
        tasks = [fetch_satellite_position(client, sat) for sat in NAVIC_FLEET]
        results = await asyncio.gather(*tasks)
        
    # Filter out failures
    valid_results = [r for r in results if r is not None]
    
    # Sort for consistent display
    valid_results.sort(key=lambda x: x['name'])
    
    if valid_results:
        _navic_cache["timestamp"] = now
        _navic_cache["data"] = valid_results
        
    return valid_results

@router.get("/archive")
async def get_chandrayaan_archive():
    """
    Returns actual historical facts for the Chandrayaan missions.
    Data is static as it represents true mission history.
    """
    return {
        "chandrayaan_1": {
            "name": "Chandrayaan-1",
            "year": 2008,
            "status": "Completed",
            "key_finding": "Discovered water molecules (H2O and OH) on the lunar surface.",
            "duration": "312 days"
        },
        "chandrayaan_2": {
            "name": "Chandrayaan-2",
            "year": 2019,
            "status": "Orbiter Operational",
            "key_finding": "Orbiter mapped lunar surface with high-resolution cameras; Lander contact lost.",
            "duration": "Ongoing (Orbiter)"
        },
        "chandrayaan_3": {
            "name": "Chandrayaan-3",
            "year": 2023,
            "status": "Historic Success",
            "lander": {
                "name": "Vikram",
                "coordinates": "69.373° S, 32.319° E",
                "landing_date": "2023-08-23",
                "status": "Hibernating"
            },
            "rover": {
                "name": "Pragyan",
                "traverse_distance_m": 101.4,
                "status": "Hibernating"
            },
            "findings": [
                "Confirmed presence of Sulfur (S) near the south pole via LIBS.",
                "Measured plasma density near lunar surface.",
                "Recorded thermal profile of lunar topsoil up to 10cm depth."
            ]
        }
    }
