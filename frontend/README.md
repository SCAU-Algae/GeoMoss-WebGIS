# GeoMoss Frontend

Frontend release: **v3.1.0**

Vue 3 + Vite + OpenLayers + Cesium frontend for GeoMoss WebGIS.

## Main Capabilities

- OpenLayers 2D map with Tianditu/Amap basemap management and swipe comparison.
- User layer import/export for GeoJSON, KML/KMZ, SHP, GeoTIFF and CSV.
- TOC layer management, drawing, measurement, attribute table and route planning.
- Draggable/resizable floating panels for AI, weather, tools, news, Fengshui analysis and layer management.
- Cesium 3D mode with 3D Tiles loading, styling, inspection, measuring, drawing and camera bookmarks.
- Native Fengshui/environment analysis panel using map-drawn study areas and backend analysis APIs.
- Admin console surfaces for API keys, geodata, 3D layer processing and usage data.

## Removed in v3.1.0

- The old Fengshui compass/HUD feature block and its SVG theme runtime.
- The shared-resource menu/loading UI and bundled shared sample layers.
- The old header slogan.

## Commands

```bash
npm install
npm run dev
npm run build
npm run preview
```

## Environment

```env
VITE_BACKEND_URL=http://localhost:8000
VITE_TIANDITU_TK=your_tianditu_token
VITE_AMAP_WEB_SERVICE_KEY=your_amap_web_service_key
VITE_BASE_URL=./
```

## Source Layout

```text
frontend/
├── public/
│   └── images/                  # Static logo and public imagery
├── src/
│   ├── api/                     # Backend/API clients
│   ├── assets/                  # Global CSS and design tokens
│   ├── components/
│   │   ├── Cesium/              # 3D scene, tools and popups
│   │   └── UserCenter/          # Account/admin panels
│   ├── composables/
│   │   ├── cesium/              # Cesium feature registry and tools
│   │   └── map/                 # OpenLayers feature modules
│   ├── constants/               # Basemap and style registries
│   ├── router/
│   ├── stores/
│   ├── utils/
│   └── views/
└── package.json
```

See the root [CHANGELOG.md](../CHANGELOG.md) for release details and [NOTICE.md](../NOTICE.md) for open-source attribution.
