# TerraVanta

A NASA Space Apps Challenge 2026 project exploring climate-resilient agriculture using Earth observation data.

## Project structure

- `index.html` — TerraVanta homepage
- `history.html` — historical climate comparison and rainfall-anomaly screening
- `backend/main.py` — FastAPI service that fetches and serves environmental data
- `backend/requirements.txt` — Python dependencies
- `backend/render.yaml` — deployment blueprint

## Backend data sources

The backend currently provides:

| Endpoint | Provider | What it returns |
|---|---|---|
| `GET /api/health` | TerraVanta | Service health |
| `GET /api/climate/daily?lat=30.1798&lon=66.9750&start_date=2019-01-01&end_date=2024-12-31` | NASA POWER | Daily air temperature, corrected precipitation and solar radiation |
| `GET /api/weather?lat=30.1798&lon=66.9750` | Open-Meteo | Current model conditions, seven-day forecast and modelled soil indicators |
| `GET /api/sources` | TerraVanta | Source descriptions and documentation |
| `GET /api/fires?lat=30.1798&lon=66.9750` | NASA FIRMS | Optional satellite active-fire detections; requires a private server-side API key |

NASA POWER daily data is near-real-time/historical gridded data, not an instant sensor feed. Open-Meteo provides model-based current conditions and forecasts. Soil moisture and soil temperature are model estimates, not field measurements. NASA FIRMS is optional and will return a setup message until its key is configured.

All upstream results are cached in memory to reduce repeat requests. The cache is temporary and resets when the service restarts.

## Deploy the backend

1. Open the repository on GitHub and make sure the latest backend files are on the `main` branch.
2. In your hosting provider, create a new service from the GitHub repository `neymar807/terravanta`.
3. Use the blueprint file `backend/render.yaml` (or set the service root directory to `backend`).
4. Deploy the service. The backend start command is `uvicorn main:app --host 0.0.0.0 --port $PORT`.
5. After deployment, open `https://YOUR-BACKEND-HOST/api/health`. A successful response contains `"status":"ok"`.
6. Open `https://YOUR-BACKEND-HOST/docs` to inspect and test the API endpoints.
7. Set `FRONTEND_ORIGINS` to the exact published website origin if it differs from the configured GitHub Pages origin.

The hosting provider may require you to review its current free-tier limits and service-sleep behavior before deployment. The backend is committed to GitHub but is **not deployed yet**.

## Connect the website

The existing GitHub Pages frontend still contains its original direct NASA POWER browser requests. It has **not yet been switched to this backend**, because the deployed backend URL does not exist until you deploy it. Once you have the backend's public URL, connect the homepage and climate-history page to these API endpoints and verify the live responses.

## Optional NASA FIRMS setup

1. Request your own free NASA FIRMS MAP_KEY from the official NASA FIRMS website.
2. Add it to the backend host's private environment variables as `NASA_FIRMS_MAP_KEY`.
3. Do not paste the key into HTML, JavaScript, GitHub commits, screenshots, or public messages.
4. Optionally set `NASA_FIRMS_SOURCE` to a supported NASA FIRMS sensor source.

FIRMS detections indicate satellite-observed active-fire pixels; they are not complete fire perimeters or proof of damage.

## Scientific limitations

- Gridded products represent regional estimates, not individual farm measurements.
- Forecasts and soil indicators are model-derived and can differ from local observations.
- A simple rainfall anomaly is not the Standardized Precipitation Index (SPI) or an official drought declaration.
- TerraVanta does not predict yield or prescribe crops, fertilizer, or irrigation.
- Always display the source, units, date/time and limitations alongside data.
