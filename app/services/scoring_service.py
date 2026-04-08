import sqlite3
from typing import Dict, List

import numpy as np
import pandas as pd
import geopandas as gpd
from shapely import wkt

from settings import DB_PATH


# -----------------------------
# Helpers: DB <-> (Geo)DataFrame
# -----------------------------
def _read_table_as_gdf(conn: sqlite3.Connection, table: str, crs: str = "EPSG:4326") -> gpd.GeoDataFrame:
    """Read a SQLite table to a GeoDataFrame, parsing WKT in 'geometry'."""
    df = pd.read_sql_query(f'SELECT * FROM "{table}"', conn)
    if "geometry" not in df.columns:
        raise ValueError(f'Table "{table}" has no "geometry" column.')
    # Parse WKT (guard nulls)
    df["geometry"] = df["geometry"].apply(lambda s: wkt.loads(s) if pd.notnull(s) else None)
    gdf = gpd.GeoDataFrame(df, geometry="geometry", crs=crs)
    return gdf


def _write_location(conn: sqlite3.Connection, gdf: gpd.GeoDataFrame) -> int:
    """
    Replace the 'location' table with gdf content (geometry as WKT).
    IMPORTANT: purge pd.NA to None before to_sql.
    """
    out = gdf.copy()

    # Geometry to WKT
    out["geometry"] = out["geometry"].apply(lambda geom: geom.wkt if geom is not None else None)

    # 🔒 Eliminate pd.NA everywhere (this prevents float(pd.NA) crashes)
    out = out.where(pd.notnull(out), None)

    cur = conn.cursor()
    cur.execute('DROP TABLE IF EXISTS "location";')
    conn.commit()

    out.to_sql("location", conn, if_exists="replace", index=False)

    # Recreate common indexes
    for col in ("Province", "District", "DS", "hex_id"):
        if col in out.columns:
            cur.execute(f'CREATE INDEX IF NOT EXISTS idx_location_{col} ON "location"("{col}");')
    conn.commit()
    return len(out)


# -----------------------------
# Original Python scoring logic (hardened)
# -----------------------------
def get_radius(df: gpd.GeoDataFrame, km: float) -> gpd.GeoDataFrame:
    # guard empty geoms
    if df["geometry"].isna().any():
        # replace missing geoms with empty polygons if any (rare)
        df = df[~df["geometry"].isna()].copy()

    temp = df[["geometry"]].copy().to_crs("EPSG:3857")
    temp["geometry"] = [g.buffer(float(km) * 1000.0) for g in temp["geometry"]]
    temp = temp.to_crs("EPSG:4326")
    df["radius"] = temp["geometry"]
    return df


def get_market_share(df: gpd.GeoDataFrame,
                     branches: gpd.GeoDataFrame,
                     competitors: gpd.GeoDataFrame,
                     radius_km: float) -> gpd.GeoDataFrame:
    # 1) buffer around each hex
    radius_df = get_radius(df[["hex_id", "geometry"]].copy(), radius_km)
    radius_df = gpd.GeoDataFrame(radius_df[["hex_id", "radius"]], geometry="radius", crs="EPSG:4326")

    # 2) sjoin: buffers vs branches
    branches = branches.set_geometry("geometry").to_crs("EPSG:4326")
    rj = gpd.sjoin(left_df=radius_df, right_df=branches[["Name", "geometry"]], how="left", predicate="intersects")

    # Count branches per hex_id/radius
    rj = rj.groupby(["hex_id", "radius"], as_index=False).agg({"Name": "count"})
    rj = gpd.GeoDataFrame(rj, geometry="radius", crs="EPSG:4326")

    # 3) sjoin: previous vs competitors
    competitors = competitors.set_geometry("geometry").to_crs("EPSG:4326")
    rj2 = gpd.sjoin(left_df=rj, right_df=competitors[["Competitor", "geometry"]], how="left", predicate="intersects")
    if "index_right" in rj2.columns:
        del rj2["index_right"]

    # 4) Aggregate counts; avoid NA by filling zeros before math
    agg = rj2.groupby(["hex_id", "radius"], as_index=False).agg(
        Name=("Name", "first"),               # Name already counts from previous step
        Competitor=("Competitor", "count")    # count of competitor matches
    )

    agg["Name"] = pd.to_numeric(agg["Name"], errors="coerce").fillna(0).astype(int)
    agg["Competitor"] = pd.to_numeric(agg["Competitor"], errors="coerce").fillna(0).astype(int)

    denom = agg["Name"] + agg["Competitor"]
    # 🚫 No pd.NA here; use np.where to avoid 0-division
    agg["Area_Presence"] = np.where(denom > 0, agg["Name"] / denom, 0.0)
    agg["Area_Presence"] = agg["Area_Presence"].astype(float).round(2)

    agg = agg.set_index("hex_id")

    # 5) Map back
    for c in ["Name", "Competitor", "Area_Presence"]:
        df[c] = df["hex_id"].map(agg[c])

    # Final cleanup on derived cols
    df["Name"] = pd.to_numeric(df["Name"], errors="coerce").fillna(0).astype(int)
    df["Competitor"] = pd.to_numeric(df["Competitor"], errors="coerce").fillna(0).astype(int)
    df["Area_Presence"] = pd.to_numeric(df["Area_Presence"], errors="coerce").fillna(0.0).astype(float)

    return df


def get_scores(df: pd.DataFrame, weights: Dict[str, float],
               boundaries: List[str] = ["Country", "Province", "District", "DS"]) -> pd.DataFrame:
    df = df.copy()
    df["Country"] = "SL"
    cols = [k for k, v in weights.items() if v and k in df.columns]

    for area in boundaries:
        norm_df = df.copy()
        for c in cols:
            # Ensure numeric, replace NA with 0 for math
            norm_df[c] = pd.to_numeric(norm_df[c], errors="coerce").fillna(0.0)
            # Normalize within boundary
            grp = norm_df.groupby(area)[c]
            max_per_grp = grp.transform("max")
            # Avoid division by zero
            normed = np.where(max_per_grp != 0, norm_df[c] / max_per_grp, 0.0)
            norm_df[c] = weights[c] * normed

        # Weighted sum
        norm_df["score"] = norm_df[cols].sum(axis=1) if cols else 0.0
        # Normalize score within boundary
        grp_score = norm_df.groupby(area)["score"]
        max_score = grp_score.transform("max")
        df[f"{area}_Score"] = np.where(max_score != 0, norm_df["score"] / max_score, 0.0)

        # Dense rank (desc)
        df[f"{area}_Rank"] = grp_score.rank(method="dense", ascending=False)

    ordered = [c for c in df.columns if c not in ("geometry", "Country")] + ["geometry"]
    return df[ordered]


# -----------------------------
# Public API
# -----------------------------
def recalculate_scores_python(weights: Dict[str, float], radius_km: float = 2.0) -> int:
    """
    Load base tables from SQLite, run market share + score (Python/GeoPandas),
    and write results back into 'location' table. Returns number of rows written.
    """
    conn = sqlite3.connect(DB_PATH)

    # Load full tables then restrict to Western Province for performance
    base_full = _read_table_as_gdf(conn, "main_df_adjusted")
    base = base_full[base_full["Province"] == "Western"].copy()

    branches_full = _read_table_as_gdf(conn, "cargills")
    branches = branches_full[branches_full["Province"] == "Western"].copy()

    competitors_full = _read_table_as_gdf(conn, "competitors_data")
    competitors = competitors_full[competitors_full["Province"] == "Western"].copy()

    df = get_market_share(base.copy(), branches, competitors, radius_km)
    df = get_scores(df, weights)
    df.to_csv('output.csv', index=False)

    n = _write_location(conn, df)
    conn.close()
    return n
