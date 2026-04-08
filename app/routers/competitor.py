from fastapi import APIRouter, Query, Depends
from fastapi.responses import StreamingResponse
from utils.db_utils import query_data, stream_csv_generator, query_geojson, get_competitor_summary
from utils.encrypt_data import encrypt_stream_generator
from typing import List
from auth import get_current_user, User
router = APIRouter(tags=["Competitor"])

@router.get("/competitor/data")
def get_competitor_data(
    province: List[str] = Query(None),
    district: List[str] = Query(None),
    ds: List[str] = Query(None),
    limit: int = Query(None),
    offset: int = Query(None),
    all_regions: bool = Query(False),
    current_user: User = Depends(get_current_user)
):
    return query_data("competitor", province, district, ds, limit, offset)

@router.get("/competitor/geojson")
def get_competitor_geojson_data(
    province: List[str] = Query(None),
    district: List[str] = Query(None),
    ds: List[str] = Query(None),
    all_regions: bool = Query(False),
    current_user: User = Depends(get_current_user)
):
    return query_geojson("competitor", province, district, ds, all_regions)

@router.get("/competitor/summary")
def get_competitor_stats(
    province: List[str] = Query(None),
    district: List[str] = Query(None),
    ds: List[str] = Query(None),
    all_regions: bool = Query(False),
    current_user: User = Depends(get_current_user)
):
    return get_competitor_summary(province, district, ds, all_regions)

@router.get("/competitor/download.csv")
def download_competitor_csv(
    province: str = Query(None),
    district: str = Query(None),
    ds: str = Query(None),
current_user: User = Depends(get_current_user)
):

    csv_generator = stream_csv_generator("competitor", province, district, ds)
    encrypted_stream_generator = encrypt_stream_generator(csv_generator)
    return StreamingResponse(
        encrypted_stream_generator,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": "attachment; filename=encrypted_competitor_data.enc"
        }
    )
