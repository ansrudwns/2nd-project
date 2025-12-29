from enum import Enum
from typing import Any, Dict, Optional

class Stage(str, Enum):
    AUTH = "AUTH"
    UPLOAD = "UPLOAD"
    FILE_VALIDATE = "FILE_VALIDATE"
    DOC_TYPE_DETECT = "DOC_TYPE_DETECT"
    OCR = "OCR"
    SCHEMA_NORMALIZE = "SCHEMA_NORMALIZE"
    RULE_ENGINE = "RULE_ENGINE"
    PII_DETECT = "PII_DETECT"
    PII_MASK = "PII_MASK"
    PII_ANSWER_MASK = "PII_ANSWER_MASK"
    PII_MASKING = "PII_MASKING"
    MARKET_API = "MARKET_API"
    MARKET_PRICE = "MARKET_PRICE"
    RAG_SEARCH = "RAG_SEARCH"
    LLM_GENERATE = "LLM_GENERATE"
    RESULT_RENDER = "RESULT_RENDER"
    RESULT_STORE = "RESULT_STORE"
    CLEANUP = "CLEANUP"
    SYSTEM = "SYSTEM"  # Fallback for unexpected errors

class AnalysisException(Exception):
    def __init__(
        self,
        stage: Stage,
        code: str,
        message: str,
        detail: Optional[Dict[str, Any]] = None,
        action: str = "시스템 관리자에게 문의하세요."
    ):
        self.stage = stage
        self.code = code
        self.message = message
        self.detail = detail or {}
        self.action = action
        super().__init__(self.message)

    def to_dict(self):
        return {
            "success": False,
            "error": {
                "stage": self.stage.value,
                "code": self.code,
                "message": self.message,
                "detail": self.detail,
                "action": self.action
            }
        }
