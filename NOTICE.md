# Notices and Third-Party References

This repository contains GeoMoss WebGIS, a derivative and heavily extended WebGIS application.

## Upstream Base

- **NEGIAO/WebGIS-Dev**
  - Repository: https://github.com/NEGIAO/WebGIS-Dev
  - Role: original WebGIS application architecture and earlier Vue/OpenLayers/FastAPI foundation.
  - License: MIT, according to the upstream repository metadata/documentation available at the time this notice was written.
  - GeoMoss keeps the original attribution and substantially extends the project with new backend architecture, 3D geodata workflows, Cesium tools, AI analysis, admin console work and redesigned UI.

## Feature and Design References

- **cesium-extends and related public Cesium extension patterns**
  - Role: feature reference for common Cesium measurement, drawing and 3D Tiles interaction patterns.
  - Usage in GeoMoss: implemented as native modules under `frontend/src/composables/cesium` and `frontend/src/components/Cesium`; external UI panels were not copied.
  - Keep license checks in mind before copying any future third-party source code verbatim.

- **llmi124/shanshui-mintang-fengshui-gis**
  - Repository: https://github.com/llmi124/shanshui-mintang-fengshui-gis
  - Role: product/domain reference for Fengshui-style terrain/water/environment analysis.
  - Usage in GeoMoss: adapted the analysis concept into GeoMoss' own OpenLayers drawing flow, backend DEM/water services, Tianditu imagery capture, Qwen vision interpretation and structured AI report format.
  - No source code or UI was copied wholesale into this repository.

## Core Open-Source Dependencies

GeoMoss depends on standard open-source packages declared in `frontend/package.json` and `backend/pyproject.toml`, including but not limited to:

- Vue, Vite, Pinia and Vue Router
- OpenLayers
- Cesium runtime loaded by the application
- ECharts
- FastAPI, Uvicorn and httpx
- pyproj, pyshp, Pillow and NumPy

Check each dependency's upstream license before redistribution in a commercial or packaged environment.

## Data and API Keys

Runtime geodata, generated 3D Tiles, uploaded datasets, databases, logs and API keys are not part of this notice and should not be committed to the repository.

