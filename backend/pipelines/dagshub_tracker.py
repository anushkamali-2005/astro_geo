"""
dagshub_tracker.py — Shared DagsHub + MLflow tracking utility for AstroGeo pipelines.

Usage:
    from dagshub_tracker import init_dagshub_tracking

    with init_dagshub_tracking(
        experiment_name="astrogeo-vegetation-ndvi",
        run_name="train_rf_v1",
    ):
        mlflow.log_param("n_estimators", 200)
        mlflow.log_metric("accuracy", 0.82)
        mlflow.sklearn.log_model(model, "model")
"""
import os
import sys

# Fix Windows cp1252 crash when MLflow prints emoji/unicode
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

from contextlib import nullcontext
from dotenv import load_dotenv

# Load .env from backend/ directory (or project root)
_backend_env = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
_root_env = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), ".env")
for _p in [_backend_env, _root_env]:
    if os.path.exists(_p):
        load_dotenv(_p)


def init_dagshub_tracking(
    experiment_name: str,
    run_name: str,
    tags: dict | None = None,
):
    """
    Initialize DagsHub + MLflow tracking and return an active run context.

    Required env vars:
        DAGSHUB_USERNAME, DAGSHUB_REPO, DAGSHUB_TOKEN

    Returns:
        mlflow.ActiveRun context manager if tracking is enabled,
        otherwise a no-op nullcontext().
    """
    tracking_enabled = os.getenv("TRACKING_ENABLED", "true").lower() == "true"
    if not tracking_enabled:
        print("[TRACKING] Tracking disabled (TRACKING_ENABLED != true)")
        return nullcontext()

    try:
        import mlflow
        import mlflow.sklearn
    except ImportError:
        print("[TRACKING] mlflow not installed — tracking disabled")
        return nullcontext()

    username = os.getenv("DAGSHUB_USERNAME")
    repo = os.getenv("DAGSHUB_REPO")
    token = os.getenv("DAGSHUB_TOKEN", "")

    if not username or not repo:
        print("[TRACKING] DAGSHUB_USERNAME or DAGSHUB_REPO not set — tracking disabled")
        return nullcontext()

    tracking_uri = f"https://dagshub.com/{username}/{repo}.mlflow"
    os.environ["MLFLOW_TRACKING_URI"] = tracking_uri
    os.environ["MLFLOW_TRACKING_USERNAME"] = username
    os.environ["MLFLOW_TRACKING_PASSWORD"] = token

    mlflow.set_tracking_uri(tracking_uri)

    # dagshub.init() — optional, URI is already set
    try:
        import dagshub
        dagshub.init(repo_owner=username, repo_name=repo, mlflow=True)
    except Exception as e:
        print(f"[TRACKING] dagshub.init() skipped (URI already set): {e}")

    mlflow.set_experiment(experiment_name)

    default_tags = {
        "env": os.getenv("ENV", "dev"),
        "triggered_by": os.getenv("USERNAME", os.getenv("USER", "local")),
        "project": "astrogeo-graphrag",
        "experiment": experiment_name,
    }
    if tags:
        default_tags.update(tags)

    print(f"[TRACKING] MLflow → {tracking_uri}")
    print(f"[TRACKING] Experiment: {experiment_name} | Run: {run_name}")

    return mlflow.start_run(run_name=run_name, tags=default_tags)
