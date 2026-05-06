/**
 * 高德地理编码 — 前端直连，不走后端代理。
 * 密钥通过 Vite 环境变量注入。
 */

const AMAP_KEY = import.meta.env.VITE_AMAP_WEB_SERVICE_KEY || 'f90670d65c72653d7c379d95db238cb5';

function wgs84ToGcj02(lng, lat) {
    const d = Math.PI / 180;
    const a = 6378245.0;
    const ee = 0.00669342162296594323;
    let dLng = lng - 105.0, dLat = lat - 35.0;
    let radLat = lat * d, magic = Math.sin(radLat);
    magic = 1 - ee * magic * magic;
    let sqrtMagic = Math.sqrt(magic);
    let dLng2 = (300.0 * dLng * dLng) / (a * (1 - ee)) + (2.0 * dLng * dLng * dLng) / a;
    let dLat2 = (300.0 * dLat * dLat) / (a * (1 - ee)) + (2.0 * dLat * dLat * dLat) / a;
    return [lng + dLng2, lat + dLat2];
}

/**
 * 直连高德逆地理编码 — 返回区/市/省 + adcode。
 */
export async function amapReverseGeocode(lng, lat) {
    const [gcjLng, gcjLat] = wgs84ToGcj02(lng, lat);
    const url = `https://restapi.amap.com/v3/geocode/regeo?location=${gcjLng.toFixed(6)},${gcjLat.toFixed(6)}&key=${AMAP_KEY}&extensions=base`;
    const resp = await fetch(url);
    if (!resp.ok) throw new Error(`高德逆地理编码失败 (${resp.status})`);
    const json = await resp.json();
    if (json.status !== '1') throw new Error(json.info || '高德逆地理编码失败');

    const ac = json.regeocode?.addressComponent || {};
    return {
        province: ac.province || '',
        city: ac.city?.replace('市', '') || ac.province || '',
        district: ac.district || '',
        adcode: ac.adcode || '',
        formatted: json.regeocode?.formatted_address || '',
    };
}
