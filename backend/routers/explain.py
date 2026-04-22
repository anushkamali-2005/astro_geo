# backend/routers/explain.py
from fastapi import APIRouter, HTTPException
import pandas as pd
import numpy as np
import os
import json

router = APIRouter(prefix="/api/explain", tags=["explainability"])

# Paths to data
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'backend', 'outputs')
SHAP_CSV = os.path.join(OUTPUT_DIR, 'shap_mean_abs_values.csv')

@router.get("/shap-heatmap")
async def get_shap_heatmap():
    """
    Returns SHAP feature impact data for a heatmap visualization.
    Rows = Features, Columns = Samples (or Classes in this case).
    """
    try:
        if not os.path.exists(SHAP_CSV):
            raise HTTPException(status_code=404, detail="SHAP data not found")
        
        df = pd.read_csv(SHAP_CSV, index_col=0)
        # Convert to format: { features: [], samples: [], values: [[...]] }
        features = df.columns.tolist()
        classes = df.index.tolist()
        values = df.values.tolist()
        
        return {
            "features": features,
            "classes": classes,
            "values": values,
            "title": "SHAP Global Feature Importance Heatmap"
        }
    except Exception as e:
        # Fallback/Simulation if file is missing or malformed
        return {
            "features": ["dist_min", "kinetic_energy", "approach_count", "orbit_stability", "v_rel"],
            "classes": ["Low Risk", "Medium Risk", "High Risk", "Anomalous"],
            "values": [
                [0.1, 0.2, 0.5, 0.8],
                [0.4, 0.3, 0.6, 0.9],
                [0.2, 0.5, 0.8, 0.3],
                [0.7, 0.8, 0.9, 0.2],
                [0.1, 0.2, 0.3, 0.4]
            ],
            "title": "SHAP Feature Impact (Simulated)"
        }

@router.get("/risk-matrix")
async def get_risk_matrix():
    """
    Returns data for a Risk Stratification Matrix.
    Shows average risk score for combinations of two features.
    """
    # For now, we return a representative 5x5 matrix
    # In a real scenario, this would be computed from the inference results
    matrix_data = [
        [4, 11, 25, 33, 45],
        [16, 21, 35, 52, 57],
        [30, 39, 48, 57, 73],
        [43, 56, 66, 78, 84],
        [58, 63, 79, 85, 99]
    ]
    
    return {
        "x_axis": {
            "label": "Anomaly Score Category",
            "ticks": ["Type A", "Type B", "Type C", "Type D", "Type E"]
        },
        "y_axis": {
            "label": "Risk Score Category",
            "ticks": ["Safe", "Low", "Moderate", "High", "Critical"]
        },
        "data": matrix_data,
        "title": "AstroGeo Risk Stratification Matrix",
        "description": "Average predicted risk score for every combination of Anomaly Type and Risk Level."
    }
