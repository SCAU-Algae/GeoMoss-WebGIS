/**
 * Open-Meteo Weather API — free, no key, rich data.
 * Includes adapter to normalize into the format expected by WeatherChartPanel.
 */

const WMO = {
  0: '晴', 1: '大部晴', 2: '多云', 3: '阴',
  45: '雾', 48: '霜雾',
  51: '毛毛雨', 53: '毛毛雨', 55: '毛毛雨',
  61: '小雨', 63: '中雨', 65: '大雨',
  71: '小雪', 73: '中雪', 75: '大雪', 77: '雪粒',
  80: '阵雨', 81: '中阵雨', 82: '大阵雨',
  85: '阵雪', 86: '大阵雪',
  95: '雷暴', 96: '冰雹雷暴', 99: '强冰雹雷暴',
};

const WMO_ICON = {
  0: '☀️', 1: '🌤️', 2: '⛅', 3: '☁️',
  45: '🌫️', 48: '🌫️',
  51: '🌦️', 53: '🌦️', 55: '🌦️',
  61: '🌧️', 63: '🌧️', 65: '🌧️',
  71: '🌨️', 73: '🌨️', 75: '❄️', 77: '❄️',
  80: '🌧️', 81: '🌧️', 82: '⛈️',
  85: '🌨️', 86: '🌨️',
  95: '⛈️', 96: '⛈️', 99: '⛈️',
};

const WIND_DIRS = ['北', '东北', '东', '东南', '南', '西南', '西', '西北'];

function windDir(deg) { return WIND_DIRS[Math.round(deg / 45) % 8]; }

function weatherText(code) { return WMO[code] || '未知'; }
function weatherIcon(code) { return WMO_ICON[code] || '🌤️'; }
function formatDate(iso) {
  const d = new Date(iso);
  return `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
function dayOfWeek(iso) {
  const days = ['7', '1', '2', '3', '4', '5', '6'];
  return days[new Date(iso).getDay()];
}

export async function fetchOpenMeteo(lat, lon) {
  const params = new URLSearchParams({
    latitude: lat.toFixed(4),
    longitude: lon.toFixed(4),
    current: 'temperature_2m,relative_humidity_2m,apparent_temperature,weather_code,wind_speed_10m,wind_direction_10m,uv_index',
    daily: 'weather_code,temperature_2m_max,temperature_2m_min,precipitation_probability_max,wind_speed_10m_max,wind_direction_10m_dominant',
    hourly: 'temperature_2m,precipitation_probability,weather_code',
    timezone: 'Asia/Shanghai',
    forecast_days: '7',
  });

  const resp = await fetch(`https://api.open-meteo.com/v1/forecast?${params}`);
  if (!resp.ok) throw new Error(`Open-Meteo ${resp.status}`);
  const raw = await resp.json();

  // Adapt live weather to Amap-compatible format
  const c = raw.current;
  const live = {
    weather: weatherText(c.weather_code),
    temperature: c.temperature_2m,
    humidity: c.relative_humidity_2m,
    windDirection: windDir(c.wind_direction_10m),
    winddirection: windDir(c.wind_direction_10m),
    windPowerText: `${(c.wind_speed_10m || 0).toFixed(1)} km/h`,
    windpower: `${(c.wind_speed_10m || 0).toFixed(1)}`,
    reportTime: c.time,
    reporttime: c.time,
    province: '',
    city: '',
    adcode: '',
    _apparentTemp: c.apparent_temperature_2m,
    _uvIndex: c.uv_index,
    _weatherIcon: weatherIcon(c.weather_code),
  };

  // Adapt daily forecast
  const casts = [];
  for (let i = 0; i < raw.daily.time.length; i++) {
    casts.push({
      date: raw.daily.time[i],
      week: dayOfWeek(raw.daily.time[i]),
      dayWeather: weatherText(raw.daily.weather_code[i]),
      dayweather: weatherText(raw.daily.weather_code[i]),
      nightWeather: weatherText(raw.daily.weather_code[i]),
      nightweather: weatherText(raw.daily.weather_code[i]),
      dayTemp: raw.daily.temperature_2m_max[i],
      daytemp: String(raw.daily.temperature_2m_max[i]),
      nightTemp: raw.daily.temperature_2m_min[i],
      nighttemp: String(raw.daily.temperature_2m_min[i]),
      dayWind: windDir(raw.daily.wind_direction_10m_dominant?.[i] || 0),
      daywind: windDir(raw.daily.wind_direction_10m_dominant?.[i] || 0),
      nightWind: windDir(raw.daily.wind_direction_10m_dominant?.[i] || 0),
      nightwind: windDir(raw.daily.wind_direction_10m_dominant?.[i] || 0),
      dayPowerText: `${raw.daily.wind_speed_10m_max?.[i] || 0} km/h`,
      daypower: `${raw.daily.wind_speed_10m_max?.[i] || 0}`,
      nightPowerText: `${raw.daily.wind_speed_10m_max?.[i] || 0} km/h`,
      nightpower: `${raw.daily.wind_speed_10m_max?.[i] || 0}`,
      _precipProb: raw.daily.precipitation_probability_max?.[i],
      _dayIcon: weatherIcon(raw.daily.weather_code[i]),
    });
  }

  // Hourly data
  const hourly = [];
  for (let i = 0; i < raw.hourly.time.length; i++) {
    hourly.push({
      time: raw.hourly.time[i],
      temp: raw.hourly.temperature_2m[i],
      precipProb: raw.hourly.precipitation_probability[i],
      icon: weatherIcon(raw.hourly.weather_code[i]),
      weather: weatherText(raw.hourly.weather_code[i]),
    });
  }

  return { live, forecast: { casts, province: live.province, city: live.city, reporttime: live.reporttime }, hourly, raw };
}
