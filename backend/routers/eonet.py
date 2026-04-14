from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from backend.services.external.eonet_service import eonet_service

router = APIRouter(prefix="/api/eonet", tags=["EONET"])


@router.get("/events")
async def get_eonet_events(
    limit: int = Query(50, ge=1, le=200),
    days: Optional[int] = Query(None, ge=1, le=365),
    category: Optional[str] = None,
    status: str = Query("open", pattern="^(open|closed|all)$"),
):
    try:
        return await eonet_service.get_events(
            limit=limit,
            days=days,
            category=category,
            status=status,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"EONET events fetch failed: {e}")


@router.get("/events/geojson")
async def get_eonet_events_geojson(
    limit: int = Query(500, ge=1, le=2000),
    days: Optional[int] = Query(None, ge=1, le=365),
    category: Optional[str] = None,
    status: str = Query("open", pattern="^(open|closed|all)$"),
):
    try:
        return await eonet_service.get_events_geojson(
            limit=limit,
            days=days,
            category=category,
            status=status,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"EONET geojson fetch failed: {e}")


@router.get("/categories")
async def get_eonet_categories():
    try:
        return await eonet_service.get_categories()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"EONET categories fetch failed: {e}")


@router.get("/layers")
async def get_eonet_layers():
    try:
        return await eonet_service.get_layers()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"EONET layers fetch failed: {e}")
