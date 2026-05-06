# WebGIS-Dev Guidance

## Project Shape

- This project is a WebGIS platform with `frontend/` for Vue 3 + Pinia + OpenLayers + Cesium and `backend/` for FastAPI + PostgreSQL.
- Before significant changes, read `/root/Desktop/WebGIS-架构文档.md` and keep the documented component, store, API, and 2D/3D boundaries intact.
- Prefer existing local patterns over new abstractions. Keep edits scoped to the module or workflow the user asks about.

## Skill-First Workflow

- Use installed skills proactively when the request matches them; the user should not need to name a skill explicitly.
- For broad or ambiguous changes, clarify and plan with the installed planning workflow before editing.
- For implementation tasks, carry work through code changes, verification, and a clear summary.
- For reviews, lead with concrete findings and file references.

## Frontend Rules

- `frontend/src/views/HomeView.vue` is the main map orchestrator. Route cross-cutting UI and map events through it unless an existing composable already owns that behavior.
- Keep 2D OpenLayers behavior in `MapContainer.vue` and related map composables. Keep 3D Cesium behavior in `components/Cesium/CesiumContainer.vue`.
- 3D mode is state-driven by visible `layerStore.threeDLayers`; do not introduce a separate route for 3D unless explicitly requested.
- Use Pinia stores for shared state and composables for reusable behavior. Avoid pushing long-lived shared state into isolated components.
- Use existing design tokens and visual conventions from `frontend/src/assets/`.
- Use `lucide-vue-next` icons when a suitable icon exists.

## Backend Rules

- `backend/app.py` is the FastAPI entry and route registration point.
- Keep API behavior inside the existing `backend/api/*.py` ownership areas.
- Preserve the PostgreSQL adapter expectations in `api/database.py`, including sqlite-style compatibility where existing code depends on it.
- Keep SHP to 3D Tiles processing inside `api/threed.py` and `api/shp_to_3dtiles.py` unless the user asks for a larger refactor.

## Figma Design Workflow

- For Figma-to-code work, use the Figma plugin skills proactively.
- When the user provides a Figma link or asks to implement a design, follow `figma-implement-design`: get design context, get screenshot, collect assets, translate into Vue/project conventions, and validate visual parity.
- When the user asks to create or update Figma screens from this app or a description, follow `figma-generate-design` together with `figma-use`.
- When asked to make reusable Figma/design-system guidance, follow `figma-create-design-system-rules` and update this file or another appropriate project rule file.
- For WebGIS UI design, favor dense, operational map tooling over marketing-style landing page layouts.
