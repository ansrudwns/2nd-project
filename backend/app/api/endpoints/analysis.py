from fastapi import APIRouter, UploadFile, File, Form, Depends, Request
import logging
import os
import re
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
from app.db.session import get_db
from sqlalchemy.orm import Session
from app.api.endpoints.auth import get_current_user
from app.services.history_service import history_service

router = APIRouter()
router = APIRouter()
logger = logging.getLogger(__name__)
# Dependency Injection? Or direct use for now
from app.services.storage import BlobStorageService

@router.post("/analyze", response_model=BaseResponse) # Generic Response
async def analyze_documents(
    request: Request,
    contract_file: UploadFile = File(...),
    registry_file: UploadFile = File(...),
    target_language: str = Form("ko"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    runner = PipelineRunner()
    runner.context['request'] = request
    
    # Define Steps
    
    # 1. Validation Step
    async def step_validate(ctx):
        # Validate Contract
        c_content = await contract_file.read()
        FileValidator.validate(c_content, contract_file.filename, contract_file.content_type)
        
        from app.core.config import settings
        from app.utils.image_opt import optimize_image_bytes
        
        if settings.USE_IMAGE_OPTIMIZATION:
            print("🖼️ Optimizing Contract Image...")
            c_content = optimize_image_bytes(c_content)
            
        ctx['contract_bytes'] = c_content
        
        # Validate Registry
        r_content = await registry_file.read()
        FileValidator.validate(r_content, registry_file.filename, registry_file.content_type)
        
        if settings.USE_IMAGE_OPTIMIZATION:
            print("🖼️ Optimizing Registry Image...")
            r_content = optimize_image_bytes(r_content)
            
        ctx['registry_bytes'] = r_content
        
        # Store extension for saving later
        import os
        _, ext = os.path.splitext(registry_file.filename)
        _, ext = os.path.splitext(registry_file.filename)
        ctx['registry_ext'] = ext.lower() if ext else ".pdf"
        ctx['target_language'] = target_language

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
        
        if c_type != 'lease_contract':
            raise AnalysisException(Stage.DOC_TYPE_DETECT, "INVALID_DOC_TYPE", "업로드된 파일은 임대차 계약서가 아닙니다. (근로계약서나 다른 문서로 보입니다)", {"detected": c_type})
        if r_type != 'registry':
            raise AnalysisException(Stage.DOC_TYPE_DETECT, "INVALID_DOC_TYPE", "두번째 파일은 등기부등본이어야 합니다.")
            
    step_classify.stage_id = Stage.DOC_TYPE_DETECT

    # 4. Normalize (Parse to Schema)
    # 4. Normalize (Parse to Schema)
    async def step_normalize(ctx):
        from app.services.llm import LLMService
        import json
        
        llm = LLMService()
        
        # 1. Extract Contract Data
        c_text = ctx.get('contract_text', '')
        print("--- Starting LLM Extraction for Contract ---")
        try:
            c_json = llm.extract_data_from_text(c_text, "CONTRACT")
            # Loose parsing to handle potential bad json
            c_data = json.loads(c_json)
            
            # Type Casting Safety
            if 'deposit_amount' in c_data:
                try: 
                    val = str(c_data['deposit_amount']).replace(',', '').replace('원', '')
                    c_data['deposit_amount'] = int(val)
                except: 
                    c_data['deposit_amount'] = 0
                    
            if 'rent_amount' in c_data:
                try:
                    val = str(c_data['rent_amount']).replace(',', '').replace('원', '')
                    c_data['rent_amount'] = int(val)
                except:
                    c_data['rent_amount'] = 0

            # Create Pydantic Object
            ctx['contract_obj'] = Contract(**c_data)
            print(f"LLM Contract Extracted: {c_data.get('lessor_name')}, {c_data.get('deposit_amount')}")
            
        except Exception as e:
            print(f"LLM Contract Extraction Failed: {e}")
            # Fallback Empty Object to prevent pipeline crash
            ctx['contract_obj'] = Contract(
                address="추출 실패", lessor_name="", lessee_name="", deposit_amount=0, 
                term_start="", term_end=""
            )

        # 2. Extract Registry Data
        r_text = ctx.get('registry_text', '')
        print("--- Starting LLM Extraction for Registry ---")
        try:
            r_json = llm.extract_data_from_text(r_text, "REGISTRY")
            r_data = json.loads(r_json)
            
            ctx['registry_obj'] = Registry(**r_data)
            print(f"LLM Registry Extracted: {r_data.get('owner_name')}")
            
        except Exception as e:
            print(f"LLM Registry Extraction Failed: {e}")
            ctx['registry_obj'] = Registry(
                property_address="추출 실패", owner_name="", issue_date=""
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
        # Pass Market Price Data (Dict with price & source)
        ctx['rule_results'] = re.run(ctx['contract_obj'], ctx['registry_obj'], ctx.get('market_price'))
        
    step_rules.stage_id = Stage.RULE_ENGINE

    # 6. PII Masking Step
    async def step_pii(ctx):
        from app.services.pii import PiiService
        
        pii_service = PiiService()
        
        # Prepare Context
        contract_addr = ctx.get('contract_obj').address if ctx.get('contract_obj') else ""
        
        def process_doc(ocr_result, doc_type, target_addr_ctx=""):
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

            # 2. PII Detection (Type-Specific)
            context = {
                "target_address": target_addr_ctx
            }
            
            # Inject LLM Extracted Names into Context
            if ctx.get('contract_obj'):
                context['lessor_name'] = ctx['contract_obj'].lessor_name
                context['lessee_name'] = ctx['contract_obj'].lessee_name
            
            if ctx.get('registry_obj'):
                context['owner_name'] = ctx['registry_obj'].owner_name
            
            entities = pii_service.detect_pii(full_text, doc_type=doc_type, context=context)
            
            # 3. Map to Boxes
            boxes = pii_service.map_pii_to_boxes(entities, pages, text_map)
            
            return boxes

        # Determine Contract Type (Rent vs Labor)
        # AGGRESSIVE classification with multiple keyword checks
        def classify_doc_type(ocr_res):
            if not ocr_res: 
                print("DEBUG: No OCR result - defaulting to RENT")
                return "RENT"
            
            # Try multiple sources for text content
            full_t = ""
            
            # Source 1: Pre-joined content
            if ocr_res.get('content'):
                full_t = ocr_res['content']
                print(f"DEBUG: Got content from ocr_res['content'], length: {len(full_t)}")
            
            # Source 2: Manual reconstruction from pages
            if not full_t and 'pages' in ocr_res:
                for p in ocr_res['pages'][:3]:  # Check first 3 pages
                    # Try lines first
                    if 'lines' in p:
                        for l in p.get('lines', []):
                            full_t += l.get('text', '') + " "
                    # Fallback to words
                    elif 'words' in p:
                        for w in p.get('words', []):
                            full_t += w.get('content', '') + " "
                if full_t:
                    print(f"DEBUG: Reconstructed text from pages, length: {len(full_t)}")
            
            if not full_t:
                print("DEBUG: No text content found - defaulting to RENT")
                return "RENT"
            
            # Show first 200 chars for debugging
            print(f"DEBUG: Text sample: {full_t[:200]}")
            
            # AGGRESSIVE keyword search - check for ANY Labor-related term
            labor_keywords = [
                r'근\s*로',  # 근로 (Labor)
                r'Labor',
                r'Employee',
                r'Employer',
                r'Standard\s*Labor',
                r'고\s*용',  # 고용 (Employment)
                r'Standard\s*Contract',
                r'사\s*용\s*자.*근\s*로\s*자',  # Employer...Employee pattern
            ]
            
            for keyword in labor_keywords:
                if re.search(keyword, full_t, re.IGNORECASE):
                    print(f"DEBUG: LABOR keyword matched: {keyword}")
                    return "LABOR"
            
            print("DEBUG: No labor keywords found - defaulting to RENT")
            return "RENT"

        primary_type = classify_doc_type(ctx.get('contract_ocr'))
        print(f"DEBUG: FINAL Document Type: {primary_type}")
        
        # Process Contract
        ctx['contract_pii'] = process_doc(ctx.get('contract_ocr'), primary_type, contract_addr)
        
        # Process Registry (Always REGISTRY type)
        ctx['registry_pii'] = process_doc(ctx.get('registry_ocr'), "REGISTRY", contract_addr)

    step_pii.stage_id = Stage.PII_MASKING

    # 6-1. Toxic Clause Detection (LLM + RAG)
    async def step_toxic_clauses(ctx):
        from app.services.rag import RAGService
        from app.services.llm import LLMService
        from app.schemas.analysis import RuleResult, RuleEvidence
        from app.core.config import settings
        import asyncio
        import functools
        import time
        
        start_time = time.time()
        mode_str = "Parallel" if settings.USE_PARALLEL_PROCESSING else "Sequential"
        
        llm = LLMService()
        rag = RAGService()
        full_text = ctx.get('contract_text', '')
        
        print("--- Scanning for Toxic Clauses ---")
        # 1. Scan Candidates
        candidates = llm.detect_toxic_candidates(full_text, doc_type="CONTRACT")
        
        if not candidates:
            print("No toxic candidates found.")
            return

        # Parallel Processing
        if settings.USE_PARALLEL_PROCESSING:
            print(f"🚀 [{mode_str} Mode] Processing Toxic Clauses (Lease)... Candidates: {len(candidates)}")
            
            sem = asyncio.Semaphore(settings.MAX_CONCURRENT_TASKS)
            import random

            async def process_candidate(cand):
                async with sem:
                    # Jitter
                    await asyncio.sleep(random.uniform(0.1, 0.3))
                    
                    retries = 5
                    last_err = None
                    
                    for attempt in range(retries):
                        try:
                            c_text = cand.get('original_text', '')
                            r_type = cand.get('risk_type', 'UNFAIR')
                            query = f"{c_text} 위법성 불공정 판례"
                            
                            # RAG Search in Thread
                            f_search_laws = functools.partial(rag.search_category, "laws", query)
                            f_search_cases = functools.partial(rag.search_category, "cases", query)
                            
                            docs = []
                            if r_type == 'ILLEGAL':
                                docs = await asyncio.to_thread(f_search_laws)
                            else:
                                docs = await asyncio.to_thread(f_search_cases)
                                
                            context_str = "\n".join(docs)
                            
                            # LLM Verify in Thread
                            f_verify = functools.partial(llm.verify_toxic_clause, cand, context_str)
                            verified = await asyncio.to_thread(f_verify)
                            
                            if verified.get('error'):
                                raise Exception(f"LLM Verification Error: {verified['error']}")
                            
                            return cand, verified
                        except Exception as e:
                            last_err = e
                            wait_time = (attempt + 1) * 0.5
                            if attempt < retries - 1:
                                await asyncio.sleep(wait_time)
                            else:
                                logger.error(f"Parallel Candidate Failed after {retries} tries: {e}")
                                return None
                    return None

            tasks = [process_candidate(c) for c in candidates]
            results = await asyncio.gather(*tasks)
            
            for res in results:
                if not res: continue
                cand, verified = res
                
                if verified.get('is_toxic'):
                    c_text = cand.get('original_text', '')
                    rule_res = RuleResult(
                        rule_id="TOXIC_TERM",
                        status="FAIL",
                        severity="HIGH",
                        title="[독소조항 의심]",
                        evidence=RuleEvidence(
                            detail=f"조항: '{c_text}'\n근거: {verified.get('legal_basis')}"
                        )
                    )
                    if 'rule_results' not in ctx: ctx['rule_results'] = []
                    ctx['rule_results'].append(rule_res)
                    print(f"Toxic Clause Verified: {c_text[:20]}...")
        else:
            # Sequential Legacy
            print(f"🐢 [{mode_str} Mode] Processing Toxic Clauses (Lease)...")
            for cand in candidates:
                # 2. Targeted RAG Retrieval
                c_text = cand.get('original_text', '')
                r_type = cand.get('risk_type', 'UNFAIR')
                query = f"{c_text} 위법성 불공정 판례"
                
                try:
                    evidence_docs = []
                    if r_type == 'ILLEGAL':
                        evidence_docs = rag.search_category("laws", query)
                    else:
                        evidence_docs = rag.search_category("cases", query) 
                except Exception as e:
                    logger.warning(f"RAG Search Error (Sequential): {e}")
                    evidence_docs = [] 
                    
                context_str = "\n".join(evidence_docs)
                
                # 3. Verify with Evidence
                verified = llm.verify_toxic_clause(cand, context_str)
                
                if verified.get('is_toxic'):
                    # 4. Add to Rules
                    rule_res = RuleResult(
                        rule_id="TOXIC_TERM",
                        status="FAIL",
                        severity="HIGH",
                        title="[독소조항 의심]",
                        evidence=RuleEvidence(
                            detail=f"조항: '{c_text}'\n근거: {verified.get('legal_basis')}"
                        )
                    )
                    if 'rule_results' not in ctx:
                        ctx['rule_results'] = []
                        
                    ctx['rule_results'].append(rule_res)
                    print(f"Toxic Clause Verified: {c_text[:20]}...")
                else:
                    print(f"Toxic Candidate Dismissed: {c_text[:20]}...")

        elapsed = time.time() - start_time
        print(f"⏱️ [Toxic Clause Check] Time Elapsed: {elapsed:.2f} seconds ({mode_str} Mode)")

    step_toxic_clauses.stage_id = Stage.RULE_ENGINE

    # 8. RAG & LLM
    async def step_ai(ctx):
        try:
            rag = RAGService()
            llm = LLMService()
            from app.core.config import settings
            import asyncio
            import functools
            import time
            
            start_time = time.time()
            mode_str = "Parallel" if settings.USE_PARALLEL_PROCESSING else "Sequential"
            
            rag_results = []
            
            # 1. Collect RAG context for Global Summary
            if not ctx['rule_results']:
                 rag_results.extend(rag.search_category("laws", "임대차 계약 주의사항"))
            
            failed_rules = [r for r in ctx['rule_results'] if r.status == 'FAIL']
            
            if settings.USE_PARALLEL_PROCESSING:
                print(f"🚀 [{mode_str} Mode] Gathering RAG (Lease)...")
                
                sem = asyncio.Semaphore(settings.MAX_CONCURRENT_TASKS)

                async def fetch_context(r):
                    async with sem:
                        search_query = r.title + " " + r.evidence.detail
                        docs = []
                        
                        # Original Routing Logic
                        # We can't easily parallelize the internal routing logic of search_all inside a loop without refactoring
                        # But we can run the whole block in a thread
                        
                        def run_search():
                            local_docs = []
                            if r.rule_id == "RIGHTS": 
                                local_docs.extend(rag.search_category("laws", "울구 선순위 근저당 권리 분석"))
                                local_docs.extend(rag.search_category("cases", "선순위 근저당 전세금 미반환 사례"))
                            elif r.rule_id == "ADDR" or r.rule_id == "OWNER":
                                local_docs.extend(rag.search_category("laws", "임대차 계약 당사자 확인 및 대항력"))
                            elif r.rule_id == "USAGE":
                                local_docs.extend(rag.search_category("laws", "불법건축물 전세자금대출 위반건축물"))
                                local_docs.extend(rag.search_category("cases", "위반건축물 임대차 계약 분쟁"))
                            elif r.rule_id == "PRICE":
                                 local_docs.extend(rag.search_category("cases", "깡통전세 예방 보증보험"))
                            else:
                                local_docs.extend(rag.search_all(search_query))
                            return local_docs

                        return await asyncio.to_thread(run_search)
                
                tasks = [fetch_context(r) for r in failed_rules]
                results = await asyncio.gather(*tasks)
                for res in results:
                    rag_results.extend(res)
            else:
                print(f"🐢 [{mode_str} Mode] Gathering RAG (Lease)...")
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
            m_data = ctx.get('market_price', {})
            if isinstance(m_data, dict):
                m_price = m_data.get('price', '정보 없음')
                m_source = m_data.get('source', '출처 미상')
                m_region = m_data.get('region', '')
                market_context = f"\n[주변 시세 정보]\n지역: {m_region}\n전세 평균: {m_price}\n(출처: {m_source})"
            else:
                market_context = f"\n[주변 시세 정보]\n해당 지역({ctx['contract_obj'].address}) 전세 평균: {str(m_data)}"
            
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
                    advice_json_str = await asyncio.to_thread(
                        lambda: llm.client.chat.completions.create(
                            model=settings.AZURE_OPENAI_DEPLOYMENT_NAME, # Use correct deployment
                            messages=[
                                {"role": "system", "content": "당신은 부동산 법률 전문가입니다. JSON만 출력하세요."},
                                {"role": "user", "content": itemized_prompt}
                            ]
                        ).choices[0].message.content
                    )
                    
                    import json
                    # Naive cleanup
                    advice_json_str = advice_json_str.strip()
                    if "```json" in advice_json_str:
                        advice_json_str = advice_json_str.split("```json")[1].split("```")[0]
                    elif "```" in advice_json_str:
                        advice_json_str = advice_json_str.split("```")[1].split("```")[0]
                    
                    advice_list = json.loads(advice_json_str)
                    
                    # Map back to rules
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
            ctx['summary_text'] = await asyncio.to_thread(
                llm.generate_explanation, ctx['rule_results'], rag_results, doc_type="CONTRACT"
            )
            
            elapsed = time.time() - start_time
            print(f"⏱️ [AI Analysis] Time Elapsed: {elapsed:.2f} seconds ({mode_str} Mode)")
            
        except Exception as e:
            # Expose error detail to Frontend for debugging
            import traceback
            logger.error(traceback.format_exc())
            raise AnalysisException(Stage.LLM_GENERATE, "LLM_DEBUG_ERROR", f"AI 단계 오류: {str(e)}")

    # 8-1. Dynamic Translation Step
    async def step_dynamic_translate(ctx):
        target_lang = ctx.get('target_language', 'ko')
        print(f"DEBUG: step_dynamic_translate called with target_lang='{target_lang}'")
        
        # Skip if Korean or Default
        if target_lang == 'ko':
            print("DEBUG: Skipping translation because target_lang is 'ko'")
            return

        print(f"--- Translating Report to {target_lang} ---")
        llm = LLMService()
        
        # Get Current Rules (Failures mostly)
        failed_rules = [r for r in ctx['rule_results'] if r.status == 'FAIL']
        print(f"DEBUG: Found {len(failed_rules)} failed rules to translate.")
        
        if not failed_rules and not ctx.get('summary_text'):
            return

        # Call LLM
        translated_data = llm.translate_analysis_result(
            ctx.get('summary_text', ''),
            failed_rules,
            target_lang
        )
        
        # Apply Translation to Context
        if translated_data.get('translated_summary'):
             val = translated_data['translated_summary']
             if isinstance(val, (dict, list)):
                 try:
                     if isinstance(val, dict):
                         sorted_keys = sorted(val.keys())
                         parts = [str(val[k]) for k in sorted_keys]
                         ctx['summary_text'] = "\n\n".join(parts)
                     else:
                         ctx['summary_text'] = "\n\n".join([str(v) for v in val])
                 except:
                     import json
                     ctx['summary_text'] = json.dumps(val, ensure_ascii=False)
             else:
                 ctx['summary_text'] = str(val)
            
        # Map back rules
        t_rules = translated_data.get('translated_rules', [])
        
        for item in t_rules:
            try:
                # item['id'] should correspond to 1-based index in failed_rules
                idx = int(item['id']) - 1
                if 0 <= idx < len(failed_rules):
                    rule = failed_rules[idx]
                    rule.title = item.get('title', rule.title)
                    if rule.ai_advice:
                        rule.ai_advice.legal_review = item.get('legal_review', rule.ai_advice.legal_review)
                        rule.ai_advice.action_guide = item.get('action_guide', rule.ai_advice.action_guide) 
            except:
                continue

    step_dynamic_translate.stage_id = Stage.LLM_GENERATE

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
                    # FIX: Prevent partial matches on addresses (e.g. matching "Seoul" + "19" when target is "Seoul" + "724")
                    # Require substantial numeric overlap if target has multiple numbers.
                    if not target_nums.isdisjoint(line_nums):
                         overlap_nums = target_nums.intersection(line_nums)
                         # If target has many numbers (e.g. 724-18, 201), we expect more than just 1 unless it's unique
                         
                         overlap_specific = target_texts_specific.intersection(line_texts_specific)
                         
                         # Check strictness
                         if len(overlap_nums) >= 2:
                             # Strong numeric match (e.g. 724 and 18)
                             if len(overlap_specific) >= 1:
                                 is_match = True
                                 
                         elif len(overlap_nums) == 1:
                             # Only 1 matching number.
                             # It must be a specific/rare number (longer is better)
                             matched_num = list(overlap_nums)[0]
                             if len(matched_num) >= 3: 
                                 # 3+ digits (e.g. 724, 201) -> Valid if context matches
                                 if len(overlap_specific) >= 2: # Need 2 text tokens (e.g. Seoul, Dong)
                                     is_match = True
                             else:
                                 # Short number (e.g. 18, 1, 2) -> Very risky. Require HIGH context.
                                 if len(overlap_specific) >= 3:
                                     is_match = True
                        
                    # 2. Strong Text Match (Context Only)
                    elif len(target_texts_specific.intersection(line_texts_specific)) >= 3:
                         # Relaxed from 2 to 3 to avoid "Seoul Seodaemun-gu" matching everything
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
        
        # Save Files to Azure Blob
        blob_service = BlobStorageService()
        
        c_filename = f"{uuid.uuid4()}_contract.pdf"
        file_url = blob_service.upload_file(c_pdf_bytes, c_filename)
            
        r_filename = f"{uuid.uuid4()}_registry.pdf" # Force .pdf extension
        registry_url = blob_service.upload_file(r_pdf_bytes, r_filename)

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
                "highest_severity": "HIGH",
                "language": ctx.get('target_language', 'ko'),
                "service_type": "rent"
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
    response = await runner.execute([
        step_validate,
        step_ocr,
        step_classify,
        step_normalize,
        step_market, # Price Info needed for Rules
        step_rules,
        step_toxic_clauses,
        step_pii,
        step_ai,
        step_dynamic_translate,
        step_result
    ])

    if response.success and response.data:
        try:
             res_data = response.data
             if hasattr(res_data, 'model_dump'):
                 res_dict = res_data.model_dump()
             elif hasattr(res_data, 'dict'):
                 res_dict = res_data.dict()
             else:
                 res_dict = res_data
             
             if await request.is_disconnected():
                 logger.info("Request cancelled. Skipping history save.")
             else:
                 history_service.create_analysis(db, current_user.id, res_dict)
        except Exception as e:
             logger.error(f"Failed to save history: {e}")

    return response

@router.post("/analyze/labor", response_model=BaseResponse)
async def analyze_labor_documents(
    request: Request,
    contract_file: UploadFile = File(...),
    target_language: str = Form("ko"),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    runner = PipelineRunner()
    runner.context['request'] = request
    
    # 1. Validation
    async def step_validate(ctx):
        c_content = await contract_file.read()
        FileValidator.validate(c_content, contract_file.filename, contract_file.content_type)
        
        from app.core.config import settings
        from app.utils.image_opt import optimize_image_bytes
        
        if settings.USE_IMAGE_OPTIMIZATION:
             print("🖼️ Optimizing Labor Contract Image...")
             c_content = optimize_image_bytes(c_content)

        ctx['contract_bytes'] = c_content
        ctx['target_language'] = target_language
    
    step_validate.stage_id = Stage.FILE_VALIDATE

    # 2. OCR
    async def step_ocr(ctx):
        ocr = OCRService()
        ctx['contract_ocr'] = ocr.extract(ctx['contract_bytes'], contract_file.content_type)
        ctx['contract_text'] = ctx['contract_ocr'].get('content', '')
    
    step_ocr.stage_id = Stage.OCR

    # 3. Classify (Optional: Check if it's Labor Contract)
    # 3. Classify (Strict Check for Labor Contract)
    async def step_classify(ctx):
        text = ctx['contract_text']
        c_type = DocTypeClassifier.classify(text)
        
        if c_type != 'labor_contract':
             # If strictly wrong (e.g. lease contract), raise error
             if c_type in ['lease_contract', 'registry']:
                 raise AnalysisException(Stage.DOC_TYPE_DETECT, "INVALID_DOC_TYPE", "업로드된 문서가 근로계약서가 아닙니다.", {"detected": c_type})
             
             # If just unknown but text has labor keywords, allow flexibility or generic pass
             # But DocTypeClassifier throws exception if undetermined.
             # So if we are here, it matches one of the known types.
             pass
            
    step_classify.stage_id = Stage.DOC_TYPE_DETECT

    # 4. Normalize
    async def step_normalize(ctx):
        from app.services.llm import LLMService
        from app.schemas.documents import LaborContract
        import json
        
        llm = LLMService()
        text = ctx.get('contract_text', '')
        
        try:
            # We reuse extract_data_from_text but with LABOR intent
            # Note: extract_data_from_text implementation needs to support new prompt type or we use custom prompt here.
            # Assuming LLMService can handle generic or we add logic later. 
            # For now, let's use a direct prompt call or if extract_data_from_text supports it.
            # Since LLMService.extract_data_from_text is hardcoded for CONTRACT/REGISTRY prompts, let's hack it or modify LLMService later.
            # For minimal impact, I'll inline the extraction call here or assume we updated LLMService.
            # Updating LLMService is cleaner. USE "LABOR" type.
            
            json_str = llm.extract_data_from_text(text, "LABOR") 
            data = json.loads(json_str)
            
            # Numeric cleanup for Salary
            if 'salary' in data:
                 try:
                    val = str(data['salary']).replace(',', '').replace('원', '')
                    data['salary'] = int(val)
                 except: result = 0
            
            ctx['contract_obj'] = LaborContract(**data)
            
        except Exception as e:
            logger.error(f"Labor Extraction Failed: {e}")
            ctx['contract_obj'] = LaborContract(
                employer_name="Unknown", employee_name="Unknown", 
                start_date="", salary=0, work_hours="Unknown"
            )

    step_normalize.stage_id = Stage.SCHEMA_NORMALIZE

    # 4-2. PII Masking (Added)
    async def step_pii(ctx):
        from app.services.pii import PiiService
        import re
        
        pii_service = PiiService()

        def process_doc(ocr_result, known_values=None):
            if not ocr_result: return []
            
            # 1. Linearize
            full_text = ""
            text_map = [] 
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
            
            if not full_text.strip(): return []

            # 2. Azure PII (WITH CORRECT DOC_TYPE)
            entities = pii_service.detect_pii(full_text, doc_type="LABOR")
            
            # 3. Known Values (Rules-based)
            if known_values:
                for val in known_values:
                    if not val or len(val) < 2: continue
                    val_chars = list(val)
                    escaped_chars = [re.escape(c) for c in val_chars if c.strip()]
                    if not escaped_chars: continue
                    pattern_str = r"\s*".join(escaped_chars)
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
                    except: continue

            boxes = pii_service.map_pii_to_boxes(entities, pages, text_map)

            # 4. Refinement
            final_boxes = []
            print(f"DEBUG ANALYSIS: Filtering {len(boxes)} boxes by category...")
            for b in boxes:
                category = b.get('category')
                # Mask RRN, Phone, Names, DateTime (birthdates), and Addresses
                # IMPORTANT: For Labor contracts, we also need DateTime (birthdate) and Address (home/location addresses)
                # NOTE: Organization is excluded - company names are public information
                if category in ['Person', 'resident_registration_number', 'PhoneNumber', 'Email', 'HybridFallback', 'DateTime', 'Address']:
                    
                    # Partial Masking for Names
                    is_person = category in ['Person', 'HybridFallback']
                    if is_person and len(b['text']) >= 2:
                         x1, y1, x2, y2 = b['box_norm']
                         width = x2 - x1
                         char_w = width / len(b['text'])
                         # Mask from 2nd char
                         mask_x1 = x1 + (char_w * 0.9) 
                         if mask_x1 < x2:
                            b['box_norm'] = [mask_x1, y1, x2, y2]
                    
                    final_boxes.append(b)
                else:
                    print(f"DEBUG ANALYSIS: FILTERING OUT category={category}: '{b['text'][:40]}...'")
            
            print(f"DEBUG ANALYSIS: Final boxes count: {len(final_boxes)} (filtered from {len(boxes)})")
            return final_boxes

        # Gather Known PII from Object
        c_obj = ctx.get('contract_obj')
        known = []
        if c_obj:
            if c_obj.employer_name: known.append(c_obj.employer_name)
            if c_obj.employee_name: known.append(c_obj.employee_name)
        
        ctx['contract_pii'] = process_doc(ctx.get('contract_ocr'), known_values=known)

    step_pii.stage_id = Stage.PII_MASKING

    # 5. Rules
    async def step_rules(ctx):
        from app.services.labor_rules import LaborRuleEngine
        ctx['rule_results'] = LaborRuleEngine.run(ctx['contract_obj'])
        
    step_rules.stage_id = Stage.RULE_ENGINE

    # 5-1. Active Toxic Clause Scanner (New for Labor)
    # 5-1. Active Toxic Clause Scanner (New for Labor)
    # 5-1. Active Toxic Clause Scanner (New for Labor)
    async def step_toxic_clauses(ctx):
        from app.services.rag import RAGService
        from app.services.llm import LLMService
        from app.schemas.analysis import RuleResult, RuleEvidence
        from app.core.config import settings
        import asyncio
        import functools
        import time
        
        start_time = time.time()
        mode_str = "Parallel" if settings.USE_PARALLEL_PROCESSING else "Sequential"
        
        llm = LLMService()
        rag = RAGService()
        full_text = ctx.get('contract_text', '')
        
        # 1. Scan Candidates (Labor Mode)
        candidates = llm.detect_toxic_candidates(full_text, doc_type="LABOR")
        
        if not candidates:
            return

        # Parallel Processing Logic
        if settings.USE_PARALLEL_PROCESSING:
            print(f"🚀 [{mode_str} Mode] Processing Toxic Clauses... Candidates: {len(candidates)}")
            
            import random
            sem = asyncio.Semaphore(settings.MAX_CONCURRENT_TASKS)
            
            async def process_candidate(cand):
                async with sem:
                    # Jitter
                    await asyncio.sleep(random.uniform(0.1, 0.3))
                    
                    retries = 5
                    last_err = None
                    
                    for attempt in range(retries):
                        try:
                            c_text = cand.get('original_text', '')
                            query = f"{c_text} 노동법 위반 판례"
                            
                            # Run RAG in Thread (Blocking IO)
                            # Search both laws and cases
                            f_rag = functools.partial(rag.search_category, "labor_laws", query)
                            raw_docs = await asyncio.to_thread(f_rag)
                            
                            f_rag2 = functools.partial(rag.search_category, "labor_cases", query)
                            raw_docs2 = await asyncio.to_thread(f_rag2)
                            raw_docs.extend(raw_docs2)
                            
                            context_str = "\n".join(raw_docs)
                            
                            # Run LLM Verify in Thread (Blocking IO)
                            f_verify = functools.partial(llm.verify_toxic_clause, cand, context_str)
                            verified = await asyncio.to_thread(f_verify)
                            
                            if verified.get('error'):
                                raise Exception(f"LLM Verification Error: {verified['error']}")
                            
                            return cand, verified
                        except Exception as e:
                            last_err = e
                            wait_time = (attempt + 1) * 0.5
                            if attempt < retries - 1:
                                await asyncio.sleep(wait_time)
                            else:
                                logger.error(f"Parallel Candidate Failed after {retries} tries: {e}")
                                return None
                    return None

            # Gather all tasks
            tasks = [process_candidate(c) for c in candidates]
            results = await asyncio.gather(*tasks)
            
            # Process results
            for res in results:
                if not res: continue
                cand, verified = res
                
                if verified.get('is_toxic'):
                    c_text = cand.get('original_text', '')
                    # Dedup Check
                    existing = [r.evidence.detail for r in ctx.get('rule_results', []) if r.evidence]
                    if any(c_text in e for e in existing): continue

                    rule_res = RuleResult(
                        rule_id="TOXIC_LABOR",
                        status="FAIL",
                        severity="HIGH",
                        title="[불공정 조항 감지]",
                        evidence=RuleEvidence(
                            detail=f"조항: '{c_text}'\n근거: {verified.get('legal_basis')}"
                        )
                    )
                    if 'rule_results' not in ctx: ctx['rule_results'] = []
                    ctx['rule_results'].append(rule_res)
        
        else:
            # Legacy Sequential Logic
            print(f"🐢 [{mode_str} Mode] Processing Toxic Clauses... Candidates: {len(candidates)}")
            for cand in candidates:
                # 2. Targeted RAG Retrieval (Labor Scope)
                c_text = cand.get('original_text', '')
                query = f"{c_text} 노동법 위반 판례"
                
                try:
                    # Run RAG (Blocking IO)
                    raw_docs = rag.search_category("labor_laws", query)
                    raw_docs2 = rag.search_category("labor_cases", query)
                    raw_docs.extend(raw_docs2)
                    
                    context_str = "\n".join(raw_docs)
                except Exception as e:
                     logger.warning(f"RAG Search Error (Sequential): {e}")
                     context_str = ""
                
                # 3. Verify with Evidence
                verified = llm.verify_toxic_clause(cand, context_str)
                
                if verified.get('is_toxic'):
                    # 4. Add to Rules
                    # Only add if not duplicate (simple check)
                    existing = [r.evidence.detail for r in ctx.get('rule_results', []) if r.evidence]
                    if any(c_text in e for e in existing): continue

                    rule_res = RuleResult(
                        rule_id="TOXIC_LABOR",
                        status="FAIL",
                        severity="HIGH",
                        title="[불공정 조항 감지]",
                        evidence=RuleEvidence(
                            detail=f"조항: '{c_text}'\n근거: {verified.get('legal_basis')}"
                        )
                    )
                    if 'rule_results' not in ctx:
                        ctx['rule_results'] = []
                        
                    ctx['rule_results'].append(rule_res)

        elapsed = time.time() - start_time
        print(f"⏱️ [Toxic Clause Check] Time Elapsed: {elapsed:.2f} seconds ({mode_str} Mode)")

    step_toxic_clauses.stage_id = Stage.RULE_ENGINE

    # 6. RAG & Check
    async def step_ai(ctx):
        rag = RAGService()
        llm = LLMService()
        from app.core.config import settings
        import asyncio
        import functools
        import time
        
        start_time = time.time()
        mode_str = "Parallel" if settings.USE_PARALLEL_PROCESSING else "Sequential"

        rag_results = []
        
        # General Labor Laws
        rag_results.extend(rag.search_category("labor_laws", "근로기준법 핵심 준수사항"))
        
        failed_rules = [r for r in ctx['rule_results'] if r.status == 'FAIL']
        
        # Parallel RAG Context Gathering
        if settings.USE_PARALLEL_PROCESSING:
            print(f"🚀 [{mode_str} Mode] Gathering RAG Context...")
            
            sem = asyncio.Semaphore(settings.MAX_CONCURRENT_TASKS)

            async def fetch_context(r):
                async with sem:
                    query = f"{r.title} {r.evidence.detail}"
                    f_laws = functools.partial(rag.search_category, "labor_laws", query)
                    f_cases = functools.partial(rag.search_category, "labor_cases", query)
                    
                    docs = await asyncio.gather(
                        asyncio.to_thread(f_laws),
                        asyncio.to_thread(f_cases)
                    )
                    return docs[0] + docs[1]

            tasks = [fetch_context(r) for r in failed_rules]
            results = await asyncio.gather(*tasks)
            for res in results:
                rag_results.extend(res)
        else:
            print(f"🐢 [{mode_str} Mode] Gathering RAG Context...")
            for r in failed_rules:
                query = f"{r.title} {r.evidence.detail}"
                rag_results.extend(rag.search_category("labor_laws", query))
                rag_results.extend(rag.search_category("labor_cases", query))
            
        rag_results = list(set(rag_results))
        
        # 2. Per-Rule Detailed Advice (Itemized for Labor)
        if failed_rules:
            from app.schemas.analysis import AIAdvice
            import json
            
            # Context Fallback
            rag_context = str(rag_results[:3]) if rag_results else "근로기준법 및 통상적인 노동 판례"

            itemized_prompt = "다음은 근로계약서 분석에서 발견된 위험 항목들입니다. 각 항목에 대해 '법률적 검토(legal_review)'와 '행동 가이드(action_guide)'를 JSON으로 작성하세요.\n"
            itemized_prompt += "**필수 사항: 내용은 무조건 1~2문장으로 아주 간결하고 명확하게 요약하세요. 긴 설명은 금지입니다.**\n"
            
            for idx, r in enumerate(failed_rules):
                itemized_prompt += f"{idx+1}. {r.title}: {r.evidence.detail}\n"
            
            itemized_prompt += f"\n참고 법령/판례:\n{rag_context}\n"
            itemized_prompt += """
            JSON Format:
            [{"legal_review": "핵심만 간결하게(50자 내외)", "action_guide": "구체적 행동 1줄(50자 내외)"}, ...]
            """
            
            try:
                # LLM Call is fundamentally synchronous in this codebase (AzureOpenAI client),
                # so we wrap it for safety, though it's one big call anyway for advice.
                # If we had per-item advice calls, parallelizing would save time.
                # Here it is one bulk call, so parallel gain is minimal for this specific step unless we split it.
                # For now, we keep it as is or wrap in thread to not block other pipeline steps if any (none here).
                
                advice_json_str = await asyncio.to_thread(
                    lambda: llm.client.chat.completions.create(
                        model=settings.AZURE_OPENAI_DEPLOYMENT_NAME,
                        messages=[
                            {"role": "system", "content": "당신은 노무사(Labor Attorney)입니다. 근로자를 위한 법률 조언을 JSON으로 출력하세요."},
                            {"role": "user", "content": itemized_prompt}
                        ],
                        temperature=0.7
                    ).choices[0].message.content
                )
                
                advice_json_str = advice_json_str.strip()
                if "```json" in advice_json_str:
                    advice_json_str = advice_json_str.split("```json")[1].split("```")[0]
                elif "```" in advice_json_str:
                    advice_json_str = advice_json_str.split("```")[1].split("```")[0]
                
                advice_list = json.loads(advice_json_str)
                
                for i, r in enumerate(failed_rules):
                    review = "상세 법률 검토가 지연되었습니다."
                    guide = "노무사 등 전문가와 상의하세요."
                    
                    if i < len(advice_list):
                        review = advice_list[i].get("legal_review", review)
                        guide = advice_list[i].get("action_guide", guide)
                    
                    # Safety Filter for Hallucinated Error Messages
                    if "불러오지 못" in review or "오류" in review:
                        review = "관련 법령을 특정할 수 없으나, 통상적인 근로기준법 위반 소지가 있어 주의가 필요합니다."
                        
                    r.ai_advice = AIAdvice(legal_review=review, action_guide=guide)

            except Exception as e:
                logger.warning(f"Labor Advice Gen Failed: {e}")
                for r in failed_rules:
                    r.ai_advice = AIAdvice(legal_review="AI 분석 지연 (서버 과부하 등)", action_guide="전문가와 상의하세요.")
        
        # Summary
        # Wrap summary generation too
        ctx['summary_text'] = await asyncio.to_thread(
             llm.generate_explanation, ctx['rule_results'], rag_results, doc_type="LABOR"
        )
        
        elapsed = time.time() - start_time
        print(f"⏱️ [AI Advice Generation] Time Elapsed: {elapsed:.2f} seconds ({mode_str} Mode)")

    step_ai.stage_id = Stage.LLM_GENERATE

    # 7. Translation (Reuse existing logic)
    async def step_translate(ctx):
        target_lang = ctx.get('target_language', 'ko')
        if target_lang == 'ko': return
        
        # Debug Logging to File
        with open("debug_translation.txt", "a", encoding="utf-8") as f:
            f.write(f"\n--- New Request ---\nDEBUG[step_translate] Target Lang: {target_lang}\n")
        
        llm = LLMService()
        failed = [r for r in ctx['rule_results'] if r.status == 'FAIL']
        
        # Ensure Summary exists
        summary_text = ctx.get('summary_text', '')
        with open("debug_translation.txt", "a", encoding="utf-8") as f:
            f.write(f"DEBUG[step_translate] Summary Len: {len(summary_text)}, Failed Rules: {len(failed)}\n")
        
        if not summary_text and not failed:
             with open("debug_translation.txt", "a", encoding="utf-8") as f:
                 f.write("DEBUG[step_translate] Nothing to translate.\n")
             return

        trans = llm.translate_analysis_result(summary_text, failed, target_lang)
        
        if trans.get('translated_summary'):
             val = trans['translated_summary']
             if isinstance(val, (dict, list)):
                 # Flatten to clean strings
                 try:
                     if isinstance(val, dict):
                         # Sort by key if possible to maintain order 1, 2, 3...
                         sorted_keys = sorted(val.keys())
                         parts = [str(val[k]) for k in sorted_keys]
                         ctx['summary_text'] = "\n\n".join(parts)
                     else:
                         # List
                         ctx['summary_text'] = "\n\n".join([str(v) for v in val])
                 except:
                     import json
                     ctx['summary_text'] = json.dumps(val, ensure_ascii=False)
             else:
                 ctx['summary_text'] = str(val)
        
        # Update rules
        t_rules = trans.get('translated_rules', [])
        for item in t_rules:
            try:
                # item['id'] corresponds to 1-based index in failed_rules list
                idx = int(item['id']) - 1
                if 0 <= idx < len(failed):
                    rule = failed[idx]
                    rule.title = item.get('title', rule.title)
                    if rule.evidence and item.get('evidence'):
                         rule.evidence.detail = item.get('evidence')
                    if rule.ai_advice:
                        rule.ai_advice.legal_review = item.get('legal_review', rule.ai_advice.legal_review)
                        rule.ai_advice.action_guide = item.get('action_guide', rule.ai_advice.action_guide)
            except Exception:
                continue

    step_translate.stage_id = Stage.LLM_GENERATE

    # 8. Result
    async def step_result(ctx):
        from app.services.visualizer import VisualizerService
        import os
        import uuid
        import re

        # -- Boxing Helper (Simplified copy) --
        def map_risk_to_box(ocr_result, evidence_detail):
            if not evidence_detail or not ocr_result: return []
            
            # --- Improved Keyword Extraction Strategy ---
            # 1. Extract 'Quoted' text (High Priority)
            quoted_keywords = re.findall(r"'(.*?)'", evidence_detail)
            
            # 2. Extract Numbers (e.g. 2,050,000)
            # Remove amounts from evidence to avoid double matching if desired, but here we add them.
            # Match 2+ digits, optionally with commas
            number_matches = re.findall(r'\b\d{1,3}(?:,\d{3})*(?:\.\d+)?\b', evidence_detail)
            # Filter solely numeric strings (remove empty) and normalize (remove commas) to act as search keys
            # STRICT: Only match numbers with 4+ digits (e.g. 2025, 10000) to avoid matching '50' in '550101'
            target_numbers = [n.replace(",", "") for n in number_matches if len(n.replace(",", "")) > 3]
            
            # 3. Fallback: Clean words from the text
            # Split by non-word characters to avoid attaching punctuation like '급여('
            raw_tokens = re.split(r'[^\w]', evidence_detail)
            text_keywords = [t for t in raw_tokens if len(t) >= 2 and not t.isdigit()] # Keep words >= 2 chars, ignore pure numbers here
            
            # Combine all targets
            # We want to match ANY of these features in the OCR line.
            
            boxes = []
            pages = ocr_result.get('pages', [])
            
            for p_idx, page in enumerate(pages):
                p_w = page.get('width', 1)
                p_h = page.get('height', 1)
                
                for line in page.get('lines', []):
                    line_content = line.get('content', '')
                    if not line_content: continue
                    
                    is_match = False
                    
                    # A. Check Quoted Exact Match (Relaxed spaces)
                    for q in quoted_keywords:
                        if q.replace(" ", "") in line_content.replace(" ", ""):
                            is_match = True
                            break
                    if is_match: 
                        # Add box logic
                        pass
                    
                    # B. Check Numeric Match
                    if not is_match and target_numbers:
                        # Normalize line content for numbers
                        # "월 2,050,000원" -> "2050000" inside?
                        line_nums = re.findall(r'\d+', line_content)
                        # We join line numbers to see if our target number sequence exists
                        # But safer to check existence of target number string in line's numeric sequences
                        for t_num in target_numbers:
                            # Heuristic: Check if the target number (clean) appears in the line content (clean of commas)
                            if t_num in line_content.replace(",", ""):
                                is_match = True
                                break
                    
                    # C. Check Text Keyword Match
                    if not is_match and text_keywords:
                        # Require at least 2 keywords to match if no quote/number? Or just 1 specific one?
                        # Evidence often short: "근로 계약 시작일 누락" -> "근로", "계약", "시작일", "누락"
                        # Finding lines with "근로" might match too many.
                        # Using finding any 2 tokens overlap if possible.
                        
                        line_tokens = set(re.split(r'[^\w]', line_content))
                        target_set = set(text_keywords)
                        overlap = target_set.intersection(line_tokens)
                        
                        # Threshold: If quote/num absent, require 2 words OR high ratio
                        if len(overlap) >= 2:
                            is_match = True
                        elif len(overlap) == 1 and len(target_set) < 3:
                            # Short evidence, 1 match might be enough (e.g. "서명 누락" -> "서명")
                            is_match = True
                            
                    if is_match:
                        poly = line.get('polygon', [])
                        if len(poly) >= 8:
                            xs = poly[0::2]
                            ys = poly[1::2]
                            box_norm = [min(xs)/p_w, min(ys)/p_h, max(xs)/p_w, max(ys)/p_h]
                            boxes.append({"box_norm": box_norm, "page_idx": p_idx})
            
            return boxes

        # Map Risks
        c_risks = []
        failed_rules = [r for r in ctx['rule_results'] if r.status == 'FAIL']
        for idx, r in enumerate(failed_rules):
            label = str(idx + 1)
            found = map_risk_to_box(ctx.get('contract_ocr'), r.evidence.detail)
            for b in found:
                c_risks.append({"box_norm": b['box_norm'], "page_idx": b['page_idx'], "severity": r.severity, "label": label})

        # Generate Masked PDF
        c_pdf_bytes = VisualizerService.create_masked_document(
            ctx['contract_bytes'],
            ctx.get('contract_pii', []),
            c_risks
        )
        
        filename = f"{uuid.uuid4()}_labor.pdf"
        # Save to Azure Blob
        blob_service = BlobStorageService()
        file_url = blob_service.upload_file(c_pdf_bytes, filename)
        
        target_lang = ctx.get('target_language', 'ko')
        ctx['result'] = AnalysisResultResponse(
            analysis_id=str(uuid.uuid4()),
            summary={
                "risk_count": len(failed_rules),
                "highest_severity": "HIGH" if any(r.severity == 'HIGH' for r in failed_rules) else "LOW",
                "highest_severity": "HIGH" if any(r.severity == 'HIGH' for r in failed_rules) else "LOW",
                "language": target_lang,
                "service_type": "labor"
            },
            rules=ctx['rule_results'],
            documents={
                "masked_pdf_url": file_url,
                "registry_url": "" # No registry
            },
            summary_text=ctx.get('summary_text')
        )

    step_result.stage_id = Stage.RESULT_RENDER

    response = await runner.execute([
        step_validate, step_ocr, step_classify, step_normalize, 
        step_rules, step_toxic_clauses, step_pii, step_ai, step_translate, step_result
    ])

    if response.success and response.data:
        try:
             res_data = response.data
             if hasattr(res_data, 'model_dump'):
                 res_dict = res_data.model_dump()
             elif hasattr(res_data, 'dict'):
                 res_dict = res_data.dict()
             else:
                 res_dict = res_data
             
             if await request.is_disconnected():
                 logger.info("Labor Analysis Request cancelled. Skipping history save.")
             else:
                 history_service.create_analysis(db, current_user.id, res_dict)
        except Exception as e:
             logger.error(f"Failed to save history: {e}")

    return response
