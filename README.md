# GeoMoss — 2D/3D WebGIS Platform

[![Vue](https://img.shields.io/badge/Vue-3.3+-4FC08D?logo=vuedotjs)](https://vuejs.org/)
[![Vite](https://img.shields.io/badge/Vite-5.0+-646CFF?logo=vite)](https://vitejs.dev/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![OpenLayers](https://img.shields.io/badge/OpenLayers-8.x-FFD700?logo=openlayers)](https://openlayers.org/)
[![Cesium](https://img.shields.io/badge/Cesium-1.108-6CACE4?logo=cesium)](https://cesium.com/)
[![License](https://img.shields.io/badge/License-MIT-blue)](#license)

## Overview

**GeoMoss** is a full-stack WebGIS platform featuring 2D/3D mapping, real-time weather, SHP-to-3D-Tiles conversion, and AI-powered spatial analysis. Built with Vue 3 + OpenLayers + Cesium on the frontend and FastAPI + PostgreSQL on the backend.

- **Frontend**: Vue 3 + Vite + OpenLayers + Cesium
- **Backend**: FastAPI + Python + PostgreSQL
- **Deployment**: Self-hosted on VPS (154.201.94.222), domain `www.geomoss.top`

## Features

### Map & GIS
- 2D OpenLayers with multi-source basemaps (Tianditu, Google, Mapbox, custom XYZ/WMS)
- 3D Cesium globe with SHP-to-3D-Tiles building extrusion
- Layer management with drag-and-drop reorder, opacity, label fields
- Drawing tools (point/line/polygon/circle), measurement, coordinate picker
- Basemap swipe comparison
- District boundary loading with label dedup

### Data Pipeline
- Multi-format import: GeoJSON, KML/KMZ, Shapefile, GeoTIFF, CSV
- SHP → 3D Tiles wizard: upload → field selection → color/opacity styling → auto-convert → load
- Layer export: CSV, TXT, GeoJSON, KML

### Weather
- Powered by Open-Meteo (free, no API key)
- Amap direct geocode for district/city/province labels
- 7-day forecast with temperature trend charts
- Rain detection alerts
- 3-level panel: collapsed / sidebar / fullscreen

### AI & Tools
- AI Chat Assistant (multi-model, guest quota, preferences)
- Bus & Drive route planning
- Feng Shui Compass (SVG layers, 5 themes, mobile HUD mode with gyroscope)
- Weather dashboard
- Hot news aggregation (Weibo, Zhihu, GitHub, Hacker News, etc.)

### Auth & Account
- Username/password login (guest / registered / admin roles)
- Email registration with CAPTCHA + SMTP verification
- Password reset via bound email
- API key management

### UI/UX
- Dark-first Arc Browser inspired design system
- Aurora gradient backdrop (mint-to-cyan)
- Frosted glass surfaces with backdrop-saturate
- Spring-easing transitions (`cubic-bezier(0.34, 1.56, 0.64, 1)`)
- Mobile responsive with safe area support

## Quick Start

```bash
# Clone
git clone https://github.com/SCAU-Algae/GeoMoss-WebGIS.git
cd GeoMoss-WebGIS

# Frontend
cd frontend && npm install && npm run dev
# → http://localhost:5173

# Backend
cd backend
export SMTP_USER="your_qq@qq.com" SMTP_PASS="your_smtp_auth_code"
python3 -m uvicorn app:app --host 0.0.0.0 --port 8000
# → http://localhost:8000/docs
```

Or use the one-click script:

```bash
bash start-webgis.sh
```

## Environment Variables

### Frontend (`frontend/.env`)
```bash
VITE_TIANDITU_TK=your_tianditu_token
VITE_AMAP_WEB_SERVICE_KEY=your_amap_key
```

### Backend (shell env)
```bash
SMTP_HOST=smtp.qq.com
SMTP_PORT=465
SMTP_USER=your_qq@qq.com
SMTP_PASS=your_qq_smtp_auth_code
DATABASE_URL=postgresql://user:password@localhost/webgis
```

## Project Structure

```
GeoMoss-WebGIS/
├── frontend/
│   ├── src/
│   │   ├── api/              # API layer (weather, geocoding, backend)
│   │   ├── components/       # Vue components
│   │   │   ├── Cesium/       # Cesium 3D globe + Wind2D
│   │   │   ├── UserCenter/   # Account, admin, API keys
│   │   │   └── feng-shui-compass-svg/  # Compass themes & types
│   │   ├── composables/      # Reusable logic
│   │   ├── stores/           # Pinia stores (auth, weather, layers, compass...)
│   │   ├── utils/            # GIS parsers, coordinate transforms
│   │   └── views/            # HomeView, RegisterView
│   └── public/               # Static assets, adcode.json
├── backend/
│   ├── api/
│   │   ├── auth.py           # Authentication & sessions
│   │   ├── email_auth.py     # Email registration + CAPTCHA
│   │   ├── shp_to_3dtiles.py # SHP → 3D Tiles converter
│   │   ├── threed.py         # 3D processing API
│   │   └── proxy.py          # Tile & API proxy
│   ├── app.py                # FastAPI entry
│   └── data/                 # Runtime data
├── Docs/                     # Development logs
└── design-system/            # UI/UX Pro Max design tokens
```

## Tech Stack

| Layer | Stack |
|-------|-------|
| Frontend | Vue 3.3+, Vite 5.0+, Pinia, Vue Router |
| 2D Map | OpenLayers 8.x |
| 3D Map | Cesium 1.108 (Tianditu) |
| Backend | FastAPI, Uvicorn, Pydantic |
| Database | PostgreSQL (with sqlite3 adapter) |
| Email | SMTP (QQ Mail) |
| Weather | Open-Meteo + Amap geocode |
| Charts | ECharts 5.x |
| Icons | Lucide Vue Next |
| Animation | @vueuse/motion |

## Attribution

This project is a derivative work based on **[NEGIAO/WebGIS-Dev](https://github.com/NEGIAO/WebGIS-Dev)** (MIT License), created by [@NEGIAO](https://github.com/NEGIAO). The original project provided the foundational WebGIS architecture (Vue 3 + OpenLayers + FastAPI), which has since been significantly extended with:

- Complete UI/UX redesign (Arc Browser-inspired dark glassmorphism)
- SHP → 3D Tiles building extrusion pipeline
- Open-Meteo weather integration with Amap direct geocode
- Email registration with CAPTCHA + SMTP verification
- Hot news aggregation from multiple platforms
- Feng Shui Compass enhancements
- 3D layer management and camera fly transitions
- Aurora design system with frosted glass surfaces

All modifications retain the original MIT License.

## License

MIT — freely use, modify, and distribute.

## Author

**SCAU-Algae** — [GitHub](https://github.com/SCAU-Algae)

---

**Repository**: https://github.com/SCAU-Algae/GeoMoss-WebGIS
**Live**: http://www.geomoss.top
