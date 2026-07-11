from pydantic import BaseModel, Field
from typing import List, Optional

# --- Shared ---
class BBox(BaseModel):
    page: int
    polygon: List[float] # [x1, y1, x2, y2, ...] 

# --- Contract ---
class Contract(BaseModel):
    address: str = Field(..., description="임차 주택의 소재지")
    lessor_name: str = Field(..., description="임대인 성명")
    lessee_name: str = Field(..., description="임차인 성명")
    deposit_amount: int = Field(..., description="보증금 액수 (정수)")
    rent_amount: int = Field(0, description="월차임 (없으면 0)")
    term_start: str = Field(..., description="임대차 기간 시작일 YYYY-MM-DD")
    term_end: str = Field(..., description="임대차 기간 종료일 YYYY-MM-DD")
    special_terms: List[str] = Field(default_factory=list, description="특약 사항 리스트")

# --- Registry ---
class RegistryRight(BaseModel):
    type: str = Field(..., description="권리 유형 (소유권/근저당/전세권/압류 등)")
    rank: int = Field(..., description="순위 번호")
    amount: int = Field(0, description="채권최고액 등 금액")
    holder_name: str = Field(..., description="권리자 이름")
    date: str = Field(..., description="접수 일자")

class Registry(BaseModel):
    property_address: str = Field(..., description="표제부 소재지")
    owner_name: str = Field(..., description="갑구 최종 소유자")
    issue_date: str = Field(..., description="등기사항증명서 발급일")
    building_usage: str = Field("", description="건축물 용도 또는 위반건축물 표기")
    rights: List[RegistryRight] = Field(default_factory=list, description="을구 권리 관계")

# --- Analysis Result Wrapper ---
class DocumentData(BaseModel):
    contract: Optional[Contract] = None
    registry: Optional[Registry] = None
    raw_text: str = ""

# --- Labor Contract ---
class LaborContract(BaseModel):
    employer_name: str = Field(..., description="사업주(고용조) 성명/상호")
    employee_name: str = Field(..., description="근로자 성명")
    start_date: str = Field(..., description="근로개시일")
    end_date: Optional[str] = Field(None, description="근로종료일 (기간제인 경우)")
    salary: int = Field(0, description="급여 (월급/연봉 등) 금액")
    work_hours: str = Field("", description="소정근로시간/근무시간")
    work_days: str = Field("", description="근무일/휴일")
    job_type: str = Field("", description="업무 내용")
    special_terms: List[str] = Field(default_factory=list, description="근로계약 특약사항")
