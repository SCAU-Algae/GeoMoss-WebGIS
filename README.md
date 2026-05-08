# GeoMoss WebGIS

GeoMoss is a full-stack WebGIS platform for 2D mapping, Cesium 3D visualization, 3D Tiles data management, weather analysis, AI-assisted spatial interpretation, and cultural landscape analysis.

Current release: **v3.1.0**
Last updated: **2026-05-08**

## Overview

- Frontend: Vue 3, Vite, OpenLayers, Cesium, Pinia, ECharts
- Backend: FastAPI, SQLite/PostgreSQL-compatible access layer, async task APIs
- 2D GIS: basemap switching, TOC layer management, draw/measure tools, attribute table, map swipe
- 3D GIS: Cesium 3D mode, Tianditu imagery/terrain support, 3D Tiles styling, inspection, drawing, measuring, feature popup
- Data pipeline: user layer import/export, administrator geodata management, SHP to 3D Tiles conversion
- AI modules: chat assistant, Fengshui/environment analysis with DEM, water data, Tianditu remote-sensing screenshot, Qwen vision, DeepSeek-style structured insight generation
- Admin console: users, API keys, API usage, geodata, 3D tiles and background task progress

## v3.1.0 Highlights

- Rebranded the application from the old slogan to **GeoMoss** and replaced the header logo.
- Removed the Fengshui compass feature block and its unused runtime modules, store, services, SVG themes, explanation data, and URL state helpers.
- Removed the shared-resource UI/loading path and cleaned the default public shared sample layers.
- Refactored backend startup into route/lifecycle/core modules to keep `app.py` small and extensible.
- Added administrator-only 3D geodata workflows: administrative split source or generated grid split, 3D layer upload, task progress, storage and deletion.
- Added 4-core/8GB friendly conversion controls: queued processing, safer upload staging, tile splitting, progress tracking, and less blocking frontend behavior.
- Added Cesium tools through a registry-style adapter: measure, sketch drawing, 3D Tiles style controls, feature picking popup, navigation bookmarks and lightweight visual effects.
- Added Fengshui/environment analysis as a native tool integrated with the existing floating-panel UI, DEM/water services, Tianditu imagery capture, Qwen vision and structured AI insights.
- Improved weather panel responsiveness and administrator API/settings UI consistency.

Full release notes are in [CHANGELOG.md](./CHANGELOG.md).

## Project Structure

```text
GeoMoss-WebGIS/
├── frontend/
│   ├── public/                 # Static public assets
│   ├── src/
│   │   ├── api/                # Frontend API clients
│   │   ├── components/         # Vue UI components
│   │   │   ├── Cesium/         # Cesium scene and tool panels
│   │   │   └── UserCenter/     # Account/admin/API/geodata panels
│   │   ├── composables/        # Reusable OpenLayers/Cesium feature modules
│   │   ├── constants/          # Basemap and style configuration
│   │   ├── stores/             # Pinia stores
│   │   ├── utils/              # GIS parsers, runtime loaders, helpers
│   │   └── views/              # Home/admin/register views
│   └── package.json
├── backend/
│   ├── api/                    # FastAPI route modules
│   ├── core/                   # App lifecycle, CORS and shared bootstrap
│   ├── scripts/                # Operational scripts
│   ├── services/               # Domain services including Fengshui analysis
│   ├── app.py                  # FastAPI entrypoint
│   └── pyproject.toml
├── Docs/                       # Historical development notes
├── docs/                       # Current design and release documentation
├── CHANGELOG.md
├── NOTICE.md
└── README.md
```

## Local Development

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Backend:

```bash
cd backend
python3 -m uvicorn app:app --reload --host 0.0.0.0 --port 8000
```

Production-style frontend build:

```bash
cd frontend
npm run build
```

## Environment

Frontend `.env.local` example:

```env
VITE_BACKEND_URL=http://localhost:8000
VITE_TIANDITU_TK=your_tianditu_token
VITE_AMAP_WEB_SERVICE_KEY=your_amap_web_service_key
VITE_BASE_URL=./
```

Backend environment/API keys can be configured through the admin API key panel or process environment:

```env
TIANDITU_TK=your_tianditu_token
AMAP_KEY=your_amap_key
DASHSCOPE_API_KEY=your_dashscope_key
AGENT_API_KEY=your_text_model_key
SMTP_HOST=smtp.qq.com
SMTP_PORT=465
SMTP_USER=your_mailbox
SMTP_PASS=your_smtp_auth_code
```

Do not commit real API keys, tokens, user uploads, generated 3D Tiles, logs, or runtime databases.

## Attribution

GeoMoss is derived from and substantially extends the original MIT-licensed **NEGIAO/WebGIS-Dev** project. This repository also references ideas and public documentation from several open-source GIS/Cesium projects. See [NOTICE.md](./NOTICE.md) for details.

## License

MIT. See the original upstream attribution and third-party notes in [NOTICE.md](./NOTICE.md).
