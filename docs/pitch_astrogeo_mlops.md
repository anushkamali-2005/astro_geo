# AstroGeo-Graphrag: Production infrastructure & MLOps Architecture
## Executive Pitch (Target: Industry Expert)

*Target Audience: Senior Engineers, Technical Directors, or MLOps Leads.*

---

## 1. The Executive Summary

"Sir, our team built AstroGeo—a multi-agent AI platform utilizing LangGraph and Neo4j to predict agricultural drought risks and space launch safety margins. 

While the data science team focused on the model logic, I led the **MLOps and Deployment layer**. My core focus was transforming a local, single-node research prototype into a highly available, cloud-agnostic production system. 

By containerizing the stack with Docker, orchestrating CI/CD pipelines, and integrating a robust observability suite, I improved our deployment times from hours of manual work to a 5-minute automated pipeline, achieving **99.9% uptime** and keeping our p95 API latency **under 500ms** under concurrent loads. I also implemented full traceability for our models using **MLflow** combined with **DVC**."

---

## 2. Architectural Decisions & Trade-offs

**(When speaking to an expert, be ready to defend *why* you chose your stack)**

### A. Compute & Deployment Strategy
*   **The Decision:** Containerized multi-environment strategy. We currently run our production loads on **Render** (for fast, auto-scaling PaaS benefits), but I also authored comprehensive **Kubernetes (K8s)** manifests.
*   **The 'Why' (Trade-off):** "We needed high rapid-iteration velocity today, which Render provides. However, I didn't want vendor lock-in. When we need to deploy on bare-metal or a private cloud for strict enterprise/government clients, our K8s manifests (deployments, namespace isolation, resource quotas) guarantee that we can migrate within hours, not weeks."

### B. Concurrency & ASGI Bottlenecks
*   **The Decision:** Deployed FastAPI on Gunicorn with Uvicorn workers.
*   **The 'Why':** "AstroGeo relies heavily on I/O-bound tasks—specifically multi-hop knowledge graph queries to Neo4j. I configured Gunicorn with 4 ASGI workers and a highly tuned Uvicorn thread pool (`THREAD_POOL_MAX_WORKERS=128`). This allows the event loop to yield correctly during heavy graph traversals, preventing the API from deadlocking under load."

### C. Connection Pooling
*   **The Decision:** Implementing Supabase (PostgreSQL) IPv4 Transaction Pooler.
*   **The 'Why':** "During stress testing, external API connections and rapid DB requests caused connection exhaustion. I implemented a transaction-level connection pooler, allowing 250+ concurrent requests to safely multiplex over a limited set of physical database connections without throwing 500 errors."

---

## 3. Creating the MLOps Lifecycle

"I ensured our models weren't just black boxes being manually shipped over SSH."

*   **Experiment Tracking:** I integrated **MLflow** locally and connected it to DagsHub. Every hyperparameter variation during the Vegetation NDVI Random Forest training is logged, alongside feature importance artifacts (SHAP values).
*   **Data Provenance:** We can't put high-resolution ERA5 satellite raster data in Git. I integrated **DVC (Data Version Control)** to sink our payloads to object storage. 
*   **The Result:** "If a production model drifts or acts unexpectedly, I can trace the exact Git commit back to the specific DVC data snapshot and the MLflow hyperparameter run. We have 100% reproducibility."

---

## 4. The "Shield Layer" (Observability & Resilience)

"A system isn't in production if you don't know it's failing."

*   **Metrics & Dashboards:** I instrumented the FastAPI backend to expose a `/metrics` endpoint. I configured **Prometheus** to scrape this on 15s intervals and deployed **Grafana** dashboards via K8s ConfigMaps. 
*   **Probes:** I instituted strict Liveness and Readiness HTTP probes. If an API worker deadlocks, K8s or Render will automatically drain and cycle the pod within 2 minutes.
*   **Protection:** I implemented `SlowAPI` rate-limiting middleware to aggressively cut off bad actors before they could exhaust our thread pool.

---

## 5. Hard Metrics (The ROI of My Work)

| Metric | Before Productionization | After Implementation |
| :--- | :--- | :--- |
| **API Latency (p95)** | Frequent timeouts > 5s | **< 500ms** (Under load of 200 concurrent reqs) |
| **Uptime Guarantee** | 0% (Single point of failure) | **99.9%** (Monitored via health checks) |
| **CI/CD Deployment** | Manual SCP / configuration | **< 5 minutes** (Automated GitHub Actions) |
| **Model Traceability** | Spreadsheets & memory | **Automated** DVC + MLflow Registry |

---

## 6. High-Level Q&A Prep (Expect These Questions)

*   **Sir:** *"Why use DVC and MLflow when cloud providers like AWS SageMaker exist?"*
    *   **Response:** "Cost boundaries and cloud-agnosticism. As a high-efficiency team, we wanted to avoid massive vendor lock-in and high hourly SageMaker billing. DVC backed by S3 (via DagsHub) gives us the exact same reproducibility at a fraction of the operational cost, allowing us to deploy anywhere."
*   **Sir:** *"Did you test the failure modes of your Prometheus setup?"*
    *   **Response:** "Yes, Prometheus is decoupled from the main event loop. Since we use the Prometheus FastAPI Instrumentator, it simply increments memory counters synchronously and serves them asynchronously. If Prometheus goes down, the API stays up."
*   **Sir:** *"How do you handle schema migrations in an auto-scaling environment?"*
    *   **Response:** "Migrations act as a blocker. I enforced a rule where DB migrations must run sequentially before rolling out the new API containers to prevent older pods from entering an invalid state against a mutated schema."

---

*Contact: AstroGeo MLOps & Deployment Lead.*
