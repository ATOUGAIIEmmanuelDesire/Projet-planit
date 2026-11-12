from fastapi import APIRouter, HTTPException
from app.services.resource_service import load_all_resources_from_excel

router = APIRouter()

@router.get("/resources")
def get_campus_resources():
    try:
        data = load_all_resources_from_excel()
        return {
            "success": True,
            "data": data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))