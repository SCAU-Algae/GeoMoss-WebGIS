function fillZeros(size) {
  return new Float32Array(size * size);
}

export function createHeightmapTerrainProvider(Cesium, layer) {
  if (!Cesium?.CustomHeightmapTerrainProvider) return null;
  const template = String(layer?.tileUrlTemplate || '').trim();
  if (!template) return null;

  const size = Number(layer?.metadata?.heightmap_size || 32);
  const cache = new Map();

  function tileUrl(x, y, level) {
    return template
      .replace('{x}', encodeURIComponent(String(x)))
      .replace('{y}', encodeURIComponent(String(y)))
      .replace('{z}', encodeURIComponent(String(level)));
  }

  async function loadTile(x, y, level) {
    const key = `${level}/${x}/${y}`;
    if (cache.has(key)) return cache.get(key);

    const promise = fetch(tileUrl(x, y, level))
      .then((response) => {
        if (!response.ok) throw new Error(`terrain ${response.status}`);
        return response.json();
      })
      .then((payload) => {
        const values = Array.isArray(payload?.heights) ? payload.heights : [];
        if (!payload?.available || values.length !== size * size) return fillZeros(size);
        return Float32Array.from(values.map((value) => Number(value) || 0));
      })
      .catch(() => fillZeros(size));

    cache.set(key, promise);
    if (cache.size > 256) {
      const firstKey = cache.keys().next().value;
      cache.delete(firstKey);
    }
    return promise;
  }

  return new Cesium.CustomHeightmapTerrainProvider({
    width: size,
    height: size,
    tilingScheme: new Cesium.GeographicTilingScheme(),
    callback: loadTile
  });
}
