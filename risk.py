from shapely.geometry import LineString, Point
import pandas as pd

def piracy_hits_along_route(route_coords_lonlat, piracy_df: pd.DataFrame, buffer_km: float):
    """Returns (hits, total_incidents)."""
    if piracy_df is None or piracy_df.empty:
        return 0, 0
    route_line = LineString([(lon,lat) for lon,lat in route_coords_lonlat])
    buf_deg = (1/111.32)*float(buffer_km)
    total_inc = len(piracy_df)
    lons=[p[0] for p in route_coords_lonlat]; lats=[p[1] for p in route_coords_lonlat]
    min_lon,max_lon = min(lons)-buf_deg*1.5, max(lons)+buf_deg*1.5
    min_lat,max_lat = min(lats)-buf_deg*1.5, max(lats)+buf_deg*1.5
    cand = piracy_df[(piracy_df["LON"].between(min_lon,max_lon)) & (piracy_df["LAT"].between(min_lat,max_lat))]
    buf_geom = route_line.buffer(buf_deg)
    risk_hits=0
    for _,row in cand.iterrows():
        try: pt=Point(float(row["LON"]), float(row["LAT"]))
        except: continue
        if buf_geom.intersects(pt): risk_hits+=1
    return risk_hits, total_inc
