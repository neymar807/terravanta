from __future__ import annotations

import asyncio
import csv
import io
import os
import time
from datetime import date, timedelta
from typing import Any

import httpx
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

APP_VERSION = "0.1.0"
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "900"))
NASA_POWER_URL = "https://power.larc.nasa.gov/api/temporal/daily/point"
OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

app = FastAPI(
    title="TerraVanta API",
    description="A transparent API for NASA Earth and climate data plus complementary weather-model information.",
    version=APP_VERSION,
)

# Set FRONTEND_ORIGINS to comma-separated trusted site origins in production.
# Example: https://neymar807.github.io
origins = [x.strip() for x in os.getenv("FRONTEND_ORIGINS", "*").split(",") if x.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET"],
    allow_headers=["*"],
)

_cache: dict[str, tuple[float, Any]] = {}
_cache_lock = asyncio.Lock()


async def cached_json(key: str, url: str, params: dict[str, Any], ttl: int = CACHE_TTL_SECONDS) -> Any:
    now = time.monotonic()
    async with _cache_lock:
        item = _cache.get(key)
        if item and item[0] > now:
            return item[1]

    try:
        async with httpx.AsyncClient(timeout=35.0, headers={"User-Agent": "TerraVanta/0.1 educational project"}) as client:
            response = await client.get(url, params=params)
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Upstream data provider returned HTTP {exc.response.status_code}.") from exc
    except (httpx.HTTPError, ValueError) as exc:
        raise HTTPException(status_code=502, detail="Could not retrieve or parse data from the upstream provider.") from exc

    async with _cache_lock:
        _cache[key] = (time.monotonic() + ttl, payload)
    return payload


def validate_dates(start_date: date, end_date: date) -> None:
    if end_date < start_date:
        raise HTTPException(status_code=400, detail="end_date must be on or after start_date.")
    if (end_date - start_date).days > 6 * 366:
        raise HTTPException(status_code=400, detail="Please request no more than six years at a time.")
    if end_date > date.today():
        raise HTTPException(status_code=400, detail="Historical data end_date cannot be in the future.")


@app.get("/")
async def root() -> dict[str, str]:
    return {"name": "TerraVanta API", "version": APP_VERSION, "docs": "/docs", "health": "/api/health"}


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "TerraVanta API", "version": APP_VERSION}


@app.get("/api/climate/daily")
async def climate_daily(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    start_date: date = Query(default=date(date.today().year - 5, 1, 1)),
    end_date: date = Query(default=date.today() - timedelta(days=2)),
) -> dict[str, Any]:
    """NASA POWER daily temperature, precipitation and solar radiation."""
    validate_dates(start_date, end_date)
    params = {
        "parameters": "T2M,PRECTOTCORR,ALLSKY_SFC_SW_DWN",
        "community": "AG",
        "longitude": lon,
        "latitude": lat,
        "start": start_date.strftime("%Y%m%d"),
        "end": end_date.strftime("%Y%m%d"),
        "format": "JSON",
        "time-standard": "UTC",
    }
    key = f"power:{lat:.4f}:{lon:.4f}:{start_date}:{end_date}"
    payload = await cached_json(key, NASA_POWER_URL, params, ttl=3600)
    return {
        "source": "NASA POWER Daily API",
        "source_url": "https://power.larc.nasa.gov/",
        "documentation": "https://power.larc.nasa.gov/docs/services/api/temporal/daily/",
        "data_type": "gridded daily estimates; near-real-time availability can lag",
        "coordinates": {"latitude": lat, "longitude": lon},
        "requested_period": {"start": str(start_date), "end": str(end_date)},
        "units": {"T2M": "°C", "PRECTOTCORR": "mm/day", "ALLSKY_SFC_SW_DWN": "MJ/m²/day"},
        "data": payload,
    }


@app.get("/api/weather")
async def current_and_forecast(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
) -> dict[str, Any]:
    """Current conditions, short-range forecast and modelled soil indicators."""
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": "temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m",
        "hourly": "soil_moisture_0_to_7cm,soil_temperature_0cm,evapotranspiration",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_sum,precipitation_probability_max,et0_fao_evapotranspiration",
        "forecast_days": 7,
        "timezone": "auto",
    }
    key = f"openmeteo:{lat:.4f}:{lon:.4f}"
    payload = await cached_json(key, OPEN_METEO_URL, params, ttl=900)
    return {
        "source": "Open-Meteo Forecast API",
        "source_url": "https://open-meteo.com/",
        "documentation": "https://open-meteo.com/en/docs",
        "data_type": "weather-model current conditions and forecast; not a farm sensor reading",
        "soil_indicator_note": "Soil moisture and soil temperature are model estimates for the selected grid cell, not direct measurements of the user's field.",
        "coordinates": {"latitude": lat, "longitude": lon},
        "data": payload,
    }


@app.get("/api/sources")
async def sources() -> dict[str, Any]:
    return {
        "sources": [
            {
                "name": "NASA POWER",
                "purpose": "Historical and near-real-time gridded meteorological and solar data",
                "url": "https://power.larc.nasa.gov/",
                "documentation": "https://power.larc.nasa.gov/docs/",
            },
            {
                "name": "Open-Meteo",
                "purpose": "Current model conditions, short-range weather forecast, and modelled soil indicators",
                "url": "https://open-meteo.com/",
                "documentation": "https://open-meteo.com/en/docs",
            },
        ],
        "note": "Sources have different methods, update schedules and spatial resolutions. Do not treat them as interchangeable or as field measurements.",
    }


@app.get("/api/fires")
async def satellite_fires(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    radius: float = Query(default=1.0, ge=0.1, le=5.0, description="Approximate search radius in degrees."),
    days: int = Query(default=1, ge=1, le=5),
) -> dict[str, Any]:
    """Optional NASA FIRMS active-fire detections; requires a private MAP_KEY."""
    map_key = os.getenv("NASA_FIRMS_MAP_KEY")
    if not map_key:
        raise HTTPException(
            status_code=503,
            detail="NASA FIRMS is not configured yet. Add NASA_FIRMS_MAP_KEY as a private server environment variable.",
        )

    west, south, east, north = lon - radius, lat - radius, lon + radius, lat + radius
    bbox = f"{west:.4f},{south:.4f},{east:.4f},{north:.4f}"
    sensor = os.getenv("NASA_FIRMS_SOURCE", "VIIRS_SNPP_NRT")
    url = f"https://firms.modaps.eosdis.nasa.gov/api/area/csv/{map_key}/{sensor}/{bbox}/{days}"
    cache_key = f"firms:{sensor}:{bbox}:{days}"
    now = time.monotonic()
    async with _cache_lock:
        item = _cache.get(cache_key)
        if item and item[0] > now:
            raw_csv = item[1]
        else:
            raw_csv = None
    if raw_csv is None:
        try:
            async with httpx.AsyncClient(timeout=35.0, headers={"User-Agent": "TerraVanta/0.1 educational project"}) as client:
                response = await client.get(url)
                response.raise_for_status()
                raw_csv = response.text
        except httpx.HTTPStatusError as exc:
            raise HTTPException(status_code=502, detail=f"NASA FIRMS returned HTTP {exc.response.status_code}.") from exc
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail="Could not retrieve NASA FIRMS data.") from exc
        async with _cache_lock:
            _cache[cache_key] = (time.monotonic() + 900, raw_csv)

    try:
        rows = list(csv.DictReader(io.StringIO(raw_csv)))
    except Exception as exc:
        raise HTTPException(status_code=502, detail="NASA FIRMS returned an unreadable CSV response.") from exc
    return {
        "source": "NASA FIRMS",
        "source_url": "https://firms.modaps.eosdis.nasa.gov/",
        "documentation": "https://firms.modaps.eosdis.nasa.gov/api/",
        "data_type": "satellite active-fire detections; detections are not a complete fire perimeter or proof of damage",
        "sensor": sensor,
        "search_area": {"latitude": lat, "longitude": lon, "radius_degrees": radius, "days": days},
        "count": len(rows),
        "detections": rows,
    }
