# app.py
import os, io, json, csv, itertools
from typing import Dict, List, Optional
import pandas as pd
import streamlit as st
import folium
from folium.plugins import HeatMap
from streamlit_folium import st_folium

from routing import compute_route, list_to_latlon, eta_hours
from weather_providers import get_weather, render_weather_card_safe
from data_sources import (
    load_wpi, clean_piracy_df, load_congestion_advanced, load_alias_map,
    get_row_by_main, latlon_from_row, _norm_country,
)
from risk import piracy_hits_along_route
from portswitch import evaluate_portswitch, draw_portswitch_markers

# ---------------- App config ----------------
st.set_page_config(page_title="Sea Route Visualizer", page_icon="🗺️", layout="wide")
st.title("🗺️ Sea Route Visualizer (Sea-lanes • Weather • Risk • CO₂ & Cost • Smart PortSwitch)")

for k, v in {"route_info": None, "alt_info": None}.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ==================== 1) Data Sources ====================
st.markdown("### 1) Data Sources")
left, right = st.columns(2, gap="large")
with left:
    wpi_file = st.file_uploader("Upload World Port Index CSV (UpdatedPub150.csv)", type=["csv"])
with right:
    piracy_file = st.file_uploader("Upload Piracy Incidents CSV (any LAT/LON columns)", type=["csv"])

rows, mains, country_col, ports_by_country = load_wpi(wpi_file.getvalue() if wpi_file else None)

piracy_df = None
if piracy_file:
    try:
        raw = pd.read_csv(piracy_file)
        piracy_df = clean_piracy_df(raw)
        if piracy_df.empty:
            st.warning("Piracy CSV loaded but no valid LAT/LON found.")
        else:
            st.caption(
                f"Loaded {len(piracy_df):,} incidents • "
                f"LAT [{piracy_df['LAT'].min():.2f},{piracy_df['LAT'].max():.2f}] • "
                f"LON [{piracy_df['LON'].min():.2f},{piracy_df['LON'].max():.2f}]"
            )
    except Exception as e:
        st.warning(f"Failed to read piracy CSV: {e}")
        piracy_df = None

# ==================== 2) Controls (Form) ====================
st.markdown("---")
st.markdown("### 2) Controls")

with st.form("controls"):
    # ---------- input mode ----------
    mode = st.radio("Input mode", ["Pick ports from list", "Enter coordinates"], horizontal=True)

    # if WPI not loaded, force coordinate mode to avoid empty selects and the red warning
    no_wpi = not mains
    if no_wpi:
        st.info("Upload a valid WPI CSV first (or place UpdatedPub150.csv next to app.py). Falling back to 'Enter coordinates'.")
        mode = "Enter coordinates"

    # group by country
    use_country = (country_col is not None) and st.checkbox("Group ports by country (subcategory)", value=True, disabled=no_wpi)

    # cascading selectors
    def pick_country_port(label_prefix: str):
        if use_country and ports_by_country:
            country_val = st.selectbox(
                f"{label_prefix} country",
                options=sorted(ports_by_country.keys()),
                key=f"{label_prefix}_country",
                disabled=no_wpi
            )
            ports = ports_by_country.get(country_val, [])
            return st.selectbox(
                f"{label_prefix} port",
                options=ports,
                index=0 if ports else None,
                key=f"{label_prefix}_port_{country_val}",
                disabled=no_wpi or not ports
            )
        else:
            return st.selectbox(
                f"{label_prefix} port",
                options=mains if mains else [],
                key=f"{label_prefix}_port_all",
                disabled=no_wpi
            )

    col1, col2, col3 = st.columns([1,1,1])
    if mode == "Pick ports from list":
        with col1:
            origin = pick_country_port("Origin")
        with col2:
            dest = pick_country_port("Destination")
        with col3:
            alt_dest = st.selectbox(
                "Alternate destination (optional)",
                options=(["— none —"] + mains) if mains else ["— none —"],
                disabled=no_wpi
            )
    else:
        with col1:
            o_lat = st.number_input("Origin lat", value=3.000, format="%.6f")
            o_lon = st.number_input("Origin lon", value=101.400, format="%.6f")
        with col2:
            d_lat = st.number_input("Destination lat", value=51.950, format="%.6f")
            d_lon = st.number_input("Destination lon", value=4.050, format="%.6f")
        with col3:
            alt_lat = st.number_input("Alt dest lat (optional)", value=0.0, format="%.6f")
            alt_lon = st.number_input("Alt dest lon (optional)", value=0.0, format="%.6f")
        alt_dest = None

    col4, col5, col6 = st.columns([1,1,1])
    with col4:
        speed_kn = st.slider("Speed (knots)", 6.0, 30.0, 18.0, 0.5)
    with col5:
        buffer_km = st.slider("Risk buffer (km)", 10, 200, 50, 5)
    with col6:
        optimize = st.checkbox("Optimize order of intermediate stops", value=False, disabled=(no_wpi or mode!="Pick ports from list"))

    # ---- CO2 & Fuel Cost inputs ----
    st.markdown("#### Fuel & Emissions (for CO₂ and cost calculations)")
    ef_default = {"HFO": 3.114, "VLSFO": 3.114, "MGO/MDO": 3.206, "LNG": 2.750}
    bunker_default = {"HFO": 500.0, "VLSFO": 600.0, "MGO/MDO": 900.0, "LNG": 1000.0}

    f1, f2, f3, f4 = st.columns([1.1,1,1,1])
    with f1:
        fuel_type = st.selectbox("Fuel type", list(ef_default.keys()), index=1)
    with f2:
        fuel_price = st.number_input("Bunker price (USD/tonne)", min_value=0.0,
                                     value=float(bunker_default[fuel_type]), step=10.0)
    with f3:
        cons_tpd = st.number_input("Fuel consumption at this speed (tonnes/day)",
                                   min_value=0.0, value=30.0, step=0.5)
    with f4:
        ef_tco2_per_t_fuel = st.number_input("CO₂ factor (tCO₂ per t fuel)",
                                             min_value=0.0, value=float(ef_default[fuel_type]), step=0.01)

    # ---- Weather controls ----
    st.markdown("#### Weather")
    wx_col1, wx_col2, wx_col3, wx_col4 = st.columns([1.2, 1, 1, 1])
    with wx_col1:
        weather_provider = st.selectbox("Provider", ["OpenWeather", "Open-Meteo (no key)"], index=0)
    with wx_col2:
        owm_key = st.text_input("OpenWeather key", type="password", disabled=(weather_provider!="OpenWeather"))
    with wx_col3:
        show_weather = st.checkbox("Show @ origin/destination", value=True)
    with wx_col4:
        sample_along = st.checkbox("Sample along route", value=False)
    samples = st.slider("Route samples", 2, 10, 4, 1, disabled=not sample_along)

    # ---- Optional stops (only when WPI exists) ----
    stops = []
    if (mode=="Pick ports from list") and (not no_wpi):
        stop_opts = [m for m in mains if m not in (origin, dest)]
        stops = st.multiselect("Intermediate stops (optional)", options=stop_opts)

    # IMPORTANT: always render the submit button (don’t st.stop() before this)
    submitted = st.form_submit_button("Compute / Update")

# ==================== Extra inputs (not in the form) ====================
congestion_file = st.file_uploader("Upload Port Congestion CSV", type=["csv"])
alias_file      = st.file_uploader("Optional: Port Name Alias CSV (WPI_Name, Source_Name)", type=["csv"])
CONG = load_congestion_advanced(congestion_file.getvalue() if congestion_file else None)
ALIAS = load_alias_map(alias_file.getvalue() if alias_file else None)
m1, m2 = st.columns(2)
with m1:
    fuzzy_threshold = st.slider("Fuzzy match threshold", 0, 100, 88, 1)
with m2:
    geo_radius_km = st.slider("Geo nearest radius (km) — if congestion CSV has lat/lon", 0, 200, 50, 5)

# ==================== 3) Compute after submit ====================
route_info = st.session_state.route_info
alt_info   = st.session_state.alt_info

if submitted:
    # validate AFTER submit so the button always exists
    if mode == "Pick ports from list":
        if not mains:
            st.error("Please upload a valid WPI CSV first.")
            st.stop()
        if not origin or not dest:
            st.error("Please select both origin and destination ports.")
            st.stop()

    # resolve endpoints
    if mode == "Pick ports from list":
        o_row=get_row_by_main(origin, rows); d_row=get_row_by_main(dest, rows)
        if not o_row or not d_row:
            st.error("Could not resolve selected ports."); st.stop()
        o_lat,o_lon = latlon_from_row(o_row); d_lat,d_lon = latlon_from_row(d_row)
        o_name, d_name = origin, dest
        alt_target=None
        if alt_dest and alt_dest!="— none —":
            a_row=get_row_by_main(alt_dest, rows)
            if a_row:
                a_lat,a_lon = latlon_from_row(a_row)
                alt_target=("Alt", a_lon, a_lat)
    else:
        o_name, d_name = "Origin (custom)", "Destination (custom)"
        alt_target=None
        if ("alt_lat" in locals()) and ("alt_lon" in locals()) and (alt_lat,alt_lon)!=(0.0,0.0):
            alt_target=("Alt (custom)", alt_lon, alt_lat)

    # path building (with optional stop optimization)
    chosen_path=[(o_lat,o_lon,o_name)]
    if (mode=="Pick ports from list") and stops and st.session_state.get("allow_opt", True) and st.session_state.get("allow_opt", True):
        if optimize:
            best_nm=float("inf"); best_seq=None
            for perm in itertools.permutations(stops):
                seq=[o_name,*perm,d_name]
                nm_sum=0.0; ok=True; resolved=[]
                for nm in seq:
                    if nm==o_name: resolved.append((o_lat,o_lon,o_name)); continue
                    if nm==d_name: resolved.append((d_lat,d_lon,d_name)); continue
                    rw=get_row_by_main(nm, rows)
                    if not rw: ok=False; break
                    lat,lon=latlon_from_row(rw); resolved.append((lat,lon,nm))
                if not ok: continue
                for i in range(len(resolved)-1):
                    _,_, nm_leg = compute_route(resolved[i][0],resolved[i][1],resolved[i+1][0],resolved[i+1][1])
                    nm_sum+=nm_leg
                if nm_sum<best_nm: best_nm, best_seq = nm_sum, resolved
            if best_seq:
                chosen_path=best_seq; d_lat,d_lon,d_name = best_seq[-1]
    else:
        chosen_path.append((d_lat,d_lon,d_name))

    # build final route (lon,lat)
    route_coords=[]; dist_km_total=0.0; dist_nm_total=0.0; leg_summ=[]
    for i in range(len(chosen_path)-1):
        a=chosen_path[i]; b=chosen_path[i+1]
        coords, km, nm = compute_route(a[0],a[1],b[0],b[1])
        route_coords.extend(coords if i==0 else coords[1:])  # keep lon,lat
        dist_km_total+=km; dist_nm_total+=nm
        leg_summ.append((a[2],b[2],km,nm))

    eta_total = eta_hours(dist_nm_total, speed_kn)  # hours

    # CO₂ & Fuel Cost
    days = (eta_total or 0.0) / 24.0
    fuel_tonnes = cons_tpd * days
    co2_tonnes  = fuel_tonnes * ef_tco2_per_t_fuel
    cost_usd    = fuel_tonnes * fuel_price
    co2_intensity_kg_per_nm = (co2_tonnes*1000.0)/max(dist_nm_total, 1e-6)

    # Piracy risk
    risk_hits, total_inc = piracy_hits_along_route(route_coords, piracy_df, buffer_km)

    st.session_state.route_info = dict(
        origin=chosen_path[0][2], destination=d_name,
        distance_km=dist_km_total, distance_nm=dist_nm_total,
        eta_hours=eta_total, legs=leg_summ,
        risk_hits=risk_hits, total_incidents=total_inc,
        coords_lonlat=route_coords,
        fuel_tonnes=fuel_tonnes, co2_tonnes=co2_tonnes, cost_usd=cost_usd,
        co2_intensity_kg_per_nm=co2_intensity_kg_per_nm,
        params=dict(fuel_type=fuel_type, fuel_price=fuel_price, cons_tpd=cons_tpd,
                    ef_tco2_per_t_fuel=ef_tco2_per_t_fuel)
    )

    # Alt destination
    if alt_target:
        label, a_lon, a_lat = alt_target
        ac, akm, anm = compute_route(o_lat,o_lon,a_lat,a_lon)
        eta_alt = eta_hours(anm, speed_kn)
        days_alt = (eta_alt or 0.0)/24.0
        fuel_t_alt = cons_tpd * days_alt
        st.session_state.alt_info = dict(
            origin=chosen_path[0][2], destination=label,
            distance_km=akm, distance_nm=anm,
            eta_hours=eta_alt, coords_lonlat=ac,
            fuel_tonnes=fuel_t_alt,
            co2_tonnes=fuel_t_alt*ef_tco2_per_t_fuel,
            cost_usd=fuel_t_alt*fuel_price
        )
    else:
        st.session_state.alt_info = None

# ==================== 4) Render ====================
route_info = st.session_state.route_info
alt_info   = st.session_state.alt_info

if route_info:
    st.markdown("### 3) Results")
    c1,c2,c3,c4 = st.columns(4)
    c1.metric("Origin", route_info["origin"])
    c2.metric("Destination", route_info["destination"])
    c3.metric("Distance", f"{route_info['distance_km']:,.1f} km ({route_info['distance_nm']:,.1f} NM)")
    c4.metric("ETA @ speed", f"{(route_info['eta_hours'] or 0):.1f} h")

    st.markdown("#### CO₂ & Fuel Cost (estimates)")
    e1,e2,e3,e4 = st.columns(4)
    e1.metric("Fuel used", f"{route_info['fuel_tonnes']:.2f} t")
    e2.metric("CO₂ emitted", f"{route_info['co2_tonnes']:.2f} tCO₂")
    e3.metric("CO₂ intensity", f"{route_info['co2_intensity_kg_per_nm']:.1f} kg/NM")
    e4.metric("Fuel cost", f"${route_info['cost_usd']:,.0f}")
    st.caption(
        f"Assumptions: {route_info['params']['fuel_type']} • "
        f"{route_info['params']['cons_tpd']:.1f} t/day @ selected speed • "
        f"CO₂ factor {route_info['params']['ef_tco2_per_t_fuel']:.3f} tCO₂/t fuel • "
        f"Price ${route_info['params']['fuel_price']:.0f}/t"
    )

    if route_info["total_incidents"]:
        st.caption(
            f"Risk: {route_info['risk_hits']} incidents within {int(buffer_km)} km of route "
            f"(out of {route_info['total_incidents']:,})"
        )

    oc = route_info["coords_lonlat"]  # lon,lat
    center_lat = (oc[0][1]+oc[-1][1])/2
    center_lon = (oc[0][0]+oc[-1][0])/2
    fmap = folium.Map(location=[center_lat, center_lon], zoom_start=4, tiles="CartoDB positron")

    folium.PolyLine(
        list_to_latlon(oc),
        weight=4, opacity=0.95, color="blue",
        tooltip=f"{route_info['origin']} → {route_info['destination']}"
    ).add_to(fmap)
    folium.Marker([oc[0][1], oc[0][0]], tooltip=route_info["origin"]).add_to(fmap)
    folium.Marker([oc[-1][1], oc[-1][0]], tooltip=route_info["destination"]).add_to(fmap)

    if piracy_df is not None and not piracy_df.empty:
        try:
            pts = piracy_df[["LAT","LON"]].astype(float).values.tolist()
            HeatMap([[lat,lon,1] for lat,lon in pts], radius=8, blur=5).add_to(fmap)
        except Exception:
            pass

    if alt_info:
        ac = alt_info["coords_lonlat"]
        folium.PolyLine(
            list_to_latlon(ac),
            weight=4, opacity=0.85, color="red",
            tooltip=f"{alt_info['origin']} → {alt_info['destination']} (alt)"
        ).add_to(fmap)
        folium.Marker([ac[-1][1], ac[-1][0]], tooltip=f"Alt: {alt_info['destination']}").add_to(fmap)
        a1,a2,a3 = st.columns(3)
        a1.metric("ALT distance", f"{alt_info['distance_km']:,.1f} km ({alt_info['distance_nm']:,.1f} NM)")
        a2.metric("ALT CO₂", f"{alt_info['co2_tonnes']:.2f} tCO₂")
        a3.metric("ALT fuel cost", f"${alt_info['cost_usd']:,.0f}")
        st.caption("Blue = main route, Red = alternate destination")

    st_folium(fmap, width=None, height=600)

    # legs table
    if route_info["legs"]:
        df_legs = pd.DataFrame([
            {"Leg": f"{a} → {b}", "Distance (km)": km, "Distance (NM)": nm}
            for a,b,km,nm in route_info["legs"]
        ])
        st.dataframe(df_legs, use_container_width=True)

    # ---------- Weather ----------
    st.markdown("### 4) Weather")
    if not st.session_state.get("show_weather_toggle_overridden", False):  # no-op flag
        show_weather = 'show_weather' in locals() and show_weather
    if not show_weather:
        st.info("Weather disabled.")
    else:
        o_lat, o_lon = oc[0][1], oc[0][0]
        d_lat, d_lon = oc[-1][1], oc[-1][0]
        w1 = get_weather(weather_provider, o_lat, o_lon, owm_key, units="metric")
        w2 = get_weather(weather_provider, d_lat, d_lon, owm_key, units="metric")
        colw1, colw2 = st.columns(2)
        with colw1: render_weather_card_safe("Origin weather", w1)
        with colw2: render_weather_card_safe("Destination weather", w2)

        if 'sample_along' in locals() and sample_along:
            st.markdown("#### Weather along route (samples)")
            idxs = [round(i*(len(oc)-1)/(samples-1)) for i in range(samples)]
            rows_wx = []
            for j, idx in enumerate(idxs, start=1):
                lon, lat = oc[idx]
                wx = get_weather(weather_provider, lat, lon, owm_key, units="metric")
                if wx and not wx.get("_error") and wx.get("current"):
                    cur = wx["current"]
                    rows_wx.append({
                        "#": j, "lat": f"{lat:.3f}", "lon": f"{lon:.3f}",
                        "temp_c": cur.get("temp_c"),
                        "wind_kph": cur.get("wind_kph"),
                        "gust_kph": cur.get("gust_kph"),
                        "precip_mm_1h": cur.get("precip_mm_1h"),
                    })
                elif wx and wx.get("_error"):
                    st.caption(f"Sample {j}: {wx['_error']}")
            if rows_wx:
                st.dataframe(pd.DataFrame(rows_wx), use_container_width=True)

    # ---------- Downloads ----------
    colD1,colD2 = st.columns(2)
    gj = {"type":"Feature",
          "geometry":{"type":"LineString","coordinates":route_info["coords_lonlat"]},
          "properties":{"origin":route_info["origin"],"destination":route_info["destination"],
                        "distance_km":route_info["distance_km"],"distance_nm":route_info["distance_nm"],
                        "eta_hours_at_speed": route_info["eta_hours"],
                        "fuel_tonnes": route_info["fuel_tonnes"],
                        "co2_tonnes": route_info["co2_tonnes"],
                        "fuel_cost_usd": route_info["cost_usd"]}}
    colD1.download_button("Download Route GeoJSON", data=json.dumps(gj, indent=2),
                          file_name="route.geojson", mime="application/geo+json")
    buf=io.StringIO(); cw=csv.writer(buf); cw.writerow(["lon","lat"])
    for lon,lat in route_info["coords_lonlat"]: cw.writerow([lon,lat])
    colD2.download_button("Download Route CSV", data=buf.getvalue(),
                          file_name="route_points.csv", mime="text/csv")

    # ---------- Smart PortSwitch ----------
    st.markdown("---")
    st.markdown("### 5) Smart PortSwitch Evaluation")
    ps_controls = {
        "same_country_only": st.checkbox("Limit to same country", value=True, disabled=(country_col is None)),
        "radius_nm": st.slider("Max alt distance from baseline (NM)", 0, 500, 200, 10),
        "top_n_show": st.slider("Show top N candidates", 3, 20, 8, 1),
        "w_time": st.slider("Weight: ETA", 0.0, 1.0, 0.25, 0.05),
        "w_cong": st.slider("Weight: Congestion", 0.0, 1.0, 0.25, 0.05),
        "w_cost": st.slider("Weight: Cost", 0.0, 1.0, 0.25, 0.05),
        "w_co2":  st.slider("Weight: CO₂", 0.0, 1.0, 0.25, 0.05),
        "fuzzy_threshold": fuzzy_threshold,
    }

    ps_result = evaluate_portswitch(
        route_info, rows, mains, ports_by_country, country_col,
        speed_kn, cons_tpd, ef_tco2_per_t_fuel, fuel_price,
        CONG, ALIAS, fuzzy_threshold, geo_radius_km, ps_controls
    )

    if ps_result is None:
        st.info("No alternate ports found that match the filters.")
    else:
        df, best_row = ps_result
        st.dataframe(
            df[["Port", "Distance_NM", "ETA_h", "Wait_h", "Adj_ETA_h", "Cost_USD", "CO2_t", "score"]]
            .head(ps_controls["top_n_show"]),
            use_container_width=True
        )
        st.success(f"Recommendation: **{best_row['Port']}** (score {best_row['score']:.3f})")

        draw_portswitch_markers(df, ps_controls["top_n_show"], best_row, fmap)
        st_folium(fmap, width=None, height=600)

        if st.button("Choose Best Route"):
            st.session_state.route_info.update({
                "destination": str(best_row["Port"]),
                "distance_km": float(best_row["Distance_NM"]) / 0.539957,
                "distance_nm": float(best_row["Distance_NM"]),
                "eta_hours": float(best_row["Adj_ETA_h"]),
                "fuel_tonnes": float(best_row["Fuel_t"]),
                "co2_tonnes": float(best_row["CO2_t"]),
                "cost_usd": float(best_row["Cost_USD"]),
                "coords_lonlat": list(best_row["coords"]),
            })
            st.toast("✅ Best route selected. Map & calculations updated.")
else:
    st.info("Upload your WPI CSV (or place it next to app.py), set controls, then press **Compute / Update**.")
