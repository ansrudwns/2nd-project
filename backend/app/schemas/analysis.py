from pydantic import BaseModel
from typing import List, Dict, Optional, Any
from app.schemas.documents import DocumentData
from app.core.exceptions import Stage

class RuleEvidence(BaseModel):
    contract_value: Optional[str] = None
    registry_value: Optional[str] = None
    detail: str = ""

class AIAdvice(BaseModel):
    legal_review: Optional[str] = None
    action_guide: Optional[str] = None

class RuleResult(BaseModel):
    rule_id: str
    status: str # PASS, FAIL, UNKNOWN
    severity: str # LOW, MED, HIGH
    title: str
    evidence: RuleEvidence
    ai_advice: Optional[AIAdvice] = None

class AnalysisSummary(BaseModel):
    risk_count: int
    highest_severity: str
    language: str = "ko"

class AnalysisResultResponse(BaseModel):
    analysis_id: str
    summary: AnalysisSummary
    rules: List[RuleResult]
    documents: Dict[str, str] # URLs
    summary_text: Optional[str] = None
