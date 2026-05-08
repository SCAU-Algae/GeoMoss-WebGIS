function formatDistance(meters) {
  const value = Number(meters || 0);
  if (value >= 1000) return `${(value / 1000).toFixed(2)} km`;
  return `${value.toFixed(1)} m`;
}

function formatArea(squareMeters) {
  const value = Number(squareMeters || 0);
  if (value >= 1000000) return `${(value / 1000000).toFixed(2)} km2`;
  return `${value.toFixed(1)} m2`;
}

function getSurfacePosition(viewer, Cesium, screenPosition) {
  if (!viewer || !Cesium || !screenPosition) return null;
  const picked = viewer.scene?.pickPositionSupported ? viewer.scene.pickPosition(screenPosition) : null;
  if (picked) return picked;
  const ray = viewer.camera.getPickRay(screenPosition);
  return ray ? viewer.scene.globe.pick(ray, viewer.scene) : null;
}

function makePointEntity(Cesium, position) {
  return {
    position,
    point: {
      pixelSize: 8,
      color: Cesium.Color.CYAN,
      outlineColor: Cesium.Color.WHITE,
      outlineWidth: 1.5,
      disableDepthTestDistance: Number.POSITIVE_INFINITY
    }
  };
}

function makeLabelEntity(Cesium, position, text) {
  return {
    position,
    label: {
      text,
      font: '13px sans-serif',
      fillColor: Cesium.Color.WHITE,
      outlineColor: Cesium.Color.BLACK,
      outlineWidth: 3,
      style: Cesium.LabelStyle.FILL_AND_OUTLINE,
      pixelOffset: new Cesium.Cartesian2(0, -18),
      disableDepthTestDistance: Number.POSITIVE_INFINITY
    }
  };
}

function cartesianDistance(Cesium, positions) {
  let sum = 0;
  for (let i = 1; i < positions.length; i += 1) {
    sum += Cesium.Cartesian3.distance(positions[i - 1], positions[i]);
  }
  return sum;
}

function polygonArea(Cesium, positions) {
  if (positions.length < 3) return 0;
  const points = positions.map((position) => {
    const carto = Cesium.Cartographic.fromCartesian(position);
    const lon = Cesium.Math.toDegrees(carto.longitude);
    const lat = Cesium.Math.toDegrees(carto.latitude);
    const latMeters = lat * 111320.0;
    const lonMeters = lon * 111320.0 * Math.cos(carto.latitude);
    return [lonMeters, latMeters];
  });
  let area = 0;
  for (let i = 0; i < points.length; i += 1) {
    const next = points[(i + 1) % points.length];
    area += points[i][0] * next[1] - next[0] * points[i][1];
  }
  return Math.abs(area) / 2;
}

function createSketchController(registry, mode, measurementEntities) {
  const viewer = registry.getViewer();
  const Cesium = registry.getCesium();
  if (!viewer || !Cesium) return null;

  const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
  const positions = [];
  const sessionEntities = [];
  let dynamicEntity = null;
  let previewPosition = null;
  let finished = false;

  function getSketchPositions() {
    if (previewPosition && positions.length) return [...positions, previewPosition];
    return positions;
  }

  const sketchPositions = new Cesium.CallbackProperty(() => getSketchPositions(), false);

  function cleanupDynamic() {
    if (dynamicEntity) {
      viewer.entities.remove(dynamicEntity);
      dynamicEntity = null;
    }
  }

  function addEntity(config) {
    const entity = viewer.entities.add(config);
    sessionEntities.push(entity);
    return entity;
  }

  function removeSessionEntities() {
    while (sessionEntities.length) {
      try { viewer.entities.remove(sessionEntities.pop()); } catch (_) {}
    }
  }

  function finish() {
    if (finished) return;
    finished = true;
    const finalPositions = positions.slice();
    if (finalPositions.length < (mode === 'area' ? 3 : 2)) {
      cleanupDynamic();
      removeSessionEntities();
      registry.notify('点位不足，已取消本次测量', 'warning');
      return;
    }
    if (mode === 'area') {
      addEntity({
        polygon: {
          hierarchy: new Cesium.PolygonHierarchy(finalPositions),
          material: Cesium.Color.CYAN.withAlpha(0.16),
          outline: true,
          outlineColor: Cesium.Color.CYAN
        }
      });
    } else {
      addEntity({
        polyline: {
          positions: finalPositions,
          width: 3,
          material: Cesium.Color.CYAN
        }
      });
    }
    cleanupDynamic();
    let result = mode === 'area' ? polygonArea(Cesium, finalPositions) : cartesianDistance(Cesium, finalPositions);
    if (mode === 'height') {
      const start = Cesium.Cartographic.fromCartesian(finalPositions[0]);
      const end = Cesium.Cartographic.fromCartesian(finalPositions[1]);
      result = Math.abs(Number(end.height || 0) - Number(start.height || 0));
    }
    const label = mode === 'area' ? formatArea(result) : formatDistance(result);
    const last = finalPositions[finalPositions.length - 1];
    addEntity(makeLabelEntity(Cesium, last, label));
    measurementEntities.push(...sessionEntities);
    sessionEntities.length = 0;
    registry.state.measurements.unshift({
      id: `${mode}_${Date.now()}`,
      type: mode,
      label,
      createdAt: new Date().toLocaleTimeString('zh-CN', { hour12: false })
    });
    registry.state.measurements.splice(12);
    registry.state.statusText = `完成：${label}`;
  }

  handler.setInputAction((movement) => {
    const position = getSurfacePosition(viewer, Cesium, movement.position);
    if (!position) return;
    positions.push(position);
    previewPosition = null;
    addEntity(makePointEntity(Cesium, position));

    if (positions.length === 1) {
      dynamicEntity = viewer.entities.add({
        polyline: mode === 'distance' || mode === 'height'
          ? {
              positions: sketchPositions,
              width: 3,
              material: Cesium.Color.CYAN
            }
          : undefined,
        polygon: mode === 'area'
          ? {
              hierarchy: new Cesium.CallbackProperty(() => new Cesium.PolygonHierarchy(getSketchPositions()), false),
              material: Cesium.Color.CYAN.withAlpha(0.18),
              outline: true,
              outlineColor: Cesium.Color.CYAN
            }
          : undefined
      });
    }

    if (mode === 'height' && positions.length >= 2) {
      finish();
      registry.deactivateActiveTool();
    }
  }, Cesium.ScreenSpaceEventType.LEFT_CLICK);

  handler.setInputAction((movement) => {
    if (!positions.length || finished) return;
    const position = getSurfacePosition(viewer, Cesium, movement.endPosition);
    if (!position) return;
    previewPosition = position;
  }, Cesium.ScreenSpaceEventType.MOUSE_MOVE);

  handler.setInputAction(() => {
    finish();
    registry.deactivateActiveTool();
  }, Cesium.ScreenSpaceEventType.RIGHT_CLICK);

  registry.state.statusText = mode === 'area' ? '左键绘制面，右键结束' : '左键取点，右键结束';

  return () => {
    handler.destroy();
    cleanupDynamic();
  };
}

export function registerCesiumMeasurementTools(registry) {
  let cleanup = null;
  const measurementEntities = [];
  const modes = [
    { id: 'measure-distance', label: '距离', category: 'measure', mode: 'distance' },
    { id: 'measure-area', label: '面积', category: 'measure', mode: 'area' },
    { id: 'measure-height', label: '高度', category: 'measure', mode: 'height' }
  ];

  modes.forEach((tool) => {
    registry.registerTool({
      ...tool,
      activate() {
        cleanup?.();
        cleanup = createSketchController(registry, tool.mode, measurementEntities);
      },
      deactivate() {
        cleanup?.();
        cleanup = null;
      },
      destroy() {
        cleanup?.();
        cleanup = null;
      }
    });
  });

  registry.registerTool({
    id: 'measure-clear',
    label: '清空',
    category: 'measure',
    activate() {
      const viewer = registry.getViewer();
      while (measurementEntities.length) {
        try { viewer?.entities?.remove?.(measurementEntities.pop()); } catch (_) {}
      }
      registry.state.measurements = [];
      registry.state.statusText = '测量和绘制结果已清空';
      registry.deactivateActiveTool();
    }
  });
}
