from typing import Dict, List, Optional, Tuple
import pandas as pd
import streamlit as st
import folium
import difflib
from math import radians, sin, cos, asin, sqrt

from routing import compute_route, eta_hours

def _haversine_nm(lat1, lon1, lat2, lon2):
    R_km = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1))*cos(radians(lat2))*sin(dlon/2)**2
    c = 2 * asin(sqrt(a))
    km = R_km * c
    return km * 0.539957

def evaluate_portswitch(
    route_info: dict,
    rows: List[Dict[str,str]],
    mains: List[str],
    ports_by_country: Dict[str, List[str]],
    country_col: Optional[str],
    speed_kn: float,
    cons_tpd: float,
    ef_tco2_per_t_fuel: float,
    fuel_price: float,
    CONG: dict,
    ALIAS: dict,
    fuzzy_threshold: int,
    geo_radius_km: float,
    ps_controls: dict
):
    from data_sources import get_row_by_main, latlon_from_row, _norm_country
    from utils import canon_name, has_rapidfuzz, rf_match

    if not route_info: return None

    oc_ll = route_info["coords_lonlat"]
    o_lon0, o_lat0 = oc_ll[0]
    d_lon0, d_lat0 = oc_ll[-1]
    baseline_dest = route_info["destination"]
    baseline_row = get_row_by_main(baseline_dest.replace(" (baseline)", ""), rows)
    baseline_country = _norm_country(baseline_row.get(country_col, "Unknown")) if (baseline_row and country_col) else "Unknown"

    # candidate list
    if ps_controls["same_country_only"] and country_col:
        candidates = ports_by_country.get(baseline_country, [])
    else:
        candidates = [p for p in (mains or [])]
    if baseline_dest not in candidates:
        candidates.append(baseline_dest)

    # radius filter around baseline dest
    cand_filtered = []
    if baseline_row:
        b_lat, b_lon = latlon_from_row(baseline_row)
        for p in candidates:
            rw = get_row_by_main(p, rows)
            if not rw: continue
            plat, plon = latlon_from_row(rw)
            if ps_controls["radius_nm"] <= 0 or _haversine_nm(b_lat, b_lon, plat, plon) <= ps_controls["radius_nm"]:
                cand_filtered.append(p)
    else:
        cand_filtered = candidates

    # origin should not be a candidate
    cand_filtered = [p for p in cand_filtered if p != route_info["origin"]]
    if not cand_filtered:
        return None

    # congestion resolver
    def resolve_wait_for_port(wpi_name: str, wpi_lat: float, wpi_lon: float) -> float:
        if not CONG or (not CONG["by_name"] and CONG["geo"] is None):
            return 0.0
        wpi_key = canon_name(wpi_name)
        by_name = CONG["by_name"]
        # alias + exact
        if ALIAS and wpi_key in ALIAS:
            src_key = ALIAS[wpi_key]
            if src_key in by_name:
                return by_name[src_key]
        if wpi_key in by_name:
            return by_name[wpi_key]
        # fuzzy
        if by_name:
            choices = list(by_name.keys())
            if has_rapidfuzz():
                match_key, score = rf_match(wpi_key, choices)
                if match_key and score >= ps_controls.get("fuzzy_threshold", 88):
                    return by_name[match_key]
            else:
                match = difflib.get_close_matches(wpi_key, choices, n=1, cutoff=ps_controls.get("fuzzy_threshold", 88)/100.0)
                if match:
                    return by_name[match[0]]
        # geo nearest
        geo_df = CONG["geo"]
        if geo_df is not None and wpi_lat is not None and wpi_lon is not None and geo_radius_km > 0:
            best = None; best_d = 1e18
            for _, r in geo_df.iterrows():
                d = _haversine_nm(wpi_lat, wpi_lon, float(r["__lat__"]), float(r["__lon__"])) * 1.852  # nm->km
                if d < best_d:
                    best_d = d; best = r
            if best is not None and best_d <= geo_radius_km:
                return float(best["__wait__"])
        return 0.0

    # compute candidates
    results = []
    for p in cand_filtered:
        rw = get_row_by_main(p, rows)
        if not rw:
            continue
        plat, plon = latlon_from_row(rw)

        coords, km, nm = compute_route(o_lat0, o_lon0, plat, plon)
        eta_h = eta_hours(nm, speed_kn) or 0.0

        wait_h = resolve_wait_for_port(p, plat, plon)

        days = (eta_h + wait_h) / 24.0
        fuel_t = cons_tpd * days
        co2_t  = fuel_t * ef_tco2_per_t_fuel
        cost_u = fuel_t * fuel_price

        results.append({
            "Port": p,
            "Distance_NM": nm,
            "ETA_h": eta_h,
            "Wait_h": wait_h,
            "Adj_ETA_h": eta_h + wait_h,
            "Fuel_t": fuel_t,
            "CO2_t": co2_t,
            "Cost_USD": cost_u,
            "coords": coords
        })

    if not results:
        return None

    df = pd.DataFrame(results)

    # normalize helper
    def norm_col(df_, col):
        rng = df_[col].max() - df_[col].min()
        if pd.isna(rng) or rng == 0:
            return pd.Series([0.0]*len(df_), index=df_.index)
        return (df_[col] - df_[col].min()) / rng

    df["ETA_h_norm"]    = norm_col(df, "ETA_h")
    df["Wait_h_norm"]   = norm_col(df, "Wait_h")
    df["Cost_USD_norm"] = norm_col(df, "Cost_USD")
    df["CO2_t_norm"]    = norm_col(df, "CO2_t")

    w_time = ps_controls["w_time"]; w_cong = ps_controls["w_cong"]
    w_cost = ps_controls["w_cost"]; w_co2  = ps_controls["w_co2"]

    df["score"] = (
        df["ETA_h_norm"]    * w_time +
        df["Wait_h_norm"]   * w_cong +
        df["Cost_USD_norm"] * w_cost +
        df["CO2_t_norm"]    * w_co2
    )

    df = df.sort_values("score", ascending=True).reset_index(drop=True)
    best = df.iloc[0]
    return df, best

def draw_portswitch_markers(df: pd.DataFrame, top_n: int, best_row: pd.Series, fmap):
    # annotate on folium map
    for _, row in df.head(top_n).iterrows():
        lat_cand, lon_cand = row["coords"][-1][1], row["coords"][-1][0]
        folium.Marker(
            [lat_cand, lon_cand],
            tooltip=f"{row['Port']} (score {row['score']:.3f})",
            icon=folium.Icon(color="green" if row["Port"]==best_row["Port"] else "gray")
        ).add_to(fmap)
