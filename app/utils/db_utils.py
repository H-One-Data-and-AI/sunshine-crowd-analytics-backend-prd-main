# app/utils/db_utils.py

import sqlite3
from fastapi.responses import StreamingResponse, JSONResponse
from settings import DB_PATH, DEFAULT_LIMIT, MAX_LIMIT
import csv
import io
import pandas as pd
import json
from typing import List

def _build_where_clause(provinces: List[str] = None, districts: List[str] = None, dss: List[str] = None, all_regions: bool = False):
    if all_regions or (not provinces and not districts and not dss):
        # Default all_regions = False might mean default to Western
        # But if they don't explicitly pass all_regions, we default to Western (legacy behavior)
        if not all_regions and not provinces and not districts and not dss:
            return ' AND "Province" = ?', ['Western']
        return '', []

    params = []
    conditions = []
    
    if provinces:
        placeholders = ", ".join(["?"] * len(provinces))
        conditions.append(f'"Province" IN ({placeholders})')
        params.extend(provinces)
    
    if districts:
        placeholders = ", ".join(["?"] * len(districts))
        conditions.append(f'"District" IN ({placeholders})')
        params.extend(districts)
        
    if dss:
        placeholders = ", ".join(["?"] * len(dss))
        conditions.append(f'"DS" IN ({placeholders})')
        params.extend(dss)
    
    if conditions:
        return f" AND ({' OR '.join(conditions)})", params
    return '', []

def _query_dataframe(table_name, provinces: List[str] = None, districts: List[str] = None, dss: List[str] = None, all_regions: bool = False, limit=None, offset=None):
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    q = f'SELECT * FROM "{table_name}" WHERE 1=1'
    
    where_clause, params = _build_where_clause(provinces, districts, dss, all_regions)
    q += where_clause
    
    if limit is not None:
        q += " LIMIT ? OFFSET ?"
        params.extend([min(limit, MAX_LIMIT), max(offset or 0, 0)])

    # Using pandas read_sql_query for fast dataframe conversion
    df = pd.read_sql_query(q, conn, params=params)
    conn.close()
    
    # Fix: Replace NaN values
    df = df.fillna(0.0)
    return df

def query_data(table_name, province=None, district=None, ds=None, limit=DEFAULT_LIMIT, offset=0, all_regions=False):
    # Ensure params are lists or None
    provinces = province if isinstance(province, list) else ([province] if province else None)
    districts = district if isinstance(district, list) else ([district] if district else None)
    dss = ds if isinstance(ds, list) else ([ds] if ds else None)
    
    df = _query_dataframe(table_name, provinces, districts, dss, all_regions=all_regions, limit=limit, offset=offset)
    if not df.empty:
        df = df.where(pd.notnull(df), None)
        return df.to_dict(orient="records")
    return []

def query_geojson(table_name, provinces: List[str] = None, districts: List[str] = None, dss: List[str] = None, all_regions: bool = False):
    df = _query_dataframe(table_name, provinces, districts, dss, all_regions, limit=None)
    
    if df.empty:
        return {"type": "FeatureCollection", "features": []}
    
    from shapely import wkt
    import geopandas as gpd
    
    if table_name == 'competitor' and 'Competitor' in df.columns:
        # Filter out bad points where Competitor label is accidentally a POINT string
        df = df[~df['Competitor'].astype(str).str.startswith('POINT (')]
        
        # Apply the ATM title fix (like Map.jsx does)
        def fix_competitor(row):
            comp = str(row['Competitor'])
            amenity = str(row.get('Amenity', '')).lower()
            if amenity == 'atm' and 'atm' not in comp.lower():
                return f"{comp} - ATM"
            return comp
        df['Competitor'] = df.apply(fix_competitor, axis=1)
        
    if 'geometry' in df.columns:
        # Drop rows with no geometry
        df = df.dropna(subset=['geometry'])
        # Drop rows where geometry is 0.0 (caused by fillna earlier if geometry was null)
        df = df[df['geometry'] != 0.0]
        
        # Filter unparseable gemetries before applying wkt.loads
        df['geometry'] = df['geometry'].apply(lambda x: wkt.loads(x) if isinstance(x, str) else None)
        df = df.dropna(subset=['geometry'])
        
        gdf = gpd.GeoDataFrame(df, geometry='geometry', crs="EPSG:4326")
        
        # Don't drop na here, we already replaced with 0.0.
        geojson_str = gdf.to_json()
        return JSONResponse(content=json.loads(geojson_str))
        
    return {"type": "FeatureCollection", "features": []}

def get_category_from_row(name, raw_amenity):
    lower_name = str(name).lower()
    lower_amenity = str(raw_amenity).lower()
    
    if 'atm' in lower_name or lower_amenity == 'atm': return 'ATM'
    
    if any(k in lower_name for k in ['ioc', 'ceypetco', 'sinopec', 'shed', 'filling station', 'fuel', 'gas station']) or \
       any(k in lower_amenity for k in ['fuel', 'gas']):
        return 'Gas Station'
        
    if any(k in lower_name for k in ['bank', 'hnb', 'sampath', 'seylan', 'ntb', 'nations', 'boc', 'peoples', 'nsb']) or lower_amenity == 'bank':
        return 'Bank'
        
    if any(k in lower_name for k in ['keells', 'arpico', 'spar', 'glomark', 'food city', 'sathosa', 'laugfs', 'softlogic', 'supermarket']):
        return 'Supermarket'
        
    if any(k in lower_name for k in ['pharmacy', 'chemist', 'healthguard']) or 'pharmacy' in lower_amenity:
        return 'Pharmacie'
        
    return raw_amenity.capitalize() if raw_amenity else 'Other'

def get_competitor_summary(provinces: List[str] = None, districts: List[str] = None, dss: List[str] = None, all_regions: bool = False):
    df = _query_dataframe('competitor', provinces, districts, dss, all_regions, limit=None)
    
    if df.empty or 'Competitor' not in df.columns or 'Amenity' not in df.columns:
        return {"categories": [], "grouped": {}}
        
    df = df[~df['Competitor'].astype(str).str.startswith('POINT (')]
    
    categories = {}
    grouped = {}
    
    for _, row in df.iterrows():
        comp = str(row['Competitor']).replace('\r', '').replace('"', '').strip()
        raw_amenity = str(row['Amenity']).replace('\r', '').replace('"', '').strip()
        
        if not comp: continue
        
        if raw_amenity.lower() == 'atm' and 'atm' not in comp.lower():
            comp = f"{comp} - ATM"
            
        categories[comp] = categories.get(comp, 0) + 1
        
        master_category = get_category_from_row(comp, raw_amenity)
        if master_category not in grouped:
            grouped[master_category] = {}
        grouped[master_category][comp] = grouped[master_category].get(comp, 0) + 1
        
    category_list = [f"{k}({v})" for k, v in categories.items()]
    category_list.sort(key=lambda x: x.split('(')[0].lower())
    
    return {"categories": category_list, "grouped": grouped}


def stream_csv_generator(table_name, province=None, district=None, ds=None):
    # This remains unchanged for backwards compatibility
    def generate():
        conn = None  
        try:
            conn = sqlite3.connect(DB_PATH, check_same_thread=False)
            cur = conn.cursor()

            q = f'SELECT * FROM "{table_name}" WHERE 1=1'
            params = []

            if not province and not district and not ds:
                effective_province = 'Western'
            else:
                effective_province = province

            if effective_province:
                q += ' AND "Province" = ?'
                params.append(effective_province)
            if district:
                q += ' AND "District" = ?'
                params.append(district)
            if ds:
                q += ' AND "DS" = ?'
                params.append(ds)

            cur.execute(q, params)
            cols = [d[0] for d in cur.description]
            buf = io.StringIO()
            writer = csv.writer(buf)

            writer.writerow(cols)
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate(0)

            for row in cur:
                cleaned_row = [None if v is None or pd.isna(v) else v for v in row]
                writer.writerow(cleaned_row)
                yield buf.getvalue()
                buf.seek(0)
                buf.truncate(0)
        finally:
            if conn:
                conn.close()

    return generate()

def stream_csv(table_name, province=None, district=None, ds=None):
    csv_generator = stream_csv_generator(table_name, province, district, ds)
    return StreamingResponse(csv_generator, media_type="text/csv", headers={
        "Content-Disposition": f"attachment; filename={table_name}.csv"
    })