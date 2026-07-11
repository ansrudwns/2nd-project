from typing import List, Dict, Any
from app.schemas.documents import LaborContract
from app.schemas.analysis import RuleResult, RuleEvidence

class LaborRuleEngine:
    """
    Dedicated Rule Engine for Labor Contracts.
    Checks Labor Standards Act compliance.
    """

    @staticmethod
    def run(contract: LaborContract, market_data: Any = None) -> List[RuleResult]:
        results = []
        
        results.append(LaborRuleEngine._check_min_wage(contract))
        results.append(LaborRuleEngine._check_work_hours(contract))
        results.append(LaborRuleEngine._check_contract_period(contract))
        
        return results

    @staticmethod
    def _check_min_wage(contract: LaborContract) -> RuleResult:
        """
        Check if salary meets minimum wage requirements (2025 Standard: 10,030 KRW / Month ~2,096,270 KRW)
        """
        MIN_WAGE_MONTHLY = 2096270 # 2025 Standard for 209 hours
        
        salary = contract.salary

        if not salary or salary <= 100000:
            return RuleResult(
                rule_id="MIN_WAGE",
                status="UNKNOWN",
                severity="MED",
                title="최저임금 판단 불가",
                evidence=RuleEvidence(
                    detail="급여 금액 또는 지급 단위를 충분히 추출하지 못해 최저임금 준수 여부를 판단할 수 없습니다."
                )
            )
        
        # Simple heuristic: If salary is clearly monthly (over 1M) and below min wage
        if 100000 < salary < MIN_WAGE_MONTHLY:
            diff = MIN_WAGE_MONTHLY - salary
            return RuleResult(
                rule_id="MIN_WAGE",
                status="FAIL",
                severity="HIGH",
                title="최저임금 위반 의심",
                evidence=RuleEvidence(
                    detail=f"계약된 급여({salary:,}원)는 2025년 최저임금 월 환산액({MIN_WAGE_MONTHLY:,}원)보다 부족합니다. (차액: {diff:,}원)\n(단, 주 소정근로시간이 40시간 미만인 경우 비례하여 계산해야 합니다.)"
                )
            )
        
        return RuleResult(
            rule_id="MIN_WAGE",
            status="PASS",
            severity="INFO",
            title="최저임금 준수",
            evidence=RuleEvidence(
                detail=f"추출된 월 급여가 2025년 월 환산 참고 기준을 상회합니다. (계약 급여: {salary:,}원)"
            )
        )

    @staticmethod
    def _check_work_hours(contract: LaborContract) -> RuleResult:
        """
        Check specifically for 52-hour work week violations or excessive hours mentions.
        """
        # This requires robust NLP parsing of 'work_hours' string, which is hard.
        # We rely on keyword detection for now.
        hours_str = (contract.work_hours or "").strip()

        if not hours_str or hours_str.lower() in {"unknown", "none", "n/a"}:
            return RuleResult(
                rule_id="WORK_HOURS",
                status="UNKNOWN",
                severity="MED",
                title="근로시간 판단 불가",
                evidence=RuleEvidence(
                    detail="소정근로시간을 충분히 추출하지 못해 법정 근로시간 준수 여부를 판단할 수 없습니다."
                )
            )
        
        if "60시간" in hours_str or "제한 없음" in hours_str:
             return RuleResult(
                rule_id="WORK_HOURS",
                status="FAIL",
                severity="HIGH",
                title="근로시간 제한 위반",
                evidence=RuleEvidence(
                    detail=f"법정 근로시간(주 52시간)을 초과할 수 있는 내용이 있습니다: '{hours_str}'"
                )
            )
            
        return RuleResult(
            rule_id="WORK_HOURS",
            status="PASS",
            severity="INFO",
            title="근로시간 점검",
            evidence=RuleEvidence(
                detail=f"특이사항 없음. (명시된 시간: {hours_str})"
            )
        )

    @staticmethod
    def _check_contract_period(contract: LaborContract) -> RuleResult:
        if not contract.start_date:
             return RuleResult(
                rule_id="PERIOD",
                status="FAIL",
                severity="MEDIUM",
                title="근로개시일 누락",
                evidence=RuleEvidence(
                    detail="근로 계약 시작일이 명시되지 않았습니다."
                )
            )
        return RuleResult(rule_id="PERIOD", status="PASS", severity="INFO", title="근로기간 명시", evidence=RuleEvidence(detail="시작일이 명시됨."))
