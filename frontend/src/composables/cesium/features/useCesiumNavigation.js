export function captureCameraBookmark(viewer, Cesium, name = '') {
  if (!viewer || !Cesium) return null;
  const camera = viewer.camera;
  const carto = camera.positionCartographic;
  return {
    id: `bookmark_${Date.now()}`,
    name: name || new Date().toLocaleTimeString('zh-CN', { hour12: false }),
    destination: {
      lon: Cesium.Math.toDegrees(carto.longitude),
      lat: Cesium.Math.toDegrees(carto.latitude),
      height: carto.height
    },
    orientation: {
      heading: camera.heading,
      pitch: camera.pitch,
      roll: camera.roll
    }
  };
}

export function flyToBookmark(viewer, Cesium, bookmark) {
  if (!viewer || !Cesium || !bookmark?.destination) return false;
  viewer.camera.flyTo({
    destination: Cesium.Cartesian3.fromDegrees(
      Number(bookmark.destination.lon || 0),
      Number(bookmark.destination.lat || 0),
      Number(bookmark.destination.height || 10000)
    ),
    orientation: {
      heading: Number(bookmark.orientation?.heading || 0),
      pitch: Number(bookmark.orientation?.pitch || -Cesium.Math.PI_OVER_TWO),
      roll: Number(bookmark.orientation?.roll || 0)
    },
    duration: 1.4
  });
  return true;
}

export function flyToShenzhen(viewer, Cesium) {
  viewer?.camera?.flyTo?.({
    destination: Cesium.Cartesian3.fromDegrees(114.0579, 22.5431, 28000),
    orientation: {
      heading: Cesium.Math.toRadians(0),
      pitch: Cesium.Math.toRadians(-42),
      roll: 0
    },
    duration: 1.8
  });
}

export function flyToChina(viewer, Cesium) {
  viewer?.camera?.flyTo?.({
    destination: Cesium.Cartesian3.fromDegrees(104.1954, 35.8617, 15000000),
    orientation: {
      heading: 0,
      pitch: -Cesium.Math.PI_OVER_TWO,
      roll: 0
    },
    duration: 1.8
  });
}
