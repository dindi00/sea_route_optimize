import os, io, csv, re, unicodedata
from typing import Dict, List, Tuple, Optional
import pandas as pd
import streamlit as st

# ---- Robust parsing for piracy csv ----
PIRACY_LAT_ALIASES = {"LAT","Latitude","latitude","Lat","LATITUDE","Y","y","lat_dd"}
PIRACY_LON_ALIASES = {"LON","Longitude","longitude","Lon","LONGITUDE","X","x","lon_dd","LONG","long","LNG","lng"}

def _parse_dms(token: str) -> Optional[float]:
    s = token.strip().upper().replace("º","°").replace("’","'").replace("”",'"')
    m = re.match(r"^\s*(\d+)[\-\s°]?(\d+)?(?:[\-\s']?(\d+(?:\.\d+)?))?\s*([NSEW])\s*$", s) or \
        re.match(r"^\s*(\d+)\s*°\s*(\d+)?\s*(?:'\s*(\d+(?:\.\d+)?)\s*\"?)?\s*([NSEW])\s*$", s)
    if not m: return None
    deg, mins, secs, hemi = float(m.group(1)), float(m.group(2) or 0), float(m.group(3) or 0), m.group(4)
    dec = deg + mins/60 + secs/3600
    return -dec if hemi in ("S","W") else dec

def _to_float_coord_general(val):
    if pd.isna(val): return None
    if isinstance(val, (int,float)): return float(val)
    s=str(val).strip()
    m = re.match(r"^\s*([0-9.+\-: °'\"/]+)\s*([NSEW])\s*$", s, re.I)
    if m:
        num, hemi = m.group(1), m.group(2).upper()
        d = _parse_dms(num) if any(ch in num for ch in "°'") else None
        if d is None:
            try: d=float(num)
            except: return None
        return -abs(d) if hemi in ("S","W") else abs(d)
    if any(ch in s for ch in "°'"):
        return _parse_dms(s)
    try: return float(s)
    except: return None

def _fix_lon_360(lon):
    if lon is None: return None
    if lon > 180.0: return lon - 360.0
    if lon < -180.0: return None
    return lon

def clean_piracy_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty: return pd.DataFrame(columns=["LAT","LON"])
    cols = {c.strip(): c for c in df.columns}
    lat_col = next((cols[c] for c in cols if c in PIRACY_LAT_ALIASES), None)
    lon_col = next((cols[c] for c in cols if c in PIRACY_LON_ALIASES), None)
    if lat_col is None or lon_col is None:
        cand = [c for c in df.columns if c.lower().startswith(("lat","y"))]
        lat_col = lat_col or (cand[0] if cand else None)
        cand = [c for c in df.columns if c.lower().startswith(("lon","x","long","lng"))]
        lon_col = lon_col or (cand[0] if cand else None)
    if lat_col is None or lon_col is None:
        return pd.DataFrame(columns=["LAT","LON"])
    lat = df[lat_col].apply(_to_float_coord_general)
    lon = df[lon_col].apply(_to_float_coord_general).apply(_fix_lon_360)
    out = pd.DataFrame({"LAT": lat, "LON": lon}).dropna()
    out = out[(out["LAT"].between(-90, 90)) & (out["LON"].between(-180, 180))]
    return out.drop_duplicates()

def _norm_country(c):
    if c is None or (isinstance(c, float) and pd.isna(c)):
        return "Unknown"
    c = re.split(r"[(/,]| - ", str(c))[0].strip()
    return c.title()

@st.cache_data(show_spinner=False)
def load_wpi(df_bytes: Optional[bytes]) -> Tuple[List[Dict[str,str]], List[str], Optional[str], Dict[str, List[str]]]:
    """
    Return: (rows, all_port_names, country_col_name_or_None, ports_by_country)
    """
    if df_bytes is None:
        path="UpdatedPub150.csv"
        if not os.path.exists(path): return [], [], None, {}
        with open(path,"rb") as f: df_bytes=f.read()
    text=df_bytes.decode("utf-8-sig","ignore")
    reader=csv.DictReader(io.StringIO(text))
    rows=list(reader)
    if not rows: return [], [], None, {}

    for req in ["Main Port Name","Latitude","Longitude"]:
        if req not in rows[0]:
            st.error(f"CSV missing '{req}'. Found: {list(rows[0].keys())}")
            return [], [], None, {}

    country_col = None
    for c in rows[0].keys():
        if "country" in c.lower():
            country_col = c; break

    mains=sorted({r["Main Port Name"] for r in rows if r.get("Main Port Name")})

    ports_by_country: Dict[str,List[str]] = {}
    if country_col:
        for r in rows:
            name=r.get("Main Port Name")
            if not name: continue
            c = _norm_country(r.get(country_col))
            ports_by_country.setdefault(c, []).append(name)
        for k in list(ports_by_country.keys()):
            ports_by_country[k]=sorted(set(ports_by_country[k]))

    return rows, mains, country_col, ports_by_country

def get_row_by_main(name: str, rows: List[Dict[str,str]]) -> Optional[Dict[str,str]]:
    for r in rows:
        if r.get("Main Port Name")==name: return r
    return None

def latlon_from_row(r: Dict[str,str]):
    def _to_float_coord(val: str) -> float:
        s = re.sub(r"(\d),(\d)", r"\\1.\\2", (val or "").strip())
        try: return float(s)
        except:
            d=_parse_dms(s)
            if d is None: raise ValueError(f"Unsupported coordinate: '{val}'")
            return d
    return _to_float_coord(r["Latitude"]), _to_float_coord(r["Longitude"])

# ---------- Congestion & alias ----------
@st.cache_data(show_spinner=False)
def load_congestion_advanced(df_bytes):
    from utils import canon_name
    if df_bytes is None:
        return {"by_name":{}, "geo":None, "raw":pd.DataFrame()}
    text = df_bytes.decode("utf-8-sig","ignore")
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        return {"by_name":{}, "geo":None, "raw":pd.DataFrame()}
    df = pd.DataFrame(rows)
    name_col = next((c for c in df.columns if c.lower() in ("port","name","port_name","portname")), None)
    wait_col = next((c for c in df.columns if c.lower() in ("waittime_hr","wait_hr","waithours","wait_hours","wait","delay_hr","delay_hours")), None)
    lat_col  = next((c for c in df.columns if c.lower() in ("lat","latitude","y")), None)
    lon_col  = next((c for c in df.columns if c.lower() in ("lon","longitude","x","long","lng")), None)

    if name_col is None or wait_col is None:
        st.warning("Congestion CSV needs at least a Port/Name column and a WaitTime_hr (or equivalent) column.")
        return {"by_name":{}, "geo":None, "raw":df}

    df["__port_name__"] = df[name_col].astype(str)
    df["__wait__"] = pd.to_numeric(df[wait_col], errors="coerce").fillna(0.0)
    df["__key__"] = df["__port_name__"].map(canon_name)

    by_name = {}
    for _, r in df.iterrows():
        k = r["__key__"]
        if not k: 
            continue
        by_name[k] = float(r["__wait__"])

    geo_df = None
    if lat_col and lon_col:
        def _num(x):
            try: return float(x)
            except: return None
        df["__lat__"] = df[lat_col].map(_num)
        df["__lon__"] = df[lon_col].map(_num)
        geo_df = df.dropna(subset=["__lat__","__lon__"])[["__port_name__","__wait__","__lat__","__lon__"]].copy()

    return {"by_name": by_name, "geo": geo_df, "raw": df}

@st.cache_data(show_spinner=False)
def load_alias_map(df_bytes):
    from utils import canon_name
    if df_bytes is None: 
        return {}
    text = df_bytes.decode("utf-8-sig","ignore")
    reader = csv.DictReader(io.StringIO(text))
    alias = {}
    for row in reader:
        wpi = canon_name(row.get("WPI_Name",""))
        src = canon_name(row.get("Source_Name",""))
        if wpi and src:
            alias[wpi] = src
    return alias
