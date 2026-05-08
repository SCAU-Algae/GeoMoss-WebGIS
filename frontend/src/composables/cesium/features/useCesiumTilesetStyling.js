const COLOR_RAMP = {
  cyan: ['#d9fbff', '#7ee7ef', '#1bb8c9', '#0a7184'],
  height: ['#2dd4bf', '#a3e635', '#facc15', '#fb7185'],
  warm: ['#fff7ad', '#fbbf24', '#f97316', '#dc2626'],
  mono: ['#89f7fe', '#66a6ff', '#4f46e5', '#312e81']
};

const FILTER_HANDLER_KEY = Symbol('webgisCesiumTilesetFilterHandler');

function normalizeStyleField(field) {
  const raw = String(field || '').trim();
  if (!raw) return '';
  return raw.replace(/[^\w\u4e00-\u9fa5]/g, '');
}

function tilesetExpressionField(field) {
  const normalized = normalizeStyleField(field);
  return normalized ? `\${${normalized}}` : '';
}

function buildStyle(Cesium, settings = {}) {
  if (!Cesium?.Cesium3DTileStyle) return null;
  const opacity = Math.max(0.08, Math.min(1, Number(settings.opacity || 1)));
  const ramp = COLOR_RAMP[settings.ramp] || COLOR_RAMP.cyan;
  const solidColor = String(settings.solidColor || ramp[1] || '#7ee7ef').trim() || '#7ee7ef';
  const style = {
    color: {
      conditions: [
        ['true', `color("${solidColor}", ${opacity})`]
      ]
    }
  };

  if (settings.mode === 'height') {
    const heightExpression = tilesetExpressionField(settings.heightField || 'height_m') || '${height_m}';
    style.color = {
      evaluateColor: undefined,
      conditions: [
        [`${heightExpression} >= 180`, `color("${ramp[3]}", ${opacity})`],
        [`${heightExpression} >= 90`, `color("${ramp[2]}", ${opacity})`],
        [`${heightExpression} >= 30`, `color("${ramp[1]}", ${opacity})`],
        ['true', `color("${ramp[0]}", ${opacity})`]
      ]
    };
  }

  return new Cesium.Cesium3DTileStyle(style);
}

function getFeatureProperty(feature, field) {
  if (!feature || !field || typeof feature.getProperty !== 'function') return undefined;
  try {
    const direct = feature.getProperty(field);
    if (direct !== undefined && direct !== null) return direct;
  } catch (_) {}

  const target = String(field).toLowerCase();
  try {
    const names = typeof feature.getPropertyNames === 'function' ? feature.getPropertyNames() : [];
    for (const name of names) {
      if (String(name).toLowerCase() === target) return feature.getProperty(name);
    }
  } catch (_) {}

  try {
    const source = feature.getProperty('source');
    if (source && typeof source === 'object') {
      if (source[field] !== undefined && source[field] !== null) return source[field];
      const match = Object.keys(source).find((key) => String(key).toLowerCase() === target);
      if (match) return source[match];
    }
  } catch (_) {}

  return undefined;
}

function forEachContentFeature(content, callback) {
  const count = Number(content?.featuresLength ?? content?.batchLength ?? 0);
  if (!content || typeof content.getFeature !== 'function' || count <= 0) return;
  for (let index = 0; index < count; index += 1) {
    try {
      const feature = content.getFeature(index);
      if (feature) callback(feature);
    } catch (_) {}
  }
}

function forEachKnownTileContent(tileset, callback) {
  const seen = new Set();
  const tileGroups = [
    tileset?._selectedTiles,
    tileset?._selectedTilesToStyle,
    tileset?._visibleTiles,
    tileset?._requestedTiles
  ];

  tileGroups.forEach((tiles) => {
    if (!Array.isArray(tiles)) return;
    tiles.forEach((tile) => {
      const content = tile?.content;
      if (!content || seen.has(content)) return;
      seen.add(content);
      callback(content);
    });
  });
}

function removeFeatureFilter(tileset, { restore = false } = {}) {
  const previous = tileset?.[FILTER_HANDLER_KEY];
  if (!previous) return;
  try {
    tileset.tileVisible?.removeEventListener?.(previous);
  } catch (_) {}
  tileset[FILTER_HANDLER_KEY] = null;

  if (restore) {
    const restoreContent = (content) => forEachContentFeature(content, (feature) => {
      try { feature.show = true; } catch (_) {}
    });
    forEachKnownTileContent(tileset, restoreContent);
  }
}

function installFeatureFilter(tileset, settings = {}) {
  removeFeatureFilter(tileset, { restore: true });

  const field = String(settings.filterField || '').trim();
  const value = String(settings.filterValue || '').trim();
  if (!field || !value) return;

  const needle = value.toLowerCase();
  const applyToContent = (content) => {
    forEachContentFeature(content, (feature) => {
      const raw = getFeatureProperty(feature, field);
      const text = raw === undefined || raw === null ? '' : String(raw);
      try {
        feature.show = text.toLowerCase().includes(needle);
      } catch (_) {}
    });
  };

  const handler = (tile) => applyToContent(tile?.content);
  tileset[FILTER_HANDLER_KEY] = handler;
  try {
    tileset.tileVisible?.addEventListener?.(handler);
  } catch (_) {}
  forEachKnownTileContent(tileset, applyToContent);
}

export function applyTilesetStyle(Cesium, tileset, settings = {}) {
  if (!tileset || !Cesium) return false;
  const style = buildStyle(Cesium, settings);
  if (!style) return false;
  tileset.style = style;
  tileset.showOutline = !!settings.outline;
  installFeatureFilter(tileset, settings);
  return true;
}

export function resetTilesetStyle(tileset) {
  if (!tileset) return false;
  removeFeatureFilter(tileset, { restore: true });
  tileset.style = undefined;
  tileset.showOutline = false;
  return true;
}

export function createDefaultTilesetStyleSettings() {
  return {
    mode: 'height',
    ramp: 'cyan',
    solidColor: '#7ee7ef',
    opacity: 0.9,
    outline: false,
    heightField: 'height_m',
    filterField: '',
    filterValue: ''
  };
}
