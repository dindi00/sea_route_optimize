import requests, pandas as pd
import streamlit as st

def _ms_to_kph(x): return None if x is None else float(x) * 3.6
def _m_to_km(x):  return None if x is None else float(x) / 1000.0

@st.cache_data(ttl=900, show_spinner=False)
def fetch_weather_openweather(api_key: str, lat: float, lon: float, units: str="metric", lang: str="en") -> dict:
    if not api_key: return {"_error": "Missing OpenWeather API key"}
    url = "https://api.openweathermap.org/data/2.5/weather"
    params = {"lat": lat, "lon": lon, "appid": api_key.strip(), "units": units, "lang": lang}
    try:
        r = requests.get(url, params=params, timeout=15)
        if r.status_code != 200: return {"_error": f"{r.status_code} — {r.text[:200]}"}
        j = r.json()
        speed = j.get("wind", {}).get("speed")
        wind_kph = None if speed is None else float(speed)*(1.60934 if units=="imperial" else 3.6)
        gust = j.get("wind", {}).get("gust")
        gust_kph = None if gust is None else float(gust)*(1.60934 if units=="imperial" else 3.6)
        rain_1h = (j.get("rain") or {}).get("1h") or 0.0
        snow_1h = (j.get("snow") or {}).get("1h") or 0.0
        return {
            "provider":"openweather",
            "location":{"name": j.get("name",""), "lat": lat, "lon": lon},
            "current":{
                "temp_c": j.get("main", {}).get("temp") if units=="metric" else None,
                "temp_f": j.get("main", {}).get("temp") if units=="imperial" else None,
                "humidity": j.get("main",{}).get("humidity"),
                "pressure_hpa": j.get("main",{}).get("pressure"),
                "wind_kph": wind_kph, "gust_kph": gust_kph,
                "precip_mm_1h": float(rain_1h)+float(snow_1h),
                "clouds_pct": j.get("clouds",{}).get("all"),
                "condition": (j.get("weather") or [{}])[0].get("description","").title(),
            },
            "hourly":[]
        }
    except Exception as e:
        return {"_error": f"Request failed: {e}"}

@st.cache_data(ttl=900, show_spinner=False)
def fetch_weather_openmeteo(lat: float, lon: float) -> dict:
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": lat, "longitude": lon,
        "current": ["temperature_2m","precipitation","wind_speed_10m","wind_gusts_10m"],
        "hourly": ["temperature_2m","precipitation","wind_speed_10m","wind_gusts_10m","visibility"],
        "forecast_days": 2, "timezone": "auto",
    }
    try:
        r = requests.get(url, params=params, timeout=15)
        if r.status_code != 200: return {"_error": f"{r.status_code} — {r.text[:200]}"}
        j=r.json(); cur=j.get("current",{}); hourly=j.get("hourly",{}); times=hourly.get("time",[]) or []
        rows=[]
        for i,t in enumerate(times):
            rows.append({
                "time": t,
                "temp_c": (hourly.get("temperature_2m") or [None]*len(times))[i],
                "wind_kph": _ms_to_kph((hourly.get("wind_speed_10m") or [None]*len(times))[i]),
                "gust_kph": _ms_to_kph((hourly.get("wind_gusts_10m") or [None]*len(times))[i]),
                "precip_mm_1h": (hourly.get("precipitation") or [None]*len(times))[i],
                "vis_km": _m_to_km((hourly.get("visibility") or [None]*len(times))[i]),
                "condition":""
            })
        return {
            "provider":"open-meteo",
            "location":{"name":"", "lat": lat, "lon": lon},
            "current":{
                "temp_c": cur.get("temperature_2m"),
                "wind_kph": _ms_to_kph(cur.get("wind_speed_10m")),
                "gust_kph": _ms_to_kph(cur.get("wind_gusts_10m")),
                "precip_mm_1h": cur.get("precipitation"),
                "condition":""
            },
            "hourly": rows
        }
    except Exception as e:
        return {"_error": f"Request failed: {e}"}

def get_weather(provider: str, lat: float, lon: float, key: str, units: str="metric") -> dict:
    return fetch_weather_openweather(key, lat, lon, units=units) if provider=="OpenWeather" else fetch_weather_openmeteo(lat, lon)

def render_weather_card_safe(title: str, wx: dict):
    if not wx: st.info(f"{title}: Weather unavailable."); return
    if wx.get("_error"): st.warning(f"{title}: {wx['_error']}"); return
    render_weather_card_norm(title, wx)

def render_weather_card_norm(title: str, wx: dict):
    cur = wx.get("current", {})
    c1,c2,c3,c4 = st.columns(4)
    temp_display = f"{cur['temp_c']:.1f} °C" if cur.get("temp_c") is not None else \
                   (f"{cur.get('temp_f','-'):.1f} °F" if cur.get('temp_f') is not None else "—")
    c1.metric(f"{title} • Temp", temp_display)
    c2.metric("Wind", f"{cur.get('wind_kph','-')} kph")
    c3.metric("Gust", f"{cur.get('gust_kph','-')} kph")
    c4.metric("Precip (1h)", f"{(0.0 if cur.get('precip_mm_1h') is None else cur.get('precip_mm_1h'))} mm")
    st.caption((cur.get("condition") or wx.get("provider","")).strip() or "—")
    try:
        hourly = wx.get("hourly") or []
        if hourly:
            df = pd.DataFrame(hourly[:24])
            st.dataframe(df, use_container_width=True, height=260)
    except Exception:
        pass
