from fastapi import APIRouter, Query, UploadFile, File, HTTPException,Depends
from fastapi.responses import StreamingResponse, JSONResponse
from utils.db_utils import query_data, stream_csv_generator
from utils.encrypt_data import encrypt_stream_generator
from typing import List
from pydantic import BaseModel
import pandas as pd
import geopandas as gpd
from shapely import wkt
import sqlite3
from settings import DB_PATH
import io
from typing import List
from auth import get_current_user, User

class DeleteLocationsRequest(BaseModel):
    geometries: List[str]
router = APIRouter(tags=["Cargills"])

@router.get("/cargills/data")
def get_cargills_data(
    province: List[str] = Query(None),
    district: List[str] = Query(None),
    ds: List[str] = Query(None),
    limit: int = Query(None),
    offset: int = Query(None),
    all_regions: bool = Query(False),
    current_user: User = Depends(get_current_user)
):
    return query_data("cargills", province, district, ds, limit, offset)

@router.get("/cargills/download.csv")
def download_cargills_csv(
    province: str = Query(None),
    district: str = Query(None),
    ds: str = Query(None),
    current_user: User = Depends(get_current_user)
):
    csv_generator= stream_csv_generator("cargills", province, district, ds)
    encrypted_stream_generator = encrypt_stream_generator(csv_generator)
    return StreamingResponse(
        encrypted_stream_generator,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": "attachment; filename=encrypted_competitor_data.enc"
        }
    )

@router.post("/cargills/upload")
async def upload_cargills_data(file: UploadFile = File(...),current_user: User = Depends(get_current_user)):
    """
    Uploads a CSV file with new client locations, processes the data,
    and inserts it into the 'cargills' table in the database.
    The CSV file should have the columns: Name, Amenity, geometry.
    """
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="Invalid file type. Please upload a CSV file.")

    try:
        # Read the uploaded CSV file into a pandas DataFrame
        contents = await file.read()
        new_df = pd.read_csv(io.StringIO(contents.decode('utf-8')))

        # Convert the geometry string to shapely Point objects and create a GeoDataFrame
        new_df['geometry'] = new_df['geometry'].apply(wkt.loads)
        combank_gdf = gpd.GeoDataFrame(new_df, geometry='geometry', crs="EPSG:4326")

        # Connect to the SQLite database
        conn = sqlite3.connect(DB_PATH)

        # Load the main_df_adjusted table into a GeoDataFrame
        hex_df = pd.read_sql_query("SELECT * FROM main_df_adjusted", conn)
        hex_df['geometry'] = hex_df['geometry'].apply(wkt.loads)
        hex_gdf = gpd.GeoDataFrame(hex_df, geometry='geometry', crs="EPSG:4326")

        # Perform a spatial join to find which hexagon each new point falls into
        joined_gdf = gpd.sjoin(combank_gdf, hex_gdf, how='left', predicate='within')

        # Prepare the final DataFrame for insertion
        result_df = joined_gdf[[
            'hex_id', 'Province', 'District', 'DS',
            'Name', 'Amenity', 'geometry'
        ]].copy()
        # result_df['Competitor'] = 'Commercial Bank'
        result_df['User'] = 'New'
        result_df['geometry'] = result_df['geometry'].apply(lambda geom: wkt.dumps(geom) if geom else None)


        # Append the new data to the 'cargills' table
        result_df.to_sql('cargills', conn, if_exists='append', index=False)

        conn.close()

        return JSONResponse(status_code=200, content={"message": f"Successfully added {len(result_df)} new locations."})

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"An error occurred: {e}")


@router.get("/cargills/new-locations")
def get_new_locations(current_user: User = Depends(get_current_user)):
    """
    Retrieves all records from the 'cargills' table where the 'User' column is 'New'.
    """
    conn = None
    try:
        # Connect to the SQLite database
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row  # This allows accessing columns by name
        cursor = conn.cursor()

        # Execute the query to find all new locations
        cursor.execute("SELECT * FROM cargills WHERE User = 'New'")
        rows = cursor.fetchall()

        # Convert the list of Row objects to a list of dictionaries
        new_locations = [dict(row) for row in rows]

        return new_locations

    except Exception as e:
        # In a real app, you'd want better error logging
        print(f"Database error: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve new locations from the database.")
    finally:
        if conn:
            conn.close()


# Add this endpoint in cargills.py
@router.delete("/cargills/delete-locations")
async def delete_locations(request: DeleteLocationsRequest,current_user: User = Depends(get_current_user)):
    """
    Deletes records from the 'cargills' table based on a list of geometry strings.
    """
    if not request.geometries:
        raise HTTPException(status_code=400, detail="No locations provided for deletion.")

    conn = None
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Use parameter substitution to prevent SQL injection.
        # Create a string of placeholders like '?, ?, ?'
        placeholders = ', '.join(['?'] * len(request.geometries))

        # The User = 'New' clause is an extra safeguard to ensure only user-added data can be deleted via this endpoint.
        query = f"DELETE FROM cargills WHERE geometry IN ({placeholders}) AND User = 'New'"

        cursor.execute(query, request.geometries)
        deleted_count = cursor.rowcount  # Get the number of rows deleted
        conn.commit()

        if deleted_count == 0:
            return {"message": "No matching locations found to delete."}

        return {"message": f"{deleted_count} location(s) deleted successfully."}

    except sqlite3.Error as e:
        if conn:
            conn.rollback()  # Roll back changes if an error occurs
        print(f"Database error during deletion: {e}")
        raise HTTPException(status_code=500, detail="A database error occurred during deletion.")
    finally:
        if conn:
            conn.close()