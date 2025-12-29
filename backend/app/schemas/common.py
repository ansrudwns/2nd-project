from pydantic import BaseModel
from typing import Optional, Dict, Any, Generic, TypeVar
from app.core.exceptions import Stage

T = TypeVar("T")

class ErrorDetail(BaseModel):
    stage: Stage
    code: str
    message: str
    detail: Dict[str, Any]
    action: str

class BaseResponse(BaseModel, Generic[T]):
    success: bool
    data: Optional[T] = None
    error: Optional[ErrorDetail] = None

# Helper to create error response
def create_error_response(stage: Stage, code: str, message: str, detail: Dict = {}, action: str = "") -> BaseResponse:
    return BaseResponse(
        success=False,
        error=ErrorDetail(
            stage=stage,
            code=code,
            message=message,
            detail=detail,
            action=action
        )
    )
