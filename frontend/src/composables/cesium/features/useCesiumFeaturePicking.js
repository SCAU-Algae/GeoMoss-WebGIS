function getFeatureProperties(feature) {
  if (!feature) return {};
  const names = typeof feature.getPropertyNames === 'function' ? feature.getPropertyNames() : [];
  const props = {};
  names.forEach((name) => {
    try {
      const value = feature.getProperty(name);
      if (value && typeof value === 'object' && !Array.isArray(value)) {
        Object.entries(value).forEach(([childKey, childValue]) => {
          if (childKey && props[childKey] === undefined) props[childKey] = childValue;
        });
      } else {
        props[name] = value;
      }
    } catch (_) {}
  });
  return props;
}

function resolveFeatureTitle(props) {
  return String(
    props?.name
    || props?.NAME
    || props?.名称
    || props?.building_id
    || props?.batch_id
    || '建筑属性'
  );
}

function toWindowScreenPoint(viewer, position) {
  const rect = viewer?.scene?.canvas?.getBoundingClientRect?.();
  return {
    x: Number(rect?.left || 0) + Number(position?.x || 0),
    y: Number(rect?.top || 0) + Number(position?.y || 0)
  };
}

function setFeatureColor(Cesium, feature, color) {
  try {
    if ('color' in feature) feature.color = color;
  } catch (_) {}
}

function resolvePickedFeature(picked) {
  if (!picked) return null;
  if (typeof picked.getPropertyNames === 'function') return picked;
  if (picked.id && typeof picked.id.getPropertyNames === 'function') return picked.id;
  if (picked.primitive && typeof picked.primitive.getPropertyNames === 'function') return picked.primitive;
  return null;
}

export function attachCesiumFeaturePicking(registry) {
  const viewer = registry.getViewer();
  const Cesium = registry.getCesium();
  if (!viewer || !Cesium) return () => {};

  const handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
  let highlighted = null;
  let selected = null;
  const highlightColor = Cesium.Color.YELLOW.withAlpha(0.55);
  const selectedColor = Cesium.Color.CYAN.withAlpha(0.72);

  function clearHighlight() {
    if (highlighted && highlighted !== selected) {
      setFeatureColor(Cesium, highlighted, Cesium.Color.WHITE);
    }
    highlighted = null;
  }

  handler.setInputAction((movement) => {
    if (registry.state.activeToolId) return;
    const picked = resolvePickedFeature(viewer.scene.pick(movement.endPosition));
    if (!picked) {
      clearHighlight();
      return;
    }
    if (highlighted !== picked) clearHighlight();
    highlighted = picked;
    if (highlighted !== selected) setFeatureColor(Cesium, highlighted, highlightColor);
  }, Cesium.ScreenSpaceEventType.MOUSE_MOVE);

  handler.setInputAction((movement) => {
    if (registry.state.activeToolId) return;
    const picked = resolvePickedFeature(viewer.scene.pick(movement.position));
    if (!picked) {
      if (selected) setFeatureColor(Cesium, selected, Cesium.Color.WHITE);
      selected = null;
      registry.state.selectedFeature = null;
      return;
    }
    if (selected && selected !== picked) {
      setFeatureColor(Cesium, selected, Cesium.Color.WHITE);
    }
    selected = picked;
    setFeatureColor(Cesium, selected, selectedColor);
    const properties = getFeatureProperties(picked);
    registry.state.selectedFeature = {
      screen: toWindowScreenPoint(viewer, movement.position),
      title: resolveFeatureTitle(properties),
      properties
    };
  }, Cesium.ScreenSpaceEventType.LEFT_CLICK);

  return () => {
    clearHighlight();
    if (selected) setFeatureColor(Cesium, selected, Cesium.Color.WHITE);
    selected = null;
    handler.destroy();
  };
}
