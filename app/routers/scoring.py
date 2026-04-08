# from fastapi import APIRouter, Body, HTTPException
# from services.scoring_service import recalculate_scores

# router = APIRouter(tags=["Scoring"])

# @router.post("/main_adjust/recalculate")
# def recalc_location_scores(weights: dict = Body(..., example={
#     "Population": 3,
#     "Latch": 2,
#     "Bank": 1,
#     "Pharmacy": 1,
#     "Fuel_Station": 1,
#     "School": 1,
#     "Supermarket": 1,
#     "Bank_User_5": 2,
#     "Eat_Out_5": 2,
#     "Tourists": 2
# })):
#     try:
#         inserted = recalculate_scores(weights)
#         return {"status": "ok", "rows": inserted}
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


from fastapi import APIRouter, Body, HTTPException, Query, Depends
from services.scoring_service import recalculate_scores_python
from auth import get_current_user, User
router = APIRouter(tags=["Scoring"])

@router.post("/main_adjust/recalculate")
def recalc_location_scores(
    weights: dict = Body(..., example={
        "Population": 3,
        "Latch": 2,
        "Bank": 1,
        "Pharmacy": 1,
        "Fuel_Station": 1,
        "School": 1,
        "Supermarket": 1,
        "Bank_User_5": 2,
        "Eat_Out_5": 2,
        "Tourists": 2
    }),
    radius_km: float = Query(2.0, ge=0.0, description="Buffer radius in kilometers for market share"),
current_user: User = Depends(get_current_user)
):
    print(weights)
    try:
        rows = recalculate_scores_python(weights, radius_km=radius_km)
        return {"status": "ok", "rows": rows, "radius_km": radius_km}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
