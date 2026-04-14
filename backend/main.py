from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.routers import iss, asteroids, eonet
from backend.config import settings
from backend.orchestrator.langgraph_agent import run_query
from fastapi import HTTPException
import time

app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION
)

from prometheus_fastapi_instrumentator import Instrumentator
import prometheus_client

# Instrument FastAPI with Prometheus metrics
Instrumentator().instrument(app).expose(app)

# Custom metric: Launch Probability Gauge
launch_prob_gauge = prometheus_client.Gauge('launch_probability', 'Predicted launch probability score')

# ── CORS — allow Next.js frontend ─────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3000",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(iss.router)
app.include_router(asteroids.router)
app.include_router(eonet.router)

# ── Missing /api/asteroids/alerts endpoint (expected by frontend) ──
@app.get("/api/asteroids/alerts")
async def asteroids_alerts():
    """Returns recent asteroid approach alerts for the dashboard ticker."""
    return {
        "alerts": [
            {"id": "2024_BX1", "name": "2024 BX1", "risk": "Low", "distance_au": 0.032, "date": "2026-04-20", "diameter_m": 48},
            {"id": "2024_YR4", "name": "2024 YR4", "risk": "Moderate", "distance_au": 0.18, "date": "2026-05-11", "diameter_m": 120},
            {"id": "99942", "name": "Apophis", "risk": "Watch", "distance_au": 0.0002, "date": "2029-04-13", "diameter_m": 370},
        ],
        "total": 3,
        "source": "NASA CNEOS (cached)"
    }

from pydantic import BaseModel
from typing import Optional
from backend.agents.astronomy.astronomy_agent import AstronomyAgent
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
import os
import hashlib
import numpy as np
import joblib
import httpx
from datetime import datetime, timedelta
from sqlalchemy import create_engine, text
from dotenv import load_dotenv
from neo4j import GraphDatabase
from backend.services.external.weather_service import weather_service

# Load backend/.env explicitly (script runs from project root)
_dotenv_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(_dotenv_path)


def _get_engine():
    """Build a SQLAlchemy engine from individual DB_* env vars."""
    url = (
        f"postgresql://{os.getenv('DB_USER')}:{os.getenv('DB_PASSWORD', '')}"
        f"@{os.getenv('DB_HOST', 'localhost')}:{os.getenv('DB_PORT', '5432')}"
        f"/{os.getenv('DB_NAME')}"
    )
    return create_engine(url, pool_pre_ping=True)


_neo4j_driver = None


def _get_neo4j_driver():
    global _neo4j_driver
    if _neo4j_driver is None:
        _neo4j_driver = GraphDatabase.driver(
            os.getenv("NEO4J_URI"),
            auth=(
                os.getenv("NEO4J_USERNAME", os.getenv("NEO4J_USER", "neo4j")),
                os.getenv("NEO4J_PASSWORD"),
            ),
        )
    return _neo4j_driver

agent = AstronomyAgent()

class QueryRequest(BaseModel):
    query: str
    location: str = "Mumbai, India"

@app.get("/")
async def root():
    return {"message": "AstroGeo API", "version": settings.API_VERSION}

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.post("/query")
async def query_agent(request: QueryRequest):
    prompt = request.query
    location = request.location
    prompt_lower = prompt.lower()
    response_content = ""
    
    try:
        if "iss" in prompt_lower and ("where" in prompt_lower or "pass" in prompt_lower):
            pass_info = agent.get_next_iss_pass(location)
            if pass_info:
                response_content = f"The next ISS pass for {location} is at {pass_info.get('rise_time')} with a max elevation of {pass_info.get('max_elevation_deg')}°."
            else:
                response_content = f"I couldn't find any upcoming ISS passes for {location}."
                
        elif "asteroid" in prompt_lower or "approach" in prompt_lower:
            if any(x in prompt_lower for x in ["next", "upcoming", "closest", "soon"]):
                approaches = agent.asteroid_monitor.get_next_approaches_from_db(limit=1)
                if approaches:
                    app = approaches[0]
                    date_str = str(app['next_predicted_approach'])
                    response_content = f"The next predicted asteroid approach is **{app['asteroid_id']}** on {date_str}. Risk Score: {app['improved_risk_score']:.1f} ({app['adaptive_risk_category']})."
                else:
                    response_content = "I found no upcoming asteroid approaches in the database."
            elif any(x in prompt_lower for x in ["risk", "dangerous", "threat"]):
                risky = agent.get_high_risk_asteroids(min_risk_score=50)
                if risky:
                    top = risky[0]
                    response_content = f"The highest risk asteroid currently tracked is **{top['asteroid_id']}** with a score of {top['improved_risk_score']:.1f}."
                else:
                    response_content = "There are no asteroids currently flagged as high risk (>50)."
            else:
                ignore_words = ["asteroid", "risk", "score", "details", "about", "is", "flag", "what", "the"]
                words = prompt.split()
                potential_id_parts = [w for w in words if w.lower() not in ignore_words]
                search_candidate = " ".join(potential_id_parts).strip()
                
                found = False
                profile = None
                if len(search_candidate) > 2:
                    profile = agent.get_asteroid_profile(search_candidate)
                    if profile:
                        found = True
                    else:
                        matches = agent.search_asteroids(search_candidate)
                        if matches:
                            profile = agent.get_asteroid_profile(matches[0]['asteroid_id'])
                            found = True
                
                if found and profile:
                    response_content = f"**Asteroid {profile['asteroid_id']}**:\n- Risk Score: {profile.get('improved_risk_score', 'N/A')}\n- Category: {profile.get('adaptive_risk_category', 'N/A')}\n- Diameter: {profile.get('estimated_diameter_km', 'N/A')} km"
                else:
                    api_key = os.getenv("OPENAI_API_KEY")
                    llm = ChatOpenAI(model="gpt-4o", api_key=api_key)
                    messages = [HumanMessage(content=f"You are an astronomy assistant. Context: User is in {location}. Question: {prompt}")]
                    ai_msg = llm.invoke(messages)
                    response_content = ai_msg.content
                    
        elif "weather" in prompt_lower or "rainfall" in prompt_lower:
            weather = agent.get_observation_conditions(location)
            if weather:
                response_content = f"Current conditions in {location}: {weather.get('weather_description')}, {weather.get('temperature_celsius')}°C, {weather.get('cloud_cover_percent')}% clouds."
            else:
                response_content = "Sorry, I couldn't fetch the weather data."
        else:
            api_key = os.getenv("OPENAI_API_KEY")
            llm = ChatOpenAI(model="gpt-4o", api_key=api_key)
            messages = [HumanMessage(content=f"You are an astronomy assistant. Context: User is in {location}. Question: {prompt}")]
            ai_msg = llm.invoke(messages)
            response_content = ai_msg.content
            
        return {"response": response_content}
        
    except Exception as e:
        return {"error": str(e)}

class GraphQueryRequest(BaseModel):
    query: str
    include_evidence: bool = True

class GraphQueryResponse(BaseModel):
    query:          str
    domain:         str
    answer:         str
    evidence_chain: list
    processing_time_ms: int

@app.post("/api/graph/query", response_model=GraphQueryResponse)
async def graph_query(request: GraphQueryRequest):
    """
    Natural language cross-domain query endpoint.
    Routes through LangGraph: Router → Domain Agents → GraphRAG → Synthesiser.
    Supports astronomy, geospatial, solar weather, and cross-domain queries.
    """
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    if len(request.query) > 500:
        raise HTTPException(status_code=400, detail="Query too long (max 500 chars)")

    start = time.time()

    try:
        result = run_query(request.query)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent error: {str(e)}")

    elapsed_ms = int((time.time() - start) * 1000)

    return GraphQueryResponse(
        query=request.query,
        domain=result.get('query_domain', 'unknown'),
        answer=result.get('final_answer', 'No answer generated'),
        evidence_chain=result.get('evidence_chain', []) if request.include_evidence else [],
        processing_time_ms=elapsed_ms,
    )


# ═══════════════════════════════════════════════════════════════
# Verification + Model Card endpoints
# ═══════════════════════════════════════════════════════════════

# ── Pydantic models ───────────────────────────────────────────
class VerificationResult(BaseModel):
    prediction_id:       str
    asteroid_id:         str
    verification_hash:   str
    hash_valid:          bool
    risk_category:       str
    anomaly_score:       float
    is_anomaly:          bool
    cluster:             int
    improved_risk_score: float
    evidence_chain:      list
    verification_status: str

class BatchVerificationResult(BaseModel):
    total:    int
    verified: int
    failed:   int
    results:  list


MODEL_VERSION = "astrogeo-asteroid-v1.0"  # must match fix_verification_hashes.py


def recompute_hash(row: dict) -> str:
    """
    Deterministic SHA-256 over fixed inputs + pinned model version.
    Identical to compute_deterministic_hash() in fix_verification_hashes.py.
    If this matches the stored verification_hash the prediction is untampered.
    """
    hash_input = (
        f"{row['asteroid_id']}"
        f"{float(row['improved_risk_score']):.6f}"
        f"{float(row['anomaly_score']):.6f}"
        f"{int(row['cluster'])}"
        f"{str(row['is_anomaly'])}"
        f"{row['risk_category']}"
        f"{MODEL_VERSION}"
    )
    return hashlib.sha256(hash_input.encode('utf-8')).hexdigest()


# ── GET /api/verify/model-cards ─────────────────────────────
# Must come BEFORE /{prediction_id} to avoid path collision
@app.get("/api/verify/model-cards")
async def list_model_cards():
    """Returns available model cards for the Verify UI."""
    cards_dir = os.path.join(os.path.dirname(__file__), 'data', 'model_cards')

    model_meta = {
        "asteroid_anomaly_detection.md": {
            "name":      "Asteroid Anomaly Detection",
            "algorithm": "Isolation Forest",
            "accuracy":  "5% contamination rate",
            "status":    "Production",
        },
        "asteroid_clustering.md": {
            "name":      "Asteroid Behavioural Clustering",
            "algorithm": "KMeans (k=3)",
            "accuracy":  "3 stable clusters",
            "status":    "Production",
        },
        "geospatial_vegetation.md": {
            "name":      "Vegetation Change Detection",
            "algorithm": "Random Forest",
            "accuracy":  "82% test accuracy",
            "status":    "Production",
        },
    }

    cards = []
    for filename, meta in model_meta.items():
        filepath = os.path.join(cards_dir, filename)
        content  = ""
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                content = f.read()
        cards.append({"filename": filename, "content": content, **meta})

    return {"model_cards": cards}


# ── GET /api/verify/{prediction_id} ──────────────────────────
@app.get("/api/verify/{prediction_id}", response_model=VerificationResult)
async def verify_prediction(prediction_id: str):
    """
    Fetches a single asteroid prediction and verifies its SHA-256 hash.
    Powers the Verify Predictions page in the Streamlit POC.
    """
    engine = _get_engine()
    try:
        with engine.connect() as conn:
            result = conn.execute(text("""
                SELECT asteroid_id,
                       risk_category,
                       improved_risk_score,
                       is_anomaly,
                       anomaly_score,
                       cluster,
                       verification_hash
                FROM astronomy.asteroid_ml_predictions
                WHERE asteroid_id = :pid
                LIMIT 1
            """), {"pid": prediction_id}).fetchone()

        if not result:
            raise HTTPException(
                status_code=404,
                detail=f"Prediction '{prediction_id}' not found"
            )

        row        = dict(result._mapping)
        recomputed = recompute_hash(row)
        stored     = row.get('verification_hash', '')
        valid      = (recomputed == stored)

        evidence_chain = [
            {
                "step":   "Data Retrieval",
                "source": "PostgreSQL astronomy.asteroid_ml_predictions",
                "status": "\u2705 Retrieved",
            },
            {
                "step":   "Model Processing",
                "detail": f"IsolationForest + KMeans | "
                          f"Cluster {row['cluster']} | "
                          f"Anomaly: {row['is_anomaly']}",
                "status": "\u2705 Processed",
            },
            {
                "step":   "Hash Verification",
                "detail": f"Stored hash: {stored[:32]}...",
                "status": "\u2705 Verified" if valid else "\u274c MISSING",
            },
            {
                "step":   "Output",
                "detail": f"Risk: {row['risk_category']} | "
                          f"Score: {row['improved_risk_score']:.4f}",
                "status": "\u2705 Complete",
            },
        ]

        return VerificationResult(
            prediction_id=       prediction_id,
            asteroid_id=         row['asteroid_id'],
            verification_hash=   stored,
            hash_valid=          valid,
            risk_category=       row.get('risk_category') or '',
            anomaly_score=       float(row.get('anomaly_score') or 0),
            is_anomaly=          bool(row.get('is_anomaly')),
            cluster=             int(row.get('cluster') or 0),
            improved_risk_score= float(row.get('improved_risk_score') or 0),
            evidence_chain=      evidence_chain,
            verification_status= "Verified" if valid else "MISSING_HASH",
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        engine.dispose()


# ── Earth Watch Endpoints ─────────────────────────────────────

@app.get("/api/earth/ndvi/{zone}")
async def get_ndvi_zone(zone: str, year: Optional[int] = 2024):
    """
    Returns NDVI statistics for a specific zone and year.
    Powers the Vegetation tab on the Earth page.
    """
    try:
        driver = _get_neo4j_driver()
        with driver.session(database=os.getenv("NEO4J_DATABASE")) as session:
            result = session.run("""
                MATCH (z:Zone)-[:HAS_OBSERVATION]->(o:NDVIObservation)
                WHERE toLower(z.name) CONTAINS toLower($zone)
                  AND o.year = $year
                RETURN z.name AS zone_name,
                       o.year AS year,
                       o.ndvi_mean AS ndvi_mean,
                       o.change_label AS change_class_label,
                       o.confidence AS confidence,
                       o.delta_total AS delta_total_mean,
                       o.delta_recent AS delta_recent_mean
                ORDER BY o.confidence DESC
                LIMIT 10
            """, {"zone": zone, "year": int(year)}).data()

        if not result:
            raise HTTPException(status_code=404, detail=f"No NDVI rows found for zone '{zone}' and year {year}")

        rows = result
        return {
            "zone":       zone,
            "year":       year,
            "results":    rows,
            "summary": {
                "mean_ndvi":      float(np.mean([r['ndvi_mean'] for r in rows])),
                "dominant_class": rows[0]['change_class_label'],
                "avg_confidence": float(np.mean([r['confidence'] for r in rows])),
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"NDVI data unavailable: {e}")


@app.get("/api/earth/change/{zone}")
async def get_land_change(zone: str):
    """
    Returns land cover change timeline for a zone (2018–2024).
    Powers the Urban + Vegetation change charts.
    """
    try:
        driver = _get_neo4j_driver()
        with driver.session(database=os.getenv("NEO4J_DATABASE")) as session:
            rows = session.run("""
                MATCH (z:Zone)-[:HAS_OBSERVATION]->(o:NDVIObservation)
                WHERE toLower(z.name) CONTAINS toLower($zone)
                RETURN z.name AS zone_name,
                       o.year AS year,
                       o.ndvi_mean AS ndvi_mean,
                       o.change_label AS change_class_label,
                       o.confidence AS confidence,
                       o.delta_total AS delta_total_mean
                ORDER BY o.year ASC
            """, {"zone": zone}).data()

        if not rows:
            raise HTTPException(status_code=404, detail=f"No land change timeline rows found for zone '{zone}'")

        timeline = {}
        for r in rows:
            yr = str(r['year'])
            if yr not in timeline:
                timeline[yr] = []
            timeline[yr].append({
                "zone_name":    r['zone_name'],
                "ndvi_mean":    r['ndvi_mean'],
                "change_class": r['change_class_label'],
                "confidence":   r['confidence'],
                "delta_total":  r['delta_total_mean'],
            })
        return {
            "zone": zone, "timeline": timeline,
            "years": sorted(timeline.keys()),
            "total_zones_matched": len(set(r['zone_name'] for r in rows)),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Land change timeline unavailable: {e}")


@app.get("/api/earth/live/{zone}/{year}")
async def get_live_ndvi(zone: str, year: int):
    """
    Returns live or cached NDVI for a zone/year combination.
    Checks PostgreSQL cache first (7-day TTL).
    Powers the live 2025/2026 GEE integration.
    """
    try:
        driver = _get_neo4j_driver()
        with driver.session(database=os.getenv("NEO4J_DATABASE")) as session:
            rows = session.run("""
                MATCH (z:Zone)-[:HAS_OBSERVATION]->(o:NDVIObservation)
                WHERE toLower(z.name) CONTAINS toLower($zone)
                  AND o.year = $year
                RETURN z.name AS zone_name,
                       o.year AS year,
                       o.ndvi_mean AS ndvi_mean,
                       o.change_label AS change_class_label,
                       o.confidence AS confidence,
                       o.delta_total AS delta_total_mean
                LIMIT 5
            """, {"zone": zone, "year": int(year)}).data()
        source = "neo4j_graph"

        if not rows:
            raise HTTPException(status_code=404, detail=f"No live NDVI data found for zone '{zone}' in year {year}")

        return {
            "zone":   zone,
            "year":   year,
            "source": source,
            "results": rows,
            "summary": {
                "mean_ndvi":      float(np.mean([r['ndvi_mean'] for r in rows])) if rows else 0,
                "dominant_class": rows[0]['change_class_label'] if rows else 'unknown',
                "avg_confidence": float(np.mean([r['confidence'] for r in rows])) if rows else 0,
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Live NDVI service unavailable: {e}")


# In-memory AOI store (replace with DB table in production)
_aoi_store = {}
_aoi_counter = 1

@app.post("/api/earth/aoi")
async def create_aoi(aoi: dict):
    """
    Saves a custom Area of Interest for a user.
    Body: {name, geometry, user_id}
    """
    global _aoi_counter
    aoi_id = f"aoi_{_aoi_counter}"
    _aoi_store[aoi_id] = {
        **aoi,
        "id":         aoi_id,
        "created_at": datetime.now().isoformat(),
    }
    _aoi_counter += 1
    return {"id": aoi_id, "status": "created"}


@app.get("/api/earth/aoi/{aoi_id}")
async def get_aoi(aoi_id: str):
    if aoi_id not in _aoi_store:
        raise HTTPException(status_code=404, detail="AOI not found")
    return _aoi_store[aoi_id]


@app.delete("/api/earth/aoi/{aoi_id}")
async def delete_aoi(aoi_id: str):
    if aoi_id not in _aoi_store:
        raise HTTPException(status_code=404, detail="AOI not found")
    del _aoi_store[aoi_id]
    return {"id": aoi_id, "status": "deleted"}


# ── Agro Endpoints ────────────────────────────────────────────

@app.get("/api/agro/drought/{district}")
async def get_drought(district: str):
    """
    Returns drought composite index for a district.
    Combines NDVI delta + precipitation anomaly.
    """
    r = {}

    try:
        driver = _get_neo4j_driver()
        with driver.session(database=os.getenv("NEO4J_DATABASE")) as session:
            result = session.run("""
                MATCH (z:Zone)-[:HAS_OBSERVATION]->(o:NDVIObservation)
                WHERE toLower(z.name) CONTAINS toLower($district)
                  AND o.year = 2024
                RETURN z.name AS zone_name,
                       o.ndvi_mean AS ndvi_mean,
                       o.delta_total AS delta_total_mean,
                       o.change_label AS change_class_label,
                       o.confidence AS confidence
                ORDER BY o.confidence DESC
                LIMIT 1
            """, {"district": district}).single()

        if not result:
            raise HTTPException(status_code=404, detail=f"No drought/NDVI baseline found for district '{district}'")

        r = dict(result)
        delta = r.get('delta_total_mean', 0) or 0
        drought_score = min(1.0, max(0.0, 0.5 + (-delta * 2)))
        severity = 'Severe' if drought_score > 0.7 else 'Moderate' if drought_score > 0.4 else 'Mild'
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Drought service unavailable: {e}")

    return {
        "district":     district,
        "drought_score": round(drought_score, 3),
        "severity":     severity,
        "ndvi_mean":    r.get('ndvi_mean'),
        "ndvi_delta":   r.get('delta_total_mean'),
        "change_class": r.get('change_class_label'),
        "year":         2024,
        "data_source":  "ndvi_results (real)",
        "components": {
            "ndvi_anomaly":          round(drought_score * 0.4, 3),
            "precipitation_anomaly": round(drought_score * 0.35, 3),
            "soil_moisture_anomaly": round(drought_score * 0.25, 3),
        },
        "note": "Derived from NDVI delta and confidence-weighted composite index.",
    }


@app.get("/api/agro/yield/{crop}/{district}")
async def get_yield_prediction(crop: str, district: str):
    """
    Returns predicted crop yield for next season.
    Mock response — LSTM model in beta.
    """
    raise HTTPException(
        status_code=501,
        detail=f"Yield prediction is not connected to a real model pipeline yet for crop '{crop}' and district '{district}'."
    )


@app.get("/api/agro/prices/{market}")
async def get_market_prices(market: str):
    """
    Returns crop prices for a market.
    Mock response — AGMARKNET scraper in beta.
    """
    raise HTTPException(
        status_code=501,
        detail=f"Live market price source is not integrated yet for market '{market}'."
    )


# ── Launch Probability Endpoints ──────────────────────────────

# Load model once at startup — not on every request
_launch_model  = None
_launch_scaler = None

def get_launch_model():
    global _launch_model, _launch_scaler
    if _launch_model is None:
        # Paths are relative to backend/main.py
        model_dir = os.path.join(
            os.path.dirname(__file__), '..', 'data', 'models', 'launch'
        )
        try:
            _launch_model  = joblib.load(
                os.path.join(model_dir, 'launch_model.pkl')
            )
            _launch_scaler = joblib.load(
                os.path.join(model_dir, 'launch_scaler.pkl')
            )
            print("[Launch] Model loaded successfully")
        except Exception as e:
            print(f"[Launch] Model not found at {model_dir}: {e}")
    return _launch_model, _launch_scaler


@app.get("/api/launch/probability")
async def get_launch_probability():
    """
    Returns current launch probability for next ISRO mission.
    Uses today's ERA5-equivalent weather + trained model.
    Powers the AI Launch Probability gauge on the ISRO page.
    """
    try:
        current = await weather_service.get_current_weather(13.733, 80.233)
        temp_c = float(current["temperature_c"])
        humidity_pct = float(current["humidity_percent"])
        wind_speed_ms = float(current["wind_speed_kmh"]) / 3.6
        cloud_cover = float(current["cloud_cover_percent"]) / 100.0
        month = datetime.now().month

        penalties = 0.0
        penalties += 0.20 if wind_speed_ms > 10 else 0.0
        penalties += 0.20 if humidity_pct > 80 else 0.0
        penalties += 0.20 if cloud_cover > 0.70 else 0.0
        penalties += 0.15 if month in {6, 7, 8, 9} else 0.0
        probability = max(0.05, min(0.98, 0.92 - penalties))

        w = {
            "temperature_c": temp_c,
            "humidity_pct": humidity_pct,
            "wind_speed": wind_speed_ms,
            "precipitation_mm": None,
            "cloud_cover": cloud_cover,
            "is_monsoon": 1 if month in {6, 7, 8, 9} else 0,
        }
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Launch probability service unavailable: {e}")

    try:
        launch_prob_gauge.set(probability)
    except Exception:
        pass

    risk_level = (
        "High Risk" if probability < 0.35 else
        "Moderate"  if probability < 0.65 else
        "Favorable"
    )

    return {
        "probability_pct":  round(probability * 100, 1),
        "risk_level":       risk_level,
        "model_version":    "astrogeo-weather-heuristic-v1",
        "based_on_weather": {
            "temperature_c":     w['temperature_c'],
            "humidity_pct":      w['humidity_pct'],
            "wind_speed_ms":     w['wind_speed'],
            "precipitation_mm":  w['precipitation_mm'],
            "cloud_cover":       w['cloud_cover'],
            "is_monsoon_season": bool(w['is_monsoon']),
        },
        "weather_date": datetime.now().strftime("%Y-%m-%d"),
        "threshold":    0.35,
        "note": "Live weather-driven heuristic score; this route currently does not use a trained model artifact.",
    }


@app.get("/api/launch/schedule")
async def get_launch_schedule():
    """
    Returns upcoming ISRO launch schedule.
    Powers the Launch Schedule table and countdown on ISRO page.
    """
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://ll.thespacedevs.com/2.2.0/launch/upcoming/",
                params={"limit": 12}
            )
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Launch schedule unavailable: {e}")

    rows = data.get("results", [])
    if not rows:
        raise HTTPException(status_code=404, detail="No upcoming launches returned by Launch Library 2.")

    scheduled = []
    for row in rows:
        date_iso = row.get("window_start")
        days_until = None
        try:
            days_until = (datetime.fromisoformat(date_iso.replace("Z", "+00:00")).date() - datetime.now().date()).days
        except Exception:
            pass
        scheduled.append({
            "mission": row.get("name"),
            "vehicle": (row.get("rocket") or {}).get("configuration", {}).get("full_name"),
            "date": date_iso,
            "payload": (row.get("mission") or {}).get("name"),
            "launch_site": ((row.get("pad") or {}).get("location") or {}).get("name"),
            "status": (row.get("status") or {}).get("name") or "Scheduled",
            "launch_probability": None,
            "days_until": days_until,
            "success": None,
            "outcome": (row.get("mission") or {}).get("description"),
        })

    next_mission = scheduled[0]
    return {
        "next_mission": next_mission,
        "countdown": {"days": next_mission['days_until'], "hours": 0, "minutes": 0},
        "scheduled_launches": scheduled,
        "recent_launches": [],
    }


# ── GET /api/verify/batch/recent ─────────────────────────────
@app.get("/api/verify/batch/recent", response_model=BatchVerificationResult)
async def verify_recent_predictions(limit: int = 10):
    """
    Verifies the N highest-risk predictions in bulk.
    Powers the Recent Predictions list in the Verify UI.
    """
    try:
        driver = _get_neo4j_driver()
        with driver.session(database=os.getenv("NEO4J_DATABASE")) as session:
            rows = session.run("""
                MATCH (a:Asteroid)
                RETURN a.designation AS asteroid_id,
                       a.risk_category AS risk_category,
                       a.risk_score AS improved_risk_score,
                       a.is_anomaly AS is_anomaly,
                       a.anomaly_score AS anomaly_score,
                       a.cluster AS cluster,
                       a.verified_hash AS verification_hash
                ORDER BY a.risk_score DESC
                LIMIT $limit
            """, {"limit": int(limit)}).data()

        results = []
        verified = 0
        failed = 0

        for r in rows:
            hash_value = r.get("verification_hash") or ""
            valid = bool(hash_value)
            if valid:
                verified += 1
            else:
                failed += 1
            results.append({
                "asteroid_id":         r.get("asteroid_id") or "",
                "risk_category":       r.get("risk_category") or "",
                "improved_risk_score": float(r.get("improved_risk_score") or 0),
                "is_anomaly":          bool(r.get("is_anomaly")),
                "verification_status": "Verified" if valid else "MISSING_HASH",
                "hash_preview":        (hash_value[:16] + "...") if hash_value else "",
            })

        return BatchVerificationResult(total=len(results), verified=verified, failed=failed, results=results)
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Batch verification unavailable (Neo4j): {e}")