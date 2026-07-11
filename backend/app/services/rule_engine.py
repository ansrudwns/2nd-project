from app.schemas.documents import Contract, Registry
from app.schemas.analysis import RuleResult, RuleEvidence
from app.utils.parsers import AddressParser
from typing import List
from datetime import datetime, timedelta

class RuleEngine:
    @staticmethod
    def run(contract: Contract, registry: Registry, market_price_data: any = None) -> List[RuleResult]:
        results = []
        
        # 1. Address Match (주소 일치)
        results.append(RuleEngine._check_address(contract, registry))
        
        # 2. Owner Match (소유자 일치)
        results.append(RuleEngine._check_owner(contract, registry))
        
        # 3. Prior Rights (선행 근저당/전세권/임차권)
        results.append(RuleEngine._check_prior_rights(registry))

        # 4. Issue Date (등기부 발행일자)
        results.append(RuleEngine._check_issue_date(registry))
        
        # 5. Building Usage (건축물 용도)
        results.append(RuleEngine._check_building_usage(contract, registry))
        
        # 6. Market Price Risk (시세 비교)
        if market_price_data:
            results.append(RuleEngine._check_market_price_risk(contract, market_price_data))
        
        return results

    # ... existing methods ...

    @staticmethod
    def _check_market_price_risk(contract: Contract, market_data: any) -> RuleResult:
        try:
            # Parse Contract Deposit
            contract_deposit = contract.deposit_amount 
            
            # Extract Price String & Source
            market_price_str = ""
            source_str = ""
            
            if isinstance(market_data, dict):
                market_price_str = market_data.get('price', '')
                source_str = market_data.get('source', '')
            else:
                market_price_str = str(market_data)
                
            # Simple Heuristic Parser for Market Price String
            digits = "".join(filter(str.isdigit, market_price_str))
            if not digits:
                 return RuleResult(rule_id="PRICE", status="UNKNOWN", severity="LOW", title="전세가율 진단", evidence=RuleEvidence(detail=f"시세 데이터 파싱 실패: {market_price_str}"))

            # Simple logic: assume standard format (e.g. 2억 4,500만원 -> 24500 -> 245000000)
            # Or simplified: just take digits if it looks like full number? 
            # Given previous implementation was simplistic, we improve slightly.
            # If 24500 -> it means 2.45 billion? No. 
            # If 24500 -> 2억4500만원 usually means 245,000,000.
            # Logic: If digits < 100000 -> multiply by 10000.
            
            market_val = int(digits)
            if market_val < 1000000: # heuristic for 'man-won' unit missing in digits
                market_val = market_val * 10000
                
            if market_val == 0:
                 return RuleResult(rule_id="PRICE", status="UNKNOWN", severity="LOW", title="전세가율 진단", evidence=RuleEvidence(detail="시세 데이터 파싱 불가"))

            # Risk Logic
            ratio = (contract_deposit / market_val) * 100
            
            # Format numbers for readability (e.g. 2,4500 -> 2억 4,500만원 style or just commas)
            # For simplicity using commas first, user can request 'Korean style' formatting if needed.
            # actually user asked for "2억 4,500만원" style if possible, but let's use the input string 'market_price_str' which is already formatted!
            
            # Re-construct formatted strings
            region_msg = f"{market_data.get('region', '해당 지역')}의 실거래가는 {market_price_str}였습니다."
            deposit_msg = f"현재 계약서 상 보증금은 {contract_deposit:,}원입니다."
            source_suffix = f"\n(출처: {source_str})" if source_str else ""
            
            if ratio > 80:
                conclusion = f"그러므로 전세가율이 {ratio:.1f}%에 달해 깡통전세 위험이 매우 높습니다."
                return RuleResult(rule_id="PRICE", status="FAIL", severity="HIGH", title="전세가율 진단 (매우 위험)", evidence=RuleEvidence(detail=f"{region_msg} {deposit_msg} {conclusion}{source_suffix} Deposit[{contract_deposit}]"))
            elif ratio > 70:
                conclusion = f"그러므로 전세가율이 {ratio:.1f}%로 다소 높아 주의가 필요합니다."
                return RuleResult(rule_id="PRICE", status="FAIL", severity="MED", title="전세가율 진단 (주의)", evidence=RuleEvidence(detail=f"{region_msg} {deposit_msg} {conclusion}{source_suffix} Deposit[{contract_deposit}]"))
            elif ratio < 55:
                conclusion = f"그러므로 보증금이 시세 대비 {ratio:.1f}%로 지나치게 낮아 확인이 필요합니다."
                return RuleResult(rule_id="PRICE", status="FAIL", severity="MED", title="전세가율 진단 (확인 필요)", evidence=RuleEvidence(detail=f"{region_msg} {deposit_msg} {conclusion}{source_suffix} Deposit[{contract_deposit}]"))
            else:
                conclusion = f"그러므로 전세가율이 {ratio:.1f}%로 안전한 범위(55~70%) 내에 있습니다."
                return RuleResult(rule_id="PRICE", status="PASS", severity="LOW", title="전세가율 진단 (안전)", evidence=RuleEvidence(detail=f"{region_msg} {deposit_msg} {conclusion}{source_suffix}"))

        except Exception as e:
            return RuleResult(rule_id="PRICE", status="UNKNOWN", severity="LOW", title="전세가율 진단", evidence=RuleEvidence(detail=f"비교 중 오류: {str(e)}"))

    @staticmethod
    def _check_address(contract: Contract, registry: Registry) -> RuleResult:
        try:
            # Normalize strings roughly
            c_addr = str(contract.address).replace(" ", "")
            r_addr = str(registry.property_address).replace(" ", "")
            
            if not c_addr or not r_addr:
                 return RuleResult(rule_id="ADDR", status="FAIL", severity="HIGH", title="주소 일치 확인", evidence=RuleEvidence(detail="주소 정보를 추출할 수 없습니다."))

            # Simple contains check for MVP
            if c_addr in r_addr or r_addr in c_addr:
                 return RuleResult(rule_id="ADDR", status="PASS", severity="LOW", title="주소 일치 확인", evidence=RuleEvidence(detail="주소가 일치합니다."))
            else:
                 # Truncate registry address for brevity
                 short_r_addr = registry.property_address[:50] + "..." if len(registry.property_address) > 50 else registry.property_address
                 return RuleResult(rule_id="ADDR", status="FAIL", severity="HIGH", title="주소 일치 확인", evidence=RuleEvidence(detail=f"Contract[{contract.address}] / Registry[{registry.property_address}] 주소 불일치"))
        except:
             return RuleResult(rule_id="ADDR", status="UNKNOWN", severity="MED", title="주소 일치 확인", evidence=RuleEvidence(detail="주소 비교 불가"))

    @staticmethod
    def _check_owner(contract: Contract, registry: Registry) -> RuleResult:
        c_owner = str(contract.lessor_name).replace(" ", "")
        r_owner = str(registry.owner_name).replace(" ", "")
        
        if not c_owner or not r_owner:
            return RuleResult(rule_id="OWNER", status="FAIL", severity="HIGH", title="소유자 일치 확인", evidence=RuleEvidence(detail="소유자/임대인 정보를 추출할 수 없습니다."))
        
        if c_owner == r_owner:
            return RuleResult(rule_id="OWNER", status="PASS", severity="LOW", title="소유자 일치 확인", evidence=RuleEvidence(detail="임대인과 소유자가 일치합니다."))
        return RuleResult(rule_id="OWNER", status="FAIL", severity="HIGH", title="소유자 일치 확인", evidence=RuleEvidence(detail=f"Contract[{contract.lessor_name}] / Registry[{registry.owner_name}] 명의 불일치"))

    @staticmethod
    def _check_prior_rights(registry: Registry) -> RuleResult:
        # Check for keywords in rights list (Mock logic assumed, real schema needs 'rights' list)
        # Assuming registry has a list of strings called 'rights' or similar.
        # For this MVP, we parse from a mock field or assume clean registry object has it.
        # Let's assume Registry schema has 'rights: List[str]'
        
        dangerous_rights = ["근저당권", "전세권", "임차권등기", "가압류", "가처분"]
        found_risks = []
        
        # Mocking access to rights if not in schema yet, will default to []
        rights = getattr(registry, "rights", None)

        if not rights:
            return RuleResult(
                rule_id="RIGHTS",
                status="UNKNOWN",
                severity="MED",
                title="선순위 권리 판단 불가",
                evidence=RuleEvidence(detail="을구 권리 정보를 추출하지 못했거나 권리 없음 상태를 확인할 근거가 부족합니다.")
            )
        
        for r in rights:
            right_type = getattr(r, "type", str(r))
            for danger in dangerous_rights:
                if danger in right_type:
                    found_risks.append(right_type)
        
        if found_risks:
            return RuleResult(
                rule_id="RIGHTS", 
                status="FAIL", 
                severity="HIGH", 
                title="선순위 권리 확인", 
                evidence=RuleEvidence(detail=f"위험 등기 존재: {', '.join(found_risks)}")
            )
        return RuleResult(rule_id="RIGHTS", status="PASS", severity="LOW", title="선순위 권리 확인", evidence=RuleEvidence(detail="선순위 제한물권이 발견되지 않았습니다."))

    @staticmethod
    def _check_issue_date(registry: Registry) -> RuleResult:
        # Check if issuance date is within 1 week? Mock logic.
        # Assuming registry.issue_date is datetime or string YYYY-MM-DD
        try:
             # Mock date check. Real world would parse date.
             # If no date, WARNING.
             raw_issue_date = str(registry.issue_date or "").strip()
             if not raw_issue_date:
                 return RuleResult(rule_id="DATE", status="UNKNOWN", severity="MED", title="등기부 발행일자", evidence=RuleEvidence(detail="발행일자를 확인할 수 없습니다."))

             normalized = raw_issue_date.replace("년", "-").replace("월", "-").replace("일", "").replace(".", "-").replace("/", "-")
             issue_date = datetime.strptime(normalized[:10], "%Y-%m-%d").date()
             age_days = (datetime.now().date() - issue_date).days
             if age_days < 0:
                 return RuleResult(rule_id="DATE", status="UNKNOWN", severity="MED", title="등기부 발행일자", evidence=RuleEvidence(detail="발행일자가 현재보다 미래로 인식되어 확인이 필요합니다."))
             if age_days > 7:
                 return RuleResult(rule_id="DATE", status="FAIL", severity="MED", title="등기부 발행일자", evidence=RuleEvidence(detail=f"발행 후 {age_days}일이 지나 최신 등기사항 재확인이 필요합니다."))
             return RuleResult(rule_id="DATE", status="PASS", severity="LOW", title="등기부 발행일자", evidence=RuleEvidence(detail=f"발행 후 {age_days}일 이내의 등기부입니다."))
        except (TypeError, ValueError):
             return RuleResult(rule_id="DATE", status="UNKNOWN", severity="MED", title="등기부 발행일자", evidence=RuleEvidence(detail="발행일자 형식을 해석할 수 없습니다."))

    @staticmethod
    def _check_building_usage(contract: Contract, registry: Registry) -> RuleResult:
        illegal = ["근린생활시설", "업무시설", "위반건축물"]
        found = []
        # Check usage in registry
        usage = getattr(registry, "building_usage", "") # Assuming field exists

        if not usage:
            return RuleResult(rule_id="USAGE", status="UNKNOWN", severity="MED", title="건축물 용도 판단 불가", evidence=RuleEvidence(detail="건축물 용도 정보를 추출하지 못했습니다."))
        
        for bad in illegal:
            if bad in usage:
                found.append(bad)
                
        if found:
            return RuleResult(rule_id="USAGE", status="FAIL", severity="HIGH", title="건축물 용도 확인", evidence=RuleEvidence(detail=f"주거용이 아닐 수 있음: {', '.join(found)}"))
            
        return RuleResult(rule_id="USAGE", status="PASS", severity="LOW", title="건축물 용도 확인", evidence=RuleEvidence(detail="위반 건축물 표기가 없습니다."))
