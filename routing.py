from functools import lru_cache
from typing import List, Tuple, Dict
from searoute import searoute

def list_to_latlon(ll_lonlat: List[List[float]]) -> List[List[float]]:
    return [[lat, lon] for lon, lat in ll_lonlat]

@lru_cache(maxsize=4096)
def maritime_route(lon1: float, lat1: float, lon2: float, lat2: float, units: str="km") -> Dict:
    return searoute([lon1, lat1], [lon2, lat2], units=units)

def compute_route(a_lat: float, a_lon: float, b_lat: float, b_lon: float) -> Tuple[List[List[float]], float, float]:
    r = maritime_route(a_lon, a_lat, b_lon, b_lat, units="km")
    coords = r["geometry"]["coordinates"]  # lon,lat
    km = float(r["properties"]["length"])
    nm = km * 0.539957
    return coords, km, nm

def eta_hours(dist_nm: float, speed_kn: float):
    return None if speed_kn <= 0 else dist_nm / speed_kn
