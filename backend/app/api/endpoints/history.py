from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.db.session import get_db
from app.services.history_service import history_service
from app.schemas.history import AnalysisHistory
from app.api.endpoints.auth import get_current_user

router = APIRouter()

@router.get("/", response_model=List[AnalysisHistory])
def read_history(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    user_id = current_user.id
    return history_service.get_user_history(db, user_id=user_id, skip=skip, limit=limit)

@router.get("/{analysis_id}", response_model=AnalysisHistory)
def read_analysis(
    analysis_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    analysis = history_service.get_analysis(db, analysis_id=analysis_id)
    if not analysis:
        raise HTTPException(status_code=404, detail="Analysis not found")
    if analysis.user_id != current_user.id:
         raise HTTPException(status_code=403, detail="Not authorized to view this analysis")
    return analysis

@router.delete("/{analysis_id}")
def delete_analysis(
    analysis_id: str,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    success = history_service.delete_analysis(db, analysis_id=analysis_id, user_id=current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Analysis not found or not authorized to delete")
    return {"message": "Analysis deleted successfully"}
