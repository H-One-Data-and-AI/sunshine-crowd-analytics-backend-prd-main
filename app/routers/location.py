from fastapi import APIRouter, Query,Depends
from fastapi.responses import StreamingResponse
from utils.db_utils import query_data, stream_csv_generator, query_geojson
from utils.encrypt_data import encrypt_stream_generator
from typing import List
from auth import get_current_user, User
router = APIRouter(tags=["Location"])

@router.get("/main_adjust/data")
def get_location_data(
    province: List[str] = Query(None, description="Filter by province name"),
    district: List[str] = Query(None, description="Filter by district name"),
    ds: List[str] = Query(None, description="Filter by DS division name"),
    limit: int = Query(100, description="Number of records to return"),
    offset: int = Query(0, description="Number of records to skip"),
    # `all_regions` boolean to bypass filtering if everything is selected
    all_regions: bool = Query(False, description="Bypass all region filters if true"),
    current_user: User = Depends(get_current_user)
):
    return query_data("location", province, district, ds, limit, offset, all_regions)

@router.get("/main_adjust/geojson")
def get_location_geojson(
    province: List[str] = Query(None, description="Filter by province names"),
    district: List[str] = Query(None, description="Filter by district names"),
    ds: List[str] = Query(None, description="Filter by DS names"),
    all_regions: bool = Query(False, description="Bypass all region filters if true"),
    current_user: User = Depends(get_current_user)
):
    return query_geojson("location", province, district, ds, all_regions)

@router.get("/main_adjust/download.csv")
def download_location_csv(
    province: str = Query(None, description="Filter by province name"),
    district: str = Query(None, description="Filter by district name"),
    ds: str = Query(None, description="Filter by DS division name"),
current_user: User = Depends(get_current_user)
):
    csv_generator = stream_csv_generator("location", province, district, ds)
    encrypted_stream_generator = encrypt_stream_generator(csv_generator)
    return StreamingResponse(
        encrypted_stream_generator,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": "attachment; filename=encrypted_location_data.enc"
        }
    )