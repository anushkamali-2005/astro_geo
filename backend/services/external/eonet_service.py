from typing import Dict, Optional

import httpx


class EONETService:
    """Thin client for NASA EONET v3 APIs."""

    def __init__(self):
        self.base_url = "https://eonet.gsfc.nasa.gov/api/v3"
        self.client = httpx.AsyncClient(timeout=20.0)

    async def get_events(
        self,
        *,
        limit: int = 50,
        days: Optional[int] = None,
        category: Optional[str] = None,
        status: Optional[str] = "open",
    ) -> Dict:
        params = {"limit": max(1, min(limit, 200))}
        if days is not None:
            params["days"] = max(1, min(days, 365))
        if category:
            params["category"] = category
        if status in {"open", "closed", "all"}:
            params["status"] = status

        response = await self.client.get(f"{self.base_url}/events", params=params)
        response.raise_for_status()
        return response.json()

    async def get_events_geojson(
        self,
        *,
        limit: int = 500,
        days: Optional[int] = None,
        category: Optional[str] = None,
        status: Optional[str] = "open",
    ) -> Dict:
        params = {"limit": max(1, min(limit, 2000))}
        if days is not None:
            params["days"] = max(1, min(days, 365))
        if category:
            params["category"] = category
        if status in {"open", "closed", "all"}:
            params["status"] = status

        response = await self.client.get(f"{self.base_url}/events/geojson", params=params)
        response.raise_for_status()
        return response.json()

    async def get_categories(self) -> Dict:
        response = await self.client.get(f"{self.base_url}/categories")
        response.raise_for_status()
        return response.json()

    async def get_layers(self) -> Dict:
        response = await self.client.get(f"{self.base_url}/layers")
        response.raise_for_status()
        return response.json()


eonet_service = EONETService()
