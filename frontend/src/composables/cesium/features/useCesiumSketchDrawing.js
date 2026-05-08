function getSurfacePosition(viewer, Cesium, screenPosition) {
  if (!viewer || !Cesium || !screenPosition) return null;
  const picked = viewer.scene?.pickPositionSupported ? viewer.scene.pickPosition(screenPosition) : null;
  if (picked) return picked;
  const ray = viewer.camera.getPickRay(screenPosition);
  return ray ? viewer.scene.globe.pick(ray, viewer.scene) : null;
}

function makePoint(Cesium, position, color) {
  return {
    position,
    point: {
      pixelSize: 9,
      color,
      outlineColor: Cesium.Color.WHITE,
      outlineWidth: 1.5,
      disableDepthTestDistance: Number.POSITIVE_INFINITY
    }
  };
}

function makeLabel(Cesium, position, text) {
  return {
    position,
    label: {
      text,
      font: '13px sans-serif',
      fillColor: Cesium.Color.WHITE,
      outlineColor: Cesium.Color.BLACK,
      outlineWidth: 3,
      style: Cesium.LabelStyle.FILL_AND_OUTLINE,
      pixelOffset: new Cesium.Cartesian2(0, -20),
      disableDepthTestDistance: Number.POSITIVE_INFINITY
    }
  };
}

function makeSketchName(mode, count) {
  const label = mode === 'point' ? '点' : mode === 'polyline' ? '线' : '面';
  return `临时${label} ${count + 1}`;
}

function createDrawingController(registry, mode, sketchEntities) {
  const viewer = registry.getViewer();
  const Cesium = registry.getCesium();
  if (!viewer || !Cesium) return null;

  const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
  const positions = [];
  const sessionEntities = [];
  let dynamicEntity = null;
  let previewPosition = null;
  let finished = false;
  const color = mode === 'polygon' ? Cesium.Color.fromCssColorString('#8bd17c') : Cesium.Color.fromCssColorString('#47d7c6');

  function sketchPositions() {
    if (previewPosition && positions.length) return [...positions, previewPosition];
    return positions;
  }

  function addEntity(config) {
    const entity = viewer.entities.add(config);
    sessionEntities.push(entity);
    return entity;
  }

  function cleanupDynamic() {
    if (dynamicEntity) {
      try { viewer.entities.remove(dynamicEntity); } catch (_) {}
      dynamicEntity = null;
    }
  }

  function cleanupSession() {
    cleanupDynamic();
    while (sessionEntities.length) {
      try { viewer.entities.remove(sessionEntities.pop()); } catch (_) {}
    }
  }

  function commit() {
    if (finished) return;
    finished = true;
    const finalPositions = positions.slice();
    const required = mode === 'point' ? 1 : mode === 'polyline' ? 2 : 3;
    if (finalPositions.length < required) {
      cleanupSession();
      registry.notify('点位不足，已取消本次绘制', 'warning');
      return;
    }

    if (mode === 'point') {
      addEntity(makePoint(Cesium, finalPositions[0], color));
    } else if (mode === 'polyline') {
      addEntity({
        polyline: {
          positions: finalPositions,
          width: 3,
          material: color
        }
      });
    } else {
      addEntity({
        polygon: {
          hierarchy: new Cesium.PolygonHierarchy(finalPositions),
          material: color.withAlpha(0.22),
          outline: true,
          outlineColor: color
        }
      });
    }

    const name = makeSketchName(mode, registry.state.sketches.length);
    addEntity(makeLabel(Cesium, finalPositions[finalPositions.length - 1], name));
    cleanupDynamic();
    sketchEntities.push(...sessionEntities);
    sessionEntities.length = 0;
    registry.state.sketches.unshift({
      id: `${mode}_${Date.now()}`,
      type: mode,
      label: name,
      pointCount: finalPositions.length,
      createdAt: new Date().toLocaleTimeString('zh-CN', { hour12: false })
    });
    registry.state.sketches.splice(20);
    registry.state.statusText = `已绘制：${name}`;
  }

  handler.setInputAction((movement) => {
    const position = getSurfacePosition(viewer, Cesium, movement.position);
    if (!position) return;
    positions.push(position);
    previewPosition = null;

    if (mode === 'point') {
      commit();
      registry.deactivateActiveTool();
      return;
    }

    addEntity(makePoint(Cesium, position, color));
    if (positions.length === 1) {
      dynamicEntity = viewer.entities.add({
        polyline: mode === 'polyline'
          ? {
              positions: new Cesium.CallbackProperty(() => sketchPositions(), false),
              width: 3,
              material: color
            }
          : undefined,
        polygon: mode === 'polygon'
          ? {
              hierarchy: new Cesium.CallbackProperty(() => new Cesium.PolygonHierarchy(sketchPositions()), false),
              material: color.withAlpha(0.18),
              outline: true,
              outlineColor: color
            }
          : undefined
      });
    }
  }, Cesium.ScreenSpaceEventType.LEFT_CLICK);

  handler.setInputAction((movement) => {
    if (!positions.length || finished || mode === 'point') return;
    const position = getSurfacePosition(viewer, Cesium, movement.endPosition);
    if (position) previewPosition = position;
  }, Cesium.ScreenSpaceEventType.MOUSE_MOVE);

  handler.setInputAction(() => {
    commit();
    registry.deactivateActiveTool();
  }, Cesium.ScreenSpaceEventType.RIGHT_CLICK);

  registry.state.statusText = mode === 'point' ? '左键落点' : '左键绘制，右键结束';

  return () => {
    handler.destroy();
    cleanupDynamic();
  };
}

export function registerCesiumSketchTools(registry) {
  let cleanup = null;
  const sketchEntities = [];
  const tools = [
    { id: 'draw-point', label: '点', mode: 'point' },
    { id: 'draw-line', label: '线', mode: 'polyline' },
    { id: 'draw-polygon', label: '面', mode: 'polygon' }
  ];

  tools.forEach((tool) => {
    registry.registerTool({
      id: tool.id,
      label: tool.label,
      category: 'draw',
      activate() {
        cleanup?.();
        cleanup = createDrawingController(registry, tool.mode, sketchEntities);
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
    id: 'draw-clear',
    label: '清空绘制',
    category: 'draw',
    activate() {
      const viewer = registry.getViewer();
      while (sketchEntities.length) {
        try { viewer?.entities?.remove?.(sketchEntities.pop()); } catch (_) {}
      }
      registry.state.sketches = [];
      registry.state.statusText = '临时绘制已清空';
      registry.deactivateActiveTool();
    }
  });
}
