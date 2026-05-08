# Changelog

## v3.1.0 - 2026-05-08

### Brand and Navigation

- Replaced the old header slogan with `GeoMoss`.
- Added the new GeoMoss logo asset at `frontend/public/images/icon.webp` and a PNG fallback.
- Removed the Fengshui compass feature block from the top menu, tool suite, side panel and OpenLayers map runtime.
- Deleted unused compass implementation files: control panel, manager service, Pinia store, URL state helpers, SVG themes and explanation datasets.
- Removed the shared-resource menu/loading path and the bundled shared sample layers from the frontend UI surface.

### Backend Architecture

- Split backend application startup into dedicated route registration, lifecycle and CORS modules.
- Added system endpoints as a dedicated router.
- Added administrator geodata and 3D layer management APIs.
- Added safer SHP to 3D Tiles processing paths with staged uploads, progress tracking and background execution.
- Added server-side terrain, water, imagery capture, visual recognition and structured Fengshui/environment analysis services.

### 3D Tiles and Cesium

- Added administrator workflows for administrative-boundary splitting or temporary grid splitting before 3D layer tiling.
- Added 3D layer availability checks so normal users only see enabled 3D layers when backend data exists.
- Added Cesium tool modules through a `useCesiumFeatureRegistry` adapter:
  - distance/area/height style measurement tools,
  - temporary point/line/polygon sketch drawing,
  - 3D Tiles color/opacity/height styling,
  - feature hover/click highlight and property popup,
  - Shenzhen/China camera presets and camera bookmarks,
  - lightweight optional visual effects.
- Added Tianditu-oriented imagery/terrain behavior for 3D mode to avoid GCJ-02 offset issues from Amap imagery.

### Fengshui / Environment Analysis

- Added a native Fengshui analysis panel integrated into the existing floating window system.
- Added polygon study-area drawing from the current OpenLayers map.
- Added backend DEM, water geometry and terrain metric analysis.
- Added Tianditu remote-sensing screenshot capture for the selected study area.
- Added Qwen vision model integration for visual water recognition.
- Added structured AI insight prompts so downstream report rendering can remain stable.
- Added Amap location-context enrichment for textual place semantics only; visual/remote-sensing facts remain Tianditu-based.

### Admin Console

- Added API key management entries for Tianditu, Amap, DashScope/Qwen vision and text-model services.
- Added geodata administration for administrative divisions, grid parameters and 3D layer processing tasks.
- Improved administrator UI styling so the API and geodata panels better match the global GeoMoss dark/cyan design.

### UI/UX

- Added reusable draggable/resizable floating panels for map-side workflows.
- Improved weather panel responsiveness for chart and forecast layouts.
- Kept Cesium tools inside the existing panel system instead of copying external panel UIs.
- Cleaned stale menu entries and dead event wiring after compass/shared-resource removal.

### Operations

- Updated `.gitignore` for runtime databases, 3D Tiles upload staging, Python caches, Vite caches and logs.
- Verified frontend production build on the deployment server with `npm run build`.

### Notes on External References

- The project remains derived from **NEGIAO/WebGIS-Dev**.
- Cesium measurement/drawing/style features were implemented in project-native modules after referencing public Cesium extension patterns such as `cesium-extends`; no external panel code was vendored.
- Fengshui analysis UX and domain flow were adapted from the public `llmi124/shanshui-mintang-fengshui-gis` idea into this project's own map, panel and backend service architecture; no external source code was copied wholesale.

