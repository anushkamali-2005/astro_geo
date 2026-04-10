from fastapi import FastAPI
from backend.routers import iss, asteroids
from backend.config import settings
from backend.orchestrator.langgraph_agent import run_query
from fastapi import HTTPException
import time

app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION
)

# Include routers
app.include_router(iss.router)
app.include_router(asteroids.router)

from pydantic import BaseModel
from typing import Optional
from backend.agents.astronomy.astronomy_agent import AstronomyAgent
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage
import os
import hashlib
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

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


# ── GET /api/verify/batch/recent ─────────────────────────────
@app.get("/api/verify/batch/recent", response_model=BatchVerificationResult)
async def verify_recent_predictions(limit: int = 10):
    """
    Verifies the N highest-risk predictions in bulk.
    Powers the Recent Predictions list in the Verify UI.
    """
    engine = _get_engine()
    try:
        with engine.connect() as conn:
            rows = conn.execute(text("""
                SELECT asteroid_id,
                       risk_category,
                       improved_risk_score,
                       is_anomaly,
                       anomaly_score,
                       cluster,
                       verification_hash
                FROM astronomy.asteroid_ml_predictions
                ORDER BY improved_risk_score DESC
                LIMIT :limit
            """), {"limit": limit}).fetchall()

        results  = []
        verified = 0
        failed   = 0

        for row in rows:
            r     = dict(row._mapping)
            valid = (recompute_hash(r) == (r.get('verification_hash') or ''))
            if valid:
                verified += 1
            else:
                failed += 1
            results.append({
                "asteroid_id":         r['asteroid_id'],
                "risk_category":       r.get('risk_category') or '',
                "improved_risk_score": float(r.get('improved_risk_score') or 0),
                "is_anomaly":          bool(r.get('is_anomaly')),
                "verification_status": "Verified" if valid else "MISSING_HASH",
                "hash_preview":        (r.get('verification_hash') or '')[:16] + "...",
            })

        return BatchVerificationResult(
            total=    len(results),
            verified= verified,
            failed=   failed,
            results=  results,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        engine.dispose()