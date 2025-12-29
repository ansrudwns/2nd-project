import logging
from typing import List, Any, Dict
from app.core.config import settings
from app.core.exceptions import AnalysisException, Stage

try:
    from openai import AzureOpenAI
except ImportError:
    AzureOpenAI = None

logger = logging.getLogger(__name__)

class LLMService:
    def __init__(self):
        self.client = None
        if settings.AZURE_OPENAI_API_KEY and settings.AZURE_OPENAI_ENDPOINT and AzureOpenAI:
            self.client = AzureOpenAI(
                api_key=settings.AZURE_OPENAI_API_KEY,
                api_version=settings.AZURE_OPENAI_API_VERSION,
                azure_endpoint=settings.AZURE_OPENAI_ENDPOINT
            )

    def generate_explanation(self, rule_results: List[Any], context_docs: List[str], doc_type: str = "CONTRACT") -> str:
        if not self.client:
            return "분석 결과 (Mock): 모의 분석이 완료되었습니다. 실제 API 연결이 필요합니다."

        try:
            # Construct Prompt based on Doc Type
            if doc_type == "LABOR":
                 prompt_context = "위 데이터를 바탕으로 근로자를 위한 '근로계약 위험성 분석 보고서'를 작성해주세요."
                 role_definition = "당신은 대한민국 노동법 전문가입니다. 근로자의 권리를 보호하기 위해 근로계약서를 분석하고 조언을 제공합니다."
            else:
                 prompt_context = "위 데이터를 바탕으로 임차인을 위한 '전세/임대차 계약 위험성 분석 보고서'를 작성해주세요."
                 role_definition = "당신은 대한민국 부동산 법률 전문가입니다. 임차인의 권리를 보호하기 위해 계약서를 분석하고 조언을 제공합니다."

            prompt = f"""
            [분석 데이터]
            1. 규칙 검증 결과: {rule_results}
            2. 관련 법령 및 판례: {context_docs}

            {prompt_context}
            
            [작성 지침]
            - 언어: 한국어 (전문적이면서도 이해하기 쉽게)
            - **필수 출력 형식 (아래 형식을 무조건 따를 것)**:
              1. **[종합 요약]**: 전체적인 안전 등급과 계약의 핵심 내용을 3줄 이내로 요약.
              2. **[주요 위험 요소]**: 발견된 위험이 있다면 법적 근거와 함께 구체적으로 설명 (없으면 '특이사항 없음' 기재).
              3. **[행동 가이드]**: 계약 당사자가 반드시 확인해야 할 사항이나 특약 사항을 번호 매겨서 나열.
            - 톤앤매너: 객관적이고 신뢰감 있게.
            - 길이: 전체 500자 이내로 핵심만 전달.
            - 주의: 불필요한 미사여구 제외. 바로 본론부터 시작하세요.
            """
            
            response = self.client.chat.completions.create(
                model=settings.AZURE_OPENAI_DEPLOYMENT_NAME,
                messages=[
                    {"role": "system", "content": role_definition},
                    {"role": "user", "content": prompt}
                ],
                seed=42
            )
            return response.choices[0].message.content
        except Exception as e:
            logger.error(f"LLM Generation Failed: {e}")
            raise AnalysisException(
                Stage.LLM_GENERATE, "LLM_GENERATION_FAILED", "설명 생성 중 오류가 발생했습니다.",
                {"detail": str(e)}, "잠시 후 다시 시도해주세요."
            )
    def extract_data_from_text(self, text: str, doc_type: str = "CONTRACT") -> str:
        """
        Extracts structured JSON data from OCR text using Azure OpenAI.
        doc_type: "CONTRACT" or "REGISTRY"
        """
        if not self.client:
            logger.warning("LLM Client not available for extraction.")
            return "{}"

        system_prompt = "You are a specialized AI for Korean Real Estate Documents. Extract key fields precisely into JSON. Return ONLY the JSON object, no markdown."
        
        user_prompt = ""
        if doc_type == "CONTRACT":
            user_prompt = f"""
            [Task]
            Extract fields from the 'Real Estate Lease Contract' (전월세 계약서).
            Handle typoes and spacing issues intelligently (e.g. "1 억" -> 100000000).
            
            [Target Fields]
            - address: Target property address (소재지)
            - lessor_name: Landlord name (임대인)
            - lessee_name: Tenant name (임차인)
            - deposit_amount: Security deposit as Integer (보증금). e.g. "금 일억오천만원" -> 150000000
            - rent_amount: Monthly rent as Integer (월세). 0 if Jeonse.
            - term_start: Start date (YYYY-MM-DD)
            - term_end: End date (YYYY-MM-DD)
            
            [Input Text]
            {text[:6000]} 

            [Output JSON Format]
            {{
                "address": "String",
                "lessor_name": "String",
                "lessee_name": "String",
                "deposit_amount": Integer,
                "rent_amount": Integer,
                "term_start": "YYYY-MM-DD",
                "term_end": "YYYY-MM-DD"
            }}
            """
        elif doc_type == "REGISTRY":
            user_prompt = f"""
            [Task]
            Extract fields from the 'Real Estate Registry' (등기부등본).
            
            [Target Fields]
            - property_address: Address in Title Section (표제부 소재지)
            - owner_name: Final Owner in Gap-Gu (갑구 최종 소유자)
            - issue_date: Date of issuance usually at bottom (발행일/열람일)
            
            [Input Text]
            {text[:6000]}

            [Output JSON Format]
                "property_address": "String",
                "owner_name": "String",
                "issue_date": "YYYY-MM-DD"
            }}
            """
        elif doc_type == "LABOR":
            user_prompt = f"""
            [Task]
            Extract fields from the 'Standard Labor Contract' (표준근로계약서).
            
            [Target Fields]
            - employer_name: Employer/Company Name (사업주/업체명)
            - employee_name: Worker Name (근로자 성명). **IMPORTANT**: If the name has both Korean and English (e.g. "홍길동 (Hong Gil Dong)"), EXTRACT THE FULL STRING EXACTLY AS IS. Do not drop the Korean part.
            - start_date: Contract Start Date (근로개시일) - YYYY-MM-DD
            - end_date: Contract End Date (근로계약기간 종료일) - YYYY-MM-DD (null if indefinite)
            - salary: Monthly or Hourly Wage as Integer.
            - work_hours: Weekly or Daily work hours summary (String).
            
            [Input Text]
            {text[:6000]}
            
            [Output JSON Format]
            {{
                "employer_name": "String",
                "employee_name": "String",
                "start_date": "YYYY-MM-DD",
                "end_date": "YYYY-MM-DD",
                "salary": Integer,
                "work_hours": "String"
            }}
            """
        else:
            return "{}"
        
        try:
            response = self.client.chat.completions.create(
                model=settings.AZURE_OPENAI_DEPLOYMENT_NAME,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.1, # Low temperature for extraction
                seed=42
            )
            # Remove any Markdown code block syntax if present
            content = response.choices[0].message.content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.endswith("```"):
                content = content[:-3]
            return content.strip()
        except Exception as e:
            logger.error(f"LLM Extraction Failed: {e}")
            return "{}"

    def detect_toxic_candidates(self, text: str, doc_type: str = "CONTRACT") -> List[Dict[str, Any]]:
        """
        Stage 1: Scan for potential toxic clauses.
        doc_type: "CONTRACT" (Lease) or "LABOR" (Labor)
        Returns list of { "original_text": "...", "risk_type": "ILLEGAL"|"UNFAIR", "reason": "..." }
        """
        if not self.client: return []
        
        system_prompt = "You are a legal AI scanner. Identify potentially unfair or illegal clauses in the provided Contract. Return JSON list."
        
        if doc_type == "CONTRACT": # Lease
            user_prompt = f"""
            [Input Lease Contract Text]
            {text[:8000]}
            
            [Task]
            Scan for clauses that might be:
            1. **ILLEGAL**: Violates Housing Lease Protection Act (e.g., shorter than 2 years is valid only for tenant).
            2. **UNFAIR**: Unreasonably disadvantageous to the tenant (e.g., "Tenant pays all repair costs", "Immediate eviction on small breach").
            
            [Output Format - JSON Only]
            [ {{ "original_text": "...", "risk_type": "ILLEGAL"|"UNFAIR", "reason": "..." }}, ... ]
            """
        elif doc_type == "LABOR":
            user_prompt = f"""
            [Input Labor Contract Text]
            {text[:6000]}
            
            [Task]
            Scan for clauses that might be ILLEGAL or UNFAIR under Korean Labor Standards Act (근로기준법).
            Focus on:
            1. **Penalty / Damages**: "If you quit early, you pay 500 dollars." (위약금 예정 금지 위반)
            2. **Broad Offset**: "Damages will be deducted from salary directly." (전액 지급 원칙 위반)
            3. **Unfair Dismissal**: "Employer can fire immediately without notice." (해고 예고 위반)
            4. **Forced Overtime**: "Must work overtime whenever requested without extra pay." (포괄임금 오남용)
            5. **Scope of Work**: "Do anything the boss says." (Too broad)
            
            [Output Format - JSON Only]
            [ {{ "original_text": "Clause content...", "risk_type": "ILLEGAL"|"UNFAIR", "reason": "Brief reason in Korean" }}, ... ]
            If none, return [].
            """
        else:
            return []
        
        try:
            response = self.client.chat.completions.create(
                model=settings.AZURE_OPENAI_DEPLOYMENT_NAME,
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                temperature=0.0
            )
            content = response.choices[0].message.content.strip()
            # Clean Markdown
            if content.startswith("```json"): content = content[7:]
            if content.endswith("```"): content = content[:-3]
            
            import json
            candidates = json.loads(content.strip())
            return candidates if isinstance(candidates, list) else []
        except Exception as e:
            logger.error(f"Toxic Candidate Scan Failed: {e}")
            return []

    def verify_toxic_clause(self, clause: Dict[str, Any], rag_evidence: str) -> Dict[str, Any]:
        """
        Stage 3: Verify suspicious clause against RAG evidence.
        Returns { "is_toxic": bool, "legal_basis": "..." }
        """
        if not self.client: return {"is_toxic": False}
        
        system_prompt = "You are a Data Judge. Verify if the clause is truly toxic based on the provided Legal Evidence. Output MUST be in Korean."
        user_prompt = f"""
        [Suspicious Clause]
        "{clause.get('original_text')}"
        (Reason: {clause.get('reason')})
        
        [Legal Evidence / Precedents]
        {rag_evidence}
        
        [Task]
        Does this clause contradict the evidence or standard legal protections?
        - If YES (Toxic): Explain WHY citing the Law Name/Article or Case Content from Evidence.
        - If NO (Safe/Standard): Return is_toxic: false.
        
        [Constraint]
        1. **Language**: Korean Only (한국어).
        2. **Length**: 1-2 sentences maximum. Concise.
        3. **Citation**: Do NOT mention filenames (e.g. 'paper.pdf'). Cite the 'Law Name' (법령명) or 'Precedent Content' (판례 내용) directly.
        
        [Output JSON]
        {{
            "is_toxic": true/false,
            "legal_basis": "Korean explanation with proper citation (e.g. '주택임대차보호법 제3조에 위반됨')."
        }}
        """
        
        try:
            response = self.client.chat.completions.create(
                model=settings.AZURE_OPENAI_DEPLOYMENT_NAME,
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                temperature=0.0
            )
            content = response.choices[0].message.content.strip()
            if content.startswith("```json"): content = content[7:]
            if content.endswith("```"): content = content[:-3]
            
            import json
            return json.loads(content.strip())
        except Exception as e:
            logger.error(f"Toxic Verification Failed: {e}")
            return {"is_toxic": False, "error": str(e)}
    def translate_analysis_result(self, summary_text: str, rules: List[Any], target_lang: str) -> Dict[str, Any]:
        """
        Translates the analysis result (Summary + Rules) into the Target Language.
        User Requirement:
        1. Translate the Korean text fully (don't summarize significantly).
        2. If a term has no direct 1:1 match (e.g. Jeonse, Geun-Ju-Dang), keep the translation but ADD a brief explanation in parentheses.
        """
        if not self.client: return {"translated_summary": summary_text, "translated_rules": []}
        
        # Prepare content to translate
        rules_content = []
        for idx, r in enumerate(rules):
            advice_legal = r.ai_advice.legal_review if r.ai_advice else ""
            advice_action = r.ai_advice.action_guide if r.ai_advice else ""
            
            rules_content.append({
                "id": idx + 1,
                "title": r.title,
                "evidence": r.evidence.detail if r.evidence else "",
                "legal_review": advice_legal,
                "action_guide": advice_action
            })
            
        import json
        rules_json = json.dumps(rules_content, ensure_ascii=False)
            
        # Validate and map language code to full name for better LLM context
        LANG_MAP = {
            "ko": "Korean", "en": "English", "ne": "Nepali", 
            "km": "Khmer (Cambodian)", "id": "Indonesian", 
            "vi": "Vietnamese", "my": "Burmese (Myanmar)", "th": "Thai"
        }
        target_lang_name = LANG_MAP.get(target_lang, target_lang)

        # Logic to relax strictness for English
        no_english_rule = ""
        if target_lang != "en":
            no_english_rule = f"2. **NO English**: Do NOT output English unless the Target Language is English. Even if the target language is difficult, try to use {target_lang_name} or keep it in Korean if impossible. English is FORBIDDEN."
        else:
            no_english_rule = "2. **English Output**: Translate everything naturally into English."

        user_prompt = f"""
        [Source Language] Korean
        [Target Language] {target_lang_name} (Code: {target_lang})
        
        [Task]
        Translate the provided 'Analysis Report' from Korean to the Target Language ({target_lang_name}).
        
        [Guidelines]
        1. **Strict Translation**: Translate 'Legal Review', 'Action Guide', 'Summary', and 'Title' into {target_lang_name}.
        {no_english_rule}
        3. **Evidence Field**: 
           - **KEEP IN KOREAN**: The 'evidence' field contains direct quotes from the contract. You MUST keep the 'evidence' text in KOREAN. Do NOT translate the contract content.
        4. **Term Handling & Explanation**:
           - Use the official or closest legal terms in {target_lang_name}.
           - **CRITICAL**: If a term has no direct 1:1 equivalent, provide a brief explanation in {target_lang_name} within parentheses.
           - Format: "Translated Term (Explanation in {target_lang_name})"
        5. **Fields**:
           - 'translated_summary': Single string (paragraphs separated by \\n\\n) in {target_lang_name}.
           - 'legal_review', 'action_guide': Translate fully into {target_lang_name}.
           - 'evidence': KEEP IN KOREAN (Source Text).
           - 'title': Translate into {target_lang_name}.
        
        [Input Data]
        -- Summary Text --
        {summary_text}
        
        -- Detected Rules (JSON) --
        {rules_json}
        
        [Output JSON Format]
        {{
            "translated_summary": "Summary in {target_lang_name}...",
            "translated_rules": [
                {{ 
                    "id": 1, 
                    "title": "Title in {target_lang_name}", 
                    "evidence": "Original Korean Contract Text (Do not translate)",
                    "legal_review": "Review in {target_lang_name}", 
                    "action_guide": "Guide in {target_lang_name}"
                }},
                ...
            ]
        }}
        """
        
        try:
            response = self.client.chat.completions.create(
                model=settings.AZURE_OPENAI_DEPLOYMENT_NAME,
                messages=[
                    {"role": "system", "content": "You are a professional legal translator. Translate accurately and comprehensively."},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.3,
                max_tokens=4000
            )
            content = response.choices[0].message.content.strip()
            
            # Debug Log LLM Output
            with open("debug_translation.txt", "a", encoding="utf-8") as f:
                f.write(f"\nDEBUG[LLM Output]: {content[:500]}...\n")

            if content.startswith("```json"): content = content[7:]
            if content.endswith("```"): content = content[:-3]
            
            import json
            # strict=False allows control characters like newlines inside strings
            return json.loads(content.strip(), strict=False)
        except Exception as e:
            logger.error(f"Translation Failed: {e}")
            return {"translated_summary": summary_text, "translated_rules": []}
