from pydantic import BaseModel
from datetime import datetime
from typing import Optional, Dict, Any

class AnalysisHistory(BaseModel):
    id: str
    user_id: str
    status: str
    created_at: datetime
    result_json: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True
