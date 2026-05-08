# Fengshui Analysis Integration Design

## Goal

Move the external "山水明堂" idea into GeoMoss as a native analysis tool, not a copied standalone app. The feature should sit beside the existing AI and route-planning tools while reusing the current map, DEM, Cesium, floating window, message, and dark/cyan UI systems.

## Product Flow

Users open `工具 -> 风水分析`. The panel supports two first-phase study area modes:

- Center/radius analysis, using the current map center or typed coordinates.
- Future polygon/rectangle analysis, reserved behind the same API contract so it can later consume map-drawn GeoJSON.

The analysis returns GIS-derived terrain indicators, rule-based cultural scores, practical risk notes, and an explicit disclaimer. If water vector data is unavailable, the water score is shown as a neutral placeholder and is excluded from weighted certainty.

## UI Boundary

The legacy compass feature block has been retired. `风水分析` is now the dedicated place for range selection, terrain metrics, scores, report text, and related actions such as checking 3D terrain.

The UI uses the existing floating panel visual language: compact tabs, dark surfaces, cyan accents, small metric cards, progress/loading feedback, and no old green/gold standalone styling.

## Backend Architecture

Add a bounded service module under `backend/services/fengshui/`:

- `geometry.py`: GeoJSON and circle study-area helpers.
- `terrain.py`: DEM sampling and fallback terrain metrics.
- `water.py`: optional vector-water relation analysis.
- `scoring.py`: transparent rules for terrain, openness, enclosure, water, aspect, and stability.
- `report.py`: deterministic Chinese report and recommendations.

Add `backend/api/fengshui.py` with:

- `GET /api/fengshui/status`
- `POST /api/fengshui/analyze`

The API accepts a GeoJSON feature or center/radius payload. It never sends raw coordinates to any external model.

## Frontend Architecture

Add:

- `frontend/src/api/fengshui.js`
- `frontend/src/components/FengshuiAnalysisPanel.vue`

Modify:

- `ToolSuitePanel.vue`: add a `风水` tab.
- `HomeView.vue`: route controls and panel metadata to the new tab.
- `ControlsPanel.vue`: make the left-side "分析" button open the new panel instead of the layer toolbox placeholder.
- Remove the old compass explanation surface from the Fengshui flow; reports are rendered directly inside `FengshuiAnalysisPanel.vue`.

## Data Strategy

Use the existing backend DEM configuration first:

- `WEBGIS_FENGSHUI_DEM_PATH`, if set.
- `WEBGIS_DEM_SOURCE_PATH`, if set.
- Existing `/root/project_test/全国DEM/GEBCO-DEM.tif` fallback.

Water data is optional:

- `WEBGIS_WATER_VECTOR_PATH`, if set.
- Empty/missing water data downgrades gracefully.

## Verification

Run Python compile checks for backend changes, frontend production build, then deploy to the remote server and smoke test:

- `GET /api/fengshui/status`
- `POST /api/fengshui/analyze`
- Tool panel renders and can run center/radius analysis.
