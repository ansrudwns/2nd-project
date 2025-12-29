from fastapi import APIRouter, UploadFile, File, Form, Depends
import logging
import os
import uuid
from typing import List
from app.core.pipeline import PipelineRunner, Stage
from app.core.exceptions import AnalysisException
from app.schemas.common import BaseResponse
from app.schemas.analysis import AnalysisResultResponse
from app.services.validator import FileValidator, DocTypeClassifier
from app.services.ocr import OCRService
from app.utils.parsers import AmountParser, AddressParser
from app.services.rule_engine import RuleEngine
from app.schemas.documents import Contract, Registry, DocumentData
from app.services.pii import PiiService
from app.services.rag import RAGService
from app.services.llm import LLMService

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/analyze", response_model=BaseResponse) # Generic Response
async def analyze_documents(
    contract_file: UploadFile = File(...),
    registry_file: UploadFile = File(...)
):
    runner = PipelineRunner()
    
    # Define Steps
    
    # 1. Validation Step
    async def step_validate(ctx):
        # Validate Contract
        c_content = await contract_file.read()
        FileValidator.validate(c_content, contract_file.filename, contract_file.content_type)
        ctx['contract_bytes'] = c_content
        
        # Validate Registry
        r_content = await registry_file.read()
        FileValidator.validate(r_content, registry_file.filename, registry_file.content_type)
        ctx['registry_bytes'] = r_content
        
        # Store extension for saving later
        import os
        _, ext = os.path.splitext(registry_file.filename)
        ctx['registry_ext'] = ext.lower() if ext else ".pdf"

    step_validate.stage_id = Stage.FILE_VALIDATE

    # 2. OCR Step
    async def step_ocr(ctx):
        ocr = OCRService()
        # Mocking mime for now if not detected correctly
        ctx['contract_ocr'] = ocr.extract(ctx['contract_bytes'], contract_file.content_type)
        ctx['registry_ocr'] = ocr.extract(ctx['registry_bytes'], registry_file.content_type)
        
        # Simple text extraction for MVP (Assuming 'content' key available)
        ctx['contract_text'] = ctx['contract_ocr'].get('content', '')
        ctx['registry_text'] = ctx['registry_ocr'].get('content', '')
        
    step_ocr.stage_id = Stage.OCR

    # 3. Doc Type Check
    async def step_classify(ctx):
        # Verify valid types
        c_type = DocTypeClassifier.classify(ctx['contract_text'])
        r_type = DocTypeClassifier.classify(ctx['registry_text'])
        
        if c_type != 'contract':
            raise AnalysisException(Stage.DOC_TYPE_DETECT, "INVALID_DOC_TYPE", "첫번째 파일은 계약서여야 합니다.")
        if r_type != 'registry':
            raise AnalysisException(Stage.DOC_TYPE_DETECT, "INVALID_DOC_TYPE", "두번째 파일은 등기부등본이어야 합니다.")
            
    step_classify.stage_id = Stage.DOC_TYPE_DETECT

    # 4. Normalize (Parse to Schema)
    # 4. Normalize (Parse to Schema)
    async def step_normalize(ctx):
        import re
        
        # Simple Heuristic Extraction Helper
        def extract_regex(text: str, label: str) -> str:
            # Common patterns for Korean documents (Refined)
            patterns = {
                "address": [r"\[집합건물\]\s*(.+)", r"소\s*재\s*지\s*[:]?\s*\[?도로명주소\]?\s*(.+)", r"소\s*재\s*지(?!번)\s*[:]?\s*(.+)", r"주\s*소\s*[:]?\s*(.+)", r"건물내역\s*[:]\s*(.+)"],
                "deposit": [r"보\s*증\s*금\s*[:]?\s*금\s*([\d억천만\s,]+)원", r"보\s*증\s*금\s*[:]?\s*([\d억천만\s,]+)", r"금\s*([\d억천만\s,]+)원"],
                "lessor": [r"임\s*대\s*인\s*[:]?\s*[^(]*\((.*?)\)", r"임\s*대\s*인\s*[:]?\s*([가-힣]{2,4})"], 
                "lessee": [r"임\s*차\s*인\s*[:]?\s*[^(]*\((.*?)\)", r"임\s*차\s*인\s*[:]?\s*([가-힣]{2,4})"],
                "owner": [r"소유자\s*([가-힣]{2,4})", r"성명\s*[:]?\s*([가-힣]{2,4})", r"권리자\s*([가-힣]{2,4})"], 
                "date": [r"(\d{4}년\s*\d{1,2}월\s*\d{1,2}일)"]
            }
            
            # Don't replace newlines globally to prevent (.) from matching the whole file
            # clean_text = text.replace("\n", " ") 
            
            for p in patterns.get(label, []):
                match = re.search(p, text)
                if match:
                    # Return the capture group that is not None
                    for group in match.groups():
                        if group:
                            val = group.strip()
                            # If captured text spans multiple lines (unlikely with . but possible if custom flags), split
                            return val.split('\n')[0].strip()
            return ""

        c_text = ctx['contract_text']
        r_text = ctx['registry_text']
        
        # Attempt Extraction
        c_address = extract_regex(c_text, "address") or ""
        c_deposit = extract_regex(c_text, "deposit") or ""
        
        # More robust name extraction
        c_lessor = extract_regex(c_text, "lessor") or ""
        c_lessee = extract_regex(c_text, "lessee") or ""
        
        # Registry often splits address. 
        r_address = extract_regex(r_text, "address") or c_address 
        
        # Registry Owner: Try to find '소유자' followed by name.
        # Fallback: if registry parsing fails, assume match for MVP flow (or set empty to force FAIL)
        # Setting distinct default to verify rule engine
        r_owner = extract_regex(r_text, "owner")
        if not r_owner:
            # If failed, try to use c_lessor to give benefit of doubt OR default to something else?
            # User complained "Safe when different". So defaults should be different if fails?
            r_owner = "소유자미상"
        
        ctx['contract_obj'] = Contract(
            address=c_address,
            lessor_name=c_lessor,
            lessee_name=c_lessee,
            deposit_amount=AmountParser.parse(c_deposit),
            term_start="2024-01-01", # Date parsing is complex, fallback for now
            term_end="2026-01-01"
        )
        
        ctx['registry_obj'] = Registry(
            property_address=r_address,
            owner_name=r_owner,
            issue_date="2024-01-01"
        )
        
    step_normalize.stage_id = Stage.SCHEMA_NORMALIZE

    # 5. Market Price API Step (Moved BEFORE Rules)
    async def step_market(ctx):
        from app.services.market import MarketService
        # Extract location from contract object
        # Simple parser logic or default
        address = ctx['contract_obj'].address
        parts = address.split()
        sigungu = parts[1] if len(parts) > 1 else ""
        dong = parts[2] if len(parts) > 2 else ""
        
        price_info = await MarketService.get_market_price(sigungu, dong)
        ctx['market_price'] = price_info
    
    step_market.stage_id = Stage.MARKET_PRICE

    # 6. Rule Engine
    async def step_rules(ctx):
        re = RuleEngine()
        # Pass Market Price for Comparison
        ctx['rule_results'] = re.run(ctx['contract_obj'], ctx['registry_obj'], ctx.get('market_price'))
        
    step_rules.stage_id = Stage.RULE_ENGINE

    # 6. PII Masking Step (Real Regex on OCR Lines)
    # 6. PII Masking Step (Advanced)
    # 6. PII Masking Step (Azure Native)
    async def step_pii(ctx):
        from app.services.pii import PiiService
        
        pii_service = PiiService()
        # Clean target address for exclusion (remove spaces)
        target_addr_clean = ctx['contract_obj'].address.replace(" ", "") if ctx.get('contract_obj') and ctx['contract_obj'].address else ""

        def process_doc(ocr_result, known_values=None):
            if not ocr_result: return []
            
            # 1. Linearize Text & Build Map
            full_text = ""
            text_map = [] # (start, end, word_obj)
            
            pages = ocr_result.get('pages', [])
            for p_idx, page in enumerate(pages):
                words = page.get('words', [])
                for w in words:
                    content = w.get('content', '')
                    start_idx = len(full_text)
                    full_text += content + " " 
                    end_idx = len(full_text) - 1 
                    w['page_idx'] = p_idx 
                    text_map.append((start_idx, end_idx, w))
            
            if not full_text.strip():
                return []

            # 2. Azure PII Detection
            entities = pii_service.detect_pii(full_text)
            
            # --- HYBRID EXTENSION: Add Regex-found values ---
            if known_values:
                # known_values is a list of strings (e.g. ["Hong Gil Dong"])
                # We artificially create "PII Entities" for these.
                # Problem: full_text has spaces inserted between words. "Hong Gil Dong" might be "Hong Gil Dong" or "HongGilDong"
                # Solution: Create a flexible regex pattern from the known string.
                import re
                for val in known_values:
                    if not val or len(val) < 2: continue
                    
                    # Create pattern: "홍길동" -> "홍\s*길\s*동"
                    # Escape chars first, then join with \s*
                    val_chars = list(val)
                    escaped_chars = [re.escape(c) for c in val_chars if c.strip()]
                    if not escaped_chars: continue
                    
                    # Allow variable spaces between meaningful characters
                    pattern_str = r"\s*".join(escaped_chars)
                    
                    # Search
                    try:
                        for m in re.finditer(pattern_str, full_text):
                            entities.append({
                                "text": m.group(),
                                "category": "HybridFallback", 
                                "subcategory": None,
                                "offset": m.start(),
                                "length": len(m.group()),
                                "confidence_score": 1.0
                            })
                    except re.error:
                        print(f"Regex Error for pattern: {pattern_str}")
                        continue
            # ------------------------------------------------

            boxes = pii_service.map_pii_to_boxes(entities, pages, text_map)

            # 4. Exclusion & Refinement
            final_boxes = []
            for b in boxes:
                # Exclusion: Target Address
                t_clean = b['text'].replace(" ", "")
                if target_addr_clean and len(t_clean) > 5 and (t_clean in target_addr_clean or target_addr_clean in t_clean):
                    continue 

                # Keyword Filter
                if b['text'] in ["임대인", "임차인", "소유자", "대리인", "주소", "성명", "주민등록번호"]:
                    continue

                # Partial Masking Logic (Person Name)
                # Apply to 'Person' category AND our 'HybridFallback' if it looks like a name (len < 5?)
                is_person = b.get('category') == 'Person' or (b.get('category') == 'HybridFallback' and len(b['text']) < 6)
                
                if is_person and len(b['text']) >= 2:
                     x1, y1, x2, y2 = b['box_norm']
                     width = x2 - x1
                     char_w = width / len(b['text'])
                     mask_x1 = x1 + (char_w * 0.9) # Leave 1st char estimate
                     
                     if mask_x1 < x2:
                        b['box_norm'] = [mask_x1, y1, x2, y2]
                
                final_boxes.append(b)
                
            return final_boxes

        # Gather Known Values from Regex Extraction
        # These are the "Truths" found by the Report
        c_obj = ctx.get('contract_obj')
        known_contract_pii = []
        if c_obj:
            if c_obj.lessor_name: known_contract_pii.append(c_obj.lessor_name)
            if c_obj.lessee_name: known_contract_pii.append(c_obj.lessee_name)
            # Add other known regex fields if needed (RRN not in obj usually)
        
        ctx['contract_pii'] = process_doc(ctx.get('contract_ocr'), known_values=known_contract_pii)
        
        # Registry Knowns
        r_obj = ctx.get('registry_obj')
        known_registry_pii = []
        if r_obj and r_obj.owner_name:
            known_registry_pii.append(r_obj.owner_name)

        ctx['registry_pii'] = process_doc(ctx.get('registry_ocr'), known_values=known_registry_pii)


            # 8. RAG & LLM
    async def step_ai(ctx):
        try:
            rag = RAGService()
            llm = LLMService()
            
            rag_results = []
            
            # 1. Collect RAG context for Global Summary
            if not ctx['rule_results']:
                 rag_results.extend(rag.search_category("laws", "임대차 계약 주의사항"))
            
            failed_rules = [r for r in ctx['rule_results'] if r.status == 'FAIL']
            
            for r in failed_rules:
                # Routing Logic matches User Request
                search_query = r.title + " " + r.evidence.detail
                if r.rule_id == "RIGHTS": 
                    rag_results.extend(rag.search_category("laws", "울구 선순위 근저당 권리 분석"))
                    rag_results.extend(rag.search_category("cases", "선순위 근저당 전세금 미반환 사례"))
                elif r.rule_id == "ADDR" or r.rule_id == "OWNER":
                    rag_results.extend(rag.search_category("laws", "임대차 계약 당사자 확인 및 대항력"))
                elif r.rule_id == "USAGE":
                    rag_results.extend(rag.search_category("laws", "불법건축물 전세자금대출 위반건축물"))
                    rag_results.extend(rag.search_category("cases", "위반건축물 임대차 계약 분쟁"))
                elif r.rule_id == "PRICE":
                     rag_results.extend(rag.search_category("cases", "깡통전세 예방 보증보험"))
                else:
                    rag_results.extend(rag.search_all(search_query))

            rag_results = list(set(rag_results)) # Dedupe
            
            # Market Context
            market_context = f"\n[주변 시세 정보]\n해당 지역({ctx['contract_obj'].address}) 전세 평균: {ctx.get('market_price', '데이터 없음')}"
            rag_results.append(market_context)

            # 2. Per-Rule Detailed Advice (Parallel or Sequential)
            
            if failed_rules:
                from app.schemas.analysis import AIAdvice
                from app.core.config import settings
                
                # Create a prompt for itemized advice
                itemized_prompt = "다음은 임대차 계약 분석에서 발견된 위험 항목들입니다. 각 항목에 대해 '법률적 검토(legal_review)'와 '행동 가이드(action_guide)'를 JSON으로 작성하세요.\n"
                itemized_prompt += "**필수 사항: 내용은 무조건 1~2문장으로 아주 간결하고 명확하게 요약하세요. 긴 설명은 금지입니다.**\n\n"
                
                for idx, r in enumerate(failed_rules):
                    itemized_prompt += f"{idx+1}. {r.title}: {r.evidence.detail}\n"
                
                itemized_prompt += f"\n참고:\n{str(rag_results[:3])}\n"
                itemized_prompt += """
                JSON Format:
                [{"legal_review": "핵심만 간결하게(50자 내외)", "action_guide": "구체적 행동 1줄(50자 내외)"}, ...]
                """
                
                try:
                    advice_json_str = llm.client.chat.completions.create(
                        model=settings.AZURE_OPENAI_DEPLOYMENT_NAME, # Use correct deployment
                        messages=[
                            {"role": "system", "content": "당신은 부동산 법률 전문가입니다. JSON만 출력하세요."},
                            {"role": "user", "content": itemized_prompt}
                        ]
                    ).choices[0].message.content
                    
                    import json
                    # Naive cleanup
                    advice_json_str = advice_json_str.strip()
                    if "```json" in advice_json_str:
                        advice_json_str = advice_json_str.split("```json")[1].split("```")[0]
                    elif "```" in advice_json_str:
                        advice_json_str = advice_json_str.split("```")[1].split("```")[0]
                    
                    advice_list = json.loads(advice_json_str)
                    
                    # Map back to rules
                    # Note: LLM might return different length if it skips items. 
                    # Ideally we match by title, but index assuming sequential generation for now.
                    for i, advice in enumerate(advice_list):
                        if i < len(failed_rules):
                            failed_rules[i].ai_advice = AIAdvice(
                                legal_review=advice.get("legal_review", "검토 내용 없음"),
                                action_guide=advice.get("action_guide", "가이드 없음")
                            )
                except Exception as e:
                    logger.warning(f"Itemized Advice Generation Failed: {e}")
                    # Fallback
                    for r in failed_rules:
                        r.ai_advice = AIAdvice(legal_review=f"AI 분석 지연 ({str(e)})", action_guide="전문가와 상의하세요.")


            # 3. Global Summary (Existing)
            ctx['summary_text'] = llm.generate_explanation(ctx['rule_results'], rag_results)
            
        except Exception as e:
            # Expose error detail to Frontend for debugging
            import traceback
            logger.error(traceback.format_exc())
            raise AnalysisException(Stage.LLM_GENERATE, "LLM_DEBUG_ERROR", f"AI 단계 오류: {str(e)}")

    # 7. Final Result Construction & Visualization
    async def step_result(ctx):
        from app.services.visualizer import VisualizerService
        import os
        import uuid
        
        # 1. Visualize Contract
        # Map Rule Failures to OCR Lines
        
        def map_risk_to_box(ocr_result, evidence_detail, doc_type="contract"):
            if not evidence_detail: return []
            boxes = []
            
            # Extract specific targets from evidence tags like Contract[...], Registry[...]
            import re
            
            # Pattern to finding tags
            # e.g. Contract[Addr]
            tag_pattern = r"(Contract|Registry|Deposit)\[(.*?)\]"
            matches = re.findall(tag_pattern, evidence_detail)
            
            keywords = []
            
            if matches:
                # Use tagged content
                for tag, content in matches:
                    if doc_type == "contract":
                        if tag in ["Contract", "Deposit"]:
                            keywords.append(content)
                    elif doc_type == "registry":
                        if tag in ["Registry"]:
                            keywords.append(content)
            else:
                # Fallback to legacy heuristic
                sub_keywords = re.findall(r"\((.*?)\)", evidence_detail)
                if not sub_keywords:
                     keywords = [w for w in evidence_detail.split() if len(w) > 3]
                else:
                    keywords = sub_keywords
            
            if not keywords:
                return []
            
            # Create a set of "Target Tokens"
            target_tokens = set()
            for k in keywords:
                # Clean and tokenize
                # Allow commas in numbers
                k_clean = re.sub(r'[^\w\s,]', ' ', k)
                for t in k_clean.split():
                    # Check if it's a number with commas
                    t_norm = t.replace(",", "")
                    if len(t_norm) >= 2:
                        if all(c.isdigit() for c in t_norm):
                             if len(t_norm) < 4: continue # Ignore small numbers like '101' unless part of phrase
                             target_tokens.add(t_norm)
                        else:
                             # For text, we might want to keep original or clean further
                             # Clean punctuation from text tokens
                             t_text = re.sub(r'[^\w]', '', t)
                             if len(t_text) >= 2:
                                 target_tokens.add(t_text)

            if not target_tokens:
                return []
                
            if not ocr_result: return []
            
            # Search Logic: Smart Hybrid Matching with Noise Filtering
            
            STOPWORDS = {"시", "도", "구", "군", "면", "동", "읍", "리", "가", "로", "길", "층", "호", "번지", "아파트", "빌라", "주택", "오피스텔", "특별시", "광역시", "특별자치시"}

            # Pre-classify target tokens
            target_nums = {t for t in target_tokens if t.isdigit()}
            target_texts = target_tokens - target_nums
            # Filter generic words from target texts for scoring
            target_texts_specific = {t for t in target_texts if t not in STOPWORDS}
            
            for page_idx, page in enumerate(ocr_result.get('pages', [])):
                p_w = page.get('width', 0) or 1
                p_h = page.get('height', 0) or 1
                
                lines = page.get('lines', [])
                for line in lines:
                    text = line.get('content', '')
                    if not text: continue
                    
                    # Tokenize line
                    line_tokens = set()
                    text_clean = re.sub(r'[^\w\s,]', ' ', text) # Keep commas
                    for t in text_clean.split():
                        t_norm = t.replace(",", "")
                        if len(t_norm) >= 2:
                             if all(c.isdigit() for c in t_norm):
                                 line_tokens.add(t_norm)
                             else:
                                 t_text = re.sub(r'[^\w]', '', t)
                                 if len(t_text) >= 2:
                                     line_tokens.add(t_text)
                            
                    line_nums = {t for t in line_tokens if t.isdigit()}
                    line_texts = line_tokens - line_nums
                    line_texts_specific = {t for t in line_texts if t not in STOPWORDS}
                    
                    is_match = False

                    # 1. Numeric Match + Context (Strict)
                    if not target_nums.isdisjoint(line_nums):
                         overlap_specific = target_texts_specific.intersection(line_texts_specific)
                         if len(overlap_specific) >= 1:
                             is_match = True
                        
                    # 2. Strong Text Match (Context Only)
                    elif len(target_texts_specific.intersection(line_texts_specific)) >= 2:
                         is_match = True

                    # 3. Fallback: Exact Short Match (Names, Deposit Amounts)
                    # Deposit Amount might be digit only or "1억2천"
                    elif len(target_tokens) <= 2:
                        overlap = target_tokens.intersection(line_tokens)
                        ratio = len(overlap) / len(target_tokens)
                        if ratio == 1.0:
                             for k in keywords:
                                if k.replace(" ", "") in text.replace(" ", ""):
                                    is_match = True
                                    break
                    
                    if is_match:
                        poly = line.get('polygon', [])
                        if len(poly) >= 8:
                            xs = poly[0::2]
                            ys = poly[1::2]
                            box_norm = [min(xs)/p_w, min(ys)/p_h, max(xs)/p_w, max(ys)/p_h]
                            boxes.append({"box_norm": box_norm, "page_idx": page_idx})

            # Filter Strategy for Registry: Keep only Top match per page to avoid noise
            if doc_type == "registry" and boxes:
                # Sort by Y-coordinate (box_norm[1])
                # Assuming top of page is 0?
                # OCR results typically have Y=0 at TOP. visualizer inverts it.
                # So smallest Y is top.
                boxes.sort(key=lambda b: b['box_norm'][1])
                # Keep top 1
                boxes = boxes[:1]

            return boxes

        # Prepare Risks with Labels matching the Filtered List
        c_risks = []
        r_risks = []
        
        # We only care about FAIL items for visualization now
        failed_rules = [r for r in ctx['rule_results'] if r.status == 'FAIL']
        
        for idx, r in enumerate(failed_rules):
            label = str(idx + 1)
            # Contract Risks
            found_boxes = map_risk_to_box(ctx.get('contract_ocr'), r.evidence.detail, doc_type="contract")
            for b in found_boxes:
                # Merge logic
                c_risks.append({"box_norm": b['box_norm'], "page_idx": b['page_idx'], "severity": r.severity, "label": label})
                
            # Registry Risks
            found_boxes = map_risk_to_box(ctx.get('registry_ocr'), r.evidence.detail, doc_type="registry")
            for b in found_boxes:
                r_risks.append({"box_norm": b['box_norm'], "page_idx": b['page_idx'], "severity": r.severity, "label": label})

        # Generate Contract PDF
        c_pdf_bytes = VisualizerService.create_masked_document(
            ctx['contract_bytes'],
            ctx.get('contract_pii', []),
            c_risks
        )
        
        # Generate Registry PDF (Always PDF output)
        r_pdf_bytes = VisualizerService.create_masked_document(
            ctx['registry_bytes'],
            ctx.get('registry_pii', []), # Mask RRNs in Registry too
            r_risks
        )
        
        # Save Files
        c_filename = f"{uuid.uuid4()}_contract.pdf"
        c_path = os.path.join("uploads", c_filename)
        with open(c_path, "wb") as f:
            f.write(c_pdf_bytes)
            
        r_filename = f"{uuid.uuid4()}_registry.pdf" # Force .pdf extension
        r_path = os.path.join("uploads", r_filename)
        with open(r_path, "wb") as f:
            f.write(r_pdf_bytes)
            
        file_url = f"http://localhost:8000/static/{c_filename}"
        registry_url = f"http://localhost:8000/static/{r_filename}"

        # Clean up Rule Evidence for Frontend Display
        # Pretty print specific tags
        import re
        cleaned_rules = []
        for r in ctx['rule_results']:
            if r.evidence and r.evidence.detail:
                detail = r.evidence.detail
                
                # Try to parse tags
                c_match = re.search(r"Contract\[(.*?)\]", detail, re.DOTALL)
                r_match = re.search(r"Registry\[(.*?)\]", detail, re.DOTALL)
                d_match = re.search(r"Deposit\[(.*?)\]", detail, re.DOTALL)
                
                new_detail = detail # Default fallback
                
                if c_match and r_match:
                    c_val = c_match.group(1).strip()
                    r_val = r_match.group(1).strip()
                    # Truncate for UI
                    if len(c_val) > 30: c_val = c_val[:30] + "..."
                    if len(r_val) > 30: r_val = r_val[:30] + "..."
                    new_detail = f"계약서: {c_val}\n등기부: {r_val}"
                    
                elif d_match:
                    val = d_match.group(1).strip()
                    # Format with commas
                    if val.isdigit():
                        try:
                            val = f"{int(val):,}"
                        except:
                            pass
                    # Keep the original warning message part?
                    # Usually "Warning... Deposit[...]". capture preamble.
                    preamble = detail.split("Deposit[")[0].strip()
                    new_detail = f"{preamble} (보증금: {val})"
                
                elif c_match: # Only Contract (Unlikely for mismatch, but possible)
                     val = c_match.group(1).strip()
                     if len(val) > 40: val = val[:40] + "..."
                     preamble = detail.split("Contract[")[0].strip()
                     new_detail = f"{preamble} ({val})"

                r.evidence.detail = new_detail
            
            cleaned_rules.append(r)

        ctx['result'] = AnalysisResultResponse(
            analysis_id=str(uuid.uuid4()),
            summary={
                "risk_count": len([r for r in ctx['rule_results'] if r.status == 'FAIL']),
                "highest_severity": "HIGH"
            },
            rules=cleaned_rules,
            documents={
                "masked_pdf_url": file_url,
                "registry_url": registry_url
            },
            summary_text=ctx.get('summary_text')
        )
            
    step_result.stage_id = Stage.RESULT_RENDER

    # Execute Pipeline
    return await runner.execute([
        step_validate,
        step_ocr,
        step_classify,
        step_normalize,
        step_market, # Price Info needed for Rules
        step_rules,
        step_pii,
        step_ai,
        step_result
    ])
