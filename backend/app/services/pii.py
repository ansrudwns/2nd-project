
import logging
import re
from typing import List, Dict, Any, Tuple, Set
from app.core.config import settings
from app.core.exceptions import AnalysisException, Stage

# Azure SDK
try:
    from azure.ai.textanalytics import TextAnalyticsClient
    from azure.core.credentials import AzureKeyCredential
except ImportError as e:
    print(f"CRITICAL: Failed to import Azure SDK: {e}")
    TextAnalyticsClient = None

logger = logging.getLogger(__name__)

class PiiService:
    def __init__(self):
        self.client = None
        if settings.AZURE_LANGUAGE_KEY and settings.AZURE_LANGUAGE_ENDPOINT and TextAnalyticsClient:
            self.client = TextAnalyticsClient(
                endpoint=settings.AZURE_LANGUAGE_ENDPOINT, 
                credential=AzureKeyCredential(settings.AZURE_LANGUAGE_KEY)
            )
        else:
            logger.warning("Azure Language Service keys not found. PII masking will use fallback logic or skip.")

    def detect_pii(self, text: str, doc_type: str = "RENT", context: Dict[str, Any] = None) -> List[Dict[str, Any]]:
        """
        Main Dispatcher for PII Detection.
        Routes to specific logic based on doc_type.
        
        Args:
            text: Full text of the document.
            doc_type: 'RENT' | 'REGISTRY' | 'LABOR'
            context: Dict containing 'target_address', 'known_names', etc.
        """
        if context is None: context = {}
        target_address = context.get('target_address', "")
        
        # EXPLICIT DEBUG
        print(f"\n[PII SERVICE] detect_pii called.")
        print(f" > DocType: {doc_type}")
        print(f" > Context Keys: {list(context.keys())}")
        if 'lessor_name' in context: print(f" > Context Lessor: {context['lessor_name']}")
        if 'owner_name' in context: print(f" > Context Owner: {context['owner_name']}")
        
        logger.info(f"PII Detection Started. Type: {doc_type}, TargetAddr: {target_address}")
        
        if doc_type == "RENT":
            return self._detect_rent(text, target_address, context)
        elif doc_type == "REGISTRY":
            return self._detect_registry(text, target_address, context)
        elif doc_type == "LABOR":
            return self._detect_labor(text)
        else:
            # Fallback to generic rent logic
            return self._detect_rent(text, target_address, context)

    # =========================================================================
    # 1. RENT CONTRACT LOGIC
    # =========================================================================
    def _detect_rent(self, text: str, target_address: str, context: Dict = None) -> List[Dict[str, Any]]:
        results = []
        
        # DEBUG LOGGING
        print(f"DEBUG: Rent Detection Start. TargetAddr: {target_address}")
        
        # A. Dynamic Name Masking
        # 1. Regex Extraction
        detected_names = self._extract_names_rent(text)
        
        # 2. LLM Fallback (Critical Addition)
        if context:
            if 'lessor_name' in context and context['lessor_name']:
                # Handle comma separated
                for n in context['lessor_name'].split(','):
                    clean_n = n.strip().split('(')[0] # Remove (인) etc
                    if len(clean_n) >= 2: detected_names.add(clean_n)
            if 'lessee_name' in context and context['lessee_name']:
                for n in context['lessee_name'].split(','):
                    clean_n = n.strip().split('(')[0]
                    if len(clean_n) >= 2: detected_names.add(clean_n)
                    
        print(f"DEBUG: Extracted Rent Names (Regex+LLM): {detected_names}")
        results.extend(self._find_all_names(text, detected_names))
        
        # B. Address Logic (Strict Exclusion)
        addr_results = self._detect_addresses_strict(text, target_address)
        print(f"DEBUG: Addresses Found: {len(addr_results)}")
        results.extend(addr_results)
        
        # C. Identification Numbers (Always Mask)
        results.extend(self._detect_id_numbers(text))
        
        # D. Phone Numbers
        results.extend(self._detect_phone_numbers(text))
        
        return results

    def _extract_names_rent(self, text: str) -> Set[str]:
        names = set()
        # Look for pattern: Role + [junk] + Name 
        # Junk can be: spaces, newlines, colons, dots, (in), (signature)
        # Relaxed Regex
        role_pattern = re.compile(
            r'(임\s*대\s*인|임\s*차\s*인|대\s*리\s*인|공\s*인\s*중\s*개\s*사)'
            r'[\s:.\(\)인서명]*' # Allow junk chars
            r'([가-힣]{2,5})', 
            re.IGNORECASE
        )
        for match in role_pattern.finditer(text):
            name = match.group(2).strip()
            # full_match = match.group(0) # Debug
            
            if not self._is_safe_keyword(name):
                names.add(name)
        return names

    # =========================================================================
    # 2. REGISTRY LOGIC
    # =========================================================================
    def _detect_registry(self, text: str, target_address: str, context: Dict = None) -> List[Dict[str, Any]]:
        results = []
        
        # DEBUG LOGGING
        print(f"DEBUG: Registry Detection Start. TargetAddr: {target_address}")
        
        # A. Owner Name Masking (Dynamic)
        detected_names = self._extract_names_registry(text)
        
        # LLM Fallback (Critical Addition)
        if context:
            if 'owner_name' in context and context['owner_name']:
                # Handle comma separated
                for n in context['owner_name'].split(','):
                    clean_n = n.strip().split('(')[0]
                    if len(clean_n) >= 2: detected_names.add(clean_n)
        
        print(f"DEBUG: Extracted Registry Owner Names (Regex+LLM): {detected_names}")
        results.extend(self._find_all_names(text, detected_names))
        
        # B. Address Logic (Strict Exclusion using Robust Normalization)
        # We reuse the logic from Rent which has the robust exclusion
        addr_results = self._detect_addresses_strict(text, target_address, is_registry=True)
        results.extend(addr_results)
        
        # C. Identification Numbers (Always Mask)
        results.extend(self._detect_id_numbers(text))
        
        return results

    def _extract_names_registry(self, text: str) -> Set[str]:
        names = set()
        role_pattern = re.compile(
            r'(소\s*유\s*자|근\s*저\s*당\s*권\s*자|전\s*세\s*권\s*자|채\s*무\s*자)'
            r'[\s:.\(\)인]*'
            r'([가-힣]{2,20})', 
            re.IGNORECASE
        )
        for match in role_pattern.finditer(text):
            name = match.group(2).strip()
            if len(name) < 20 and not self._is_safe_keyword(name):
                clean_name = name.split(" ")[0]
                if 2 <= len(clean_name) <= 5:
                    names.add(clean_name)
        return names

    # =========================================================================
    # 3. LABOR CONTRACT LOGIC
    # =========================================================================
    def _detect_labor(self, text: str) -> List[Dict[str, Any]]:
        results = []
        
        print("\n=== LABOR PII DETECTION START (AZURE + CUSTOM) ===")
        
        # STEP 1: Use Azure Language Service (Primary) with Chunking
        if self.client:
            try:
                print("[AZURE] Calling Azure Language Service...")
                
                # Azure has 5120 character limit - chunk the text
                chunk_size = 5000
                chunks = []
                for i in range(0, len(text), chunk_size):
                    chunks.append(text[i:i+chunk_size])
                
                print(f"[AZURE] Text length: {len(text)}, Chunks: {len(chunks)}")
                
                for chunk_idx, chunk in enumerate(chunks):
                    try:
                        response = self.client.recognize_pii_entities(
                            documents=[{"id": str(chunk_idx), "language": "ko", "text": chunk}],
                            domain_filter="phi",
                            categories_filter=["Person", "PersonType", "PhoneNumber", "Email", 
                                             "Address", "Age", "DateTime", "Organization"]
                        )
                        
                        for doc in response:
                            if not doc.is_error:
                                for entity in doc.entities:
                                    # Skip wage amounts (numbers followed by won/month)
                                    if re.search(r'^\d{1,3}(,\d{3})*\s*(won|원)', entity.text, re.IGNORECASE):
                                        print(f"  [AZURE] Chunk {chunk_idx}: SKIPPED wage amount: {entity.text}")
                                        continue
                                    
                                    # Adjust offset for chunked text
                                    adjusted_offset = entity.offset + (chunk_idx * chunk_size)
                                    
                                    category = entity.category
                                    subcategory = entity.subcategory if hasattr(entity, 'subcategory') else None
                                    
                                    results.append({
                                        "text": entity.text,
                                        "category": category,
                                        "subcategory": subcategory,
                                        "offset": adjusted_offset,
                                        "length": entity.length,
                                        "confidence_score": entity.confidence_score
                                    })
                                    print(f"  [AZURE] Chunk {chunk_idx}: {category}/{subcategory}: {entity.text[:30]}...")
                            else:
                                print(f"[AZURE] Chunk {chunk_idx} Error: {doc.error.message}")
                    except Exception as chunk_error:
                        print(f"[AZURE] Chunk {chunk_idx} failed: {chunk_error}")
                        
                print(f"[AZURE] Total found: {len(results)} entities")
                
            except Exception as e:
                print(f"[AZURE] Failed: {e}")
                logger.error(f"Azure PII detection failed: {e}")
        else:
            print("[AZURE] Client not initialized - using fallback only")
        
        # STEP 2: Custom Regex Supplements (for Korea-specific patterns Azure might miss)
        print("\n[CUSTOM] Adding Korea-specific patterns...")
        
        # A. Foreign Names in Korean (Azure misses these)
        # Example: "무 함 마 드 아 시 프" - Azure doesn't detect Korean transliterations
        detected_names = self._extract_foreign_korean_names(text)
        name_results = self._find_all_names(text, detected_names)
        print(f"[CUSTOM] Foreign Korean Names: {len(name_results)}")
        results.extend(name_results)
        
        # B. Korean Birthdate with specific headers (생년월일, Birthdate)
        birthdate_results = self._detect_labor_sensitive(text)
        print(f"[CUSTOM] Birthdates/Addresses: {len(birthdate_results)}")
        for b in birthdate_results:
            print(f"  - {b['category']}/{b.get('subcategory')}: '{b['text'][:40]}...' (offset={b['offset']}, len={b['length']})")
        results.extend(birthdate_results)
        
        # C. Korean addresses with headers (소재지, 주소, Location)
        location_results = self._detect_labor_locations(text)
        print(f"[CUSTOM] Location Headers: {len(location_results)}")
        for loc in location_results:
            print(f"  - Address: '{loc['text'][:40]}...' (offset={loc['offset']}, len={loc['length']})")
        results.extend(location_results)
        
        # D. ID Numbers (Korean resident/business registration)
        id_results = self._detect_id_numbers(text)
        print(f"[CUSTOM] ID Numbers: {len(id_results)}")
        results.extend(id_results)
        
        print(f"\n=== TOTAL LABOR PII ENTITIES: {len(results)} ===\n")
        return results
        
    def _extract_foreign_korean_names(self, text: str) -> Set[str]:
        """
        Extract ONLY foreign names written in Korean (e.g., 무 함 마 드 아 시 프)
        Azure doesn't detect these, so we need custom logic
        Uses EXTREMELY strict filters to avoid garbage
        """
        names = set()
        
        # Pattern: Role (근로자, Employee) + Foreign Name in Korean
        role_pattern = re.compile(
            r'(근\s*로\s*자|사\s*용\s*자|Employee|Employer|성\s*명)'
            r'[\s:.()인서명]{0,5}'  # Separator
            r'([가-힣 ]{8,20})',  # ONLY Korean chars + spaces, 8-20 chars
            re.IGNORECASE
        )
        
        for match in role_pattern.finditer(text):
            name = match.group(2).strip()
            
            # VERY STRICT: Must be ONLY Korean + spaces
            if not all(c.isspace() or '가' <= c <= '힣' for c in name):
                continue
            
            # Must have at least 4 spaces (foreign names: 무 함 마 드 아 시 프 = 5 spaces)
            if name.count(' ') < 4:
                continue
            
            # CRITICAL: Skip if contains role/action words IN the name itself
            # Garbage like "근 로 자 명 의 로 된" contains "근로자", "로된"
            # IMPORTANT: Remove spaces first to match against forbidden words
            name_no_space = name.replace(' ', '')
            forbidden_in_name = ['근로', '사용', '로자', '계약', '명의', '예금', '통장', 
                                '도장', '관리', '정한', '장소', '수행', '협의', '체결',
                                '각자', '경우', '시간', '휴일', '비용', '부담', '수준']
            if any(word in name_no_space for word in forbidden_in_name):
                continue
            
            # Skip if contains particles
            particles = ['와', '은', '를', '을', '는', '의', '에', '서', '가', '한', '된']
            if any(name.endswith(p) for p in particles):
                continue
            
            # Skip if contains bad words (already checked above but double-check)
            bad_words = ['법', '협의', '장소', '업무']
            if any(word in name for word in bad_words):
                continue
            
            if len(name) >= 8:
                names.add(name)
        
        return names
        
    def _extract_names_labor(self, text: str) -> Set[str]:
        names = set()
        print("\n[DEBUG NAME EXTRACTION]")
        # "User" (사용자) / "Worker" (근로자) / "Representative" (대표자)
        # Added English headers (Name, Employer, Employee) and separator robustness
        role_pattern = re.compile(
            r'(사\s*용\s*자|근\s*로\s*자|대\s*표\s*자|성\s*명|Name|Employer|Employee)'
            r'[\s:.\(\)인서명]{0,3}' # MAX 3 chars separator
            r'([가-힣a-zA-Z \-]{2,15})', # MAX 15 chars (was 50)
            re.IGNORECASE
        )
        
        match_count = 0
        for match in role_pattern.finditer(text):
            match_count += 1
            role = match.group(1)
            name = match.group(2).strip()
            print(f"  Match {match_count}: Role='{role}' Name='{name}' (len={len(name)})")
            
            # STRICT FILTERING TO AVOID GARBAGE
            # 1. Length check (before processing)
            if len(name) < 2 or len(name) > 20:
                print(f"    ❌ Rejected: Length out of range")
                continue
            
            # 2. Skip if contains obvious noise words
            noise_words = ['또는', 'or', 'and', 'must', 'shall', 'will', 'can', 'the', 'of', 'in', 'to', 'is', 'are']
            if any(noise in name.lower() for noise in noise_words):
                print(f"    ❌ Rejected: Contains noise word")
                continue
            
            # 2.5. Skip if it's a header word itself
            if name.strip() in ['Employer', 'Employee', 'Name', 'Signature']:
                print(f"    ❌ Rejected: Is a header word")
                continue
            
            # 3. Skip if ends with punctuation (likely incomplete sentence)
            if name.endswith(('.', ',', ':', ';', '!', '?')):
                print(f"    ❌ Rejected: Ends with punctuation")
                continue
            
            # 4. Skip if excessive spaces (> 8 spaces = likely OCR garbage)
            # Increased from 4 to 8 to allow '무 함 마 드 아 시 프'
            if name.count(' ') > 8:
                print(f"    ❌ Rejected: Too many spaces ({name.count(' ')})")
                continue
            
            # 5. Skip safe keywords
            if self._is_safe_keyword(name):
                print(f"    ❌ Rejected: Safe keyword")
                continue
            
            # 5.5. Skip if it's mostly English lowercase and doesn't look like a name
            # Reject "s after arrival", "must be stated", etc.
            english_chars = sum(1 for c in name if c.islower())
            total_chars = len(name.replace(' ', ''))
            if total_chars > 0 and english_chars / total_chars > 0.7 and not name[0].isupper():
                print(f"    ❌ Rejected: Looks like English sentence fragment")
                continue
            
            # 5.6. Skip Korean names ending with particles/postpositions
            korean_particles = ['와', '은', '를', '을', '는', '의', '에', '서', '가', '에서', '를']
            if any(name.strip().endswith(p) for p in korean_particles):
                print(f"    ❌ Rejected: Ends with Korean particle")
                continue
            
            # 5.7. Skip if contains common non-name Korean words
            bad_korean_words = ['법률', '법', '계약', '협의', '비용', '부담', '수준', '자유', '경우', '시행', '규칙', '시간', '장소', '업무', '업체']
            if any(word in name for word in bad_korean_words):
                print(f"    ❌ Rejected: Contains non-name Korean word")
                continue
            
            # 5.8. Korean names should be SHORT - but allow foreign names
            # Pure Korean names (김철수): max 10 chars
            # Foreign names in Korean (무함마드 아시프): max 20 chars allowed
            korean_chars = sum(1 for c in name if '가' <= c <= '힣')
            if korean_chars > 5 and len(name) > 20:  # Increased limit
                print(f"    ❌ Rejected: Korean name too long")
                continue
                
            # 6. Clean up (remove (Signature) etc)
            clean_name = re.sub(r'[\(\)서명인]', '', name).strip()
            # Remove "Signature" English word if present
            clean_name = re.sub(r'(Signature|sign)', '', clean_name, flags=re.IGNORECASE).strip()
            
            # 7. Filter out pure headers captured by mistake
            if clean_name.replace(" ", "").lower() in ["name", "employer", "employee", "signature"]: 
                continue

            # 8. Final length check
            if 2 <= len(clean_name) <= 20:
                print(f"    ✅ ACCEPTED: '{clean_name}'")
                names.add(clean_name)
            else:
                print(f"    ❌ Rejected: Final length check failed ({len(clean_name)})")
        
        print(f"[DEBUG] Total matches found: {match_count}, Names extracted: {len(names)}\n")
        return names

    def _detect_labor_sensitive(self, text: str) -> List[Dict[str, Any]]:
        results = []
        # 1. Birthdate (Multi-format)
        # Matches: "Birthdate 1990.01.01", "생년월일 : 900101", "Date of Birth: ..."
        # IMPORTANT: Stops at next field header
        birth_pattern = re.compile(
            r'(Birthdate|Date of Birth|Birth\s*Date|생\s*년\s*월\s*일)[a-zA-Z\s]*[:.]?\s*'
            r'([0-9\s\.년월일-]{6,30}?)'  # Non-greedy
            r'(?=\s*(?:본\s*국|주\s*소|Address|성\s*명|Name|전\s*화|Phone|$))',  # Lookahead
            re.IGNORECASE
        )
        for match in birth_pattern.finditer(text):
            val = match.group(2).strip()
            if sum(c.isdigit() for c in val) < 6: continue
            
            # Mask the VALUE only
            start_idx = match.start(2)
            results.append({
                "text": val,
                "category": "DateTime",
                "subcategory": "BirthDate",
                "offset": start_idx,
                "length": len(val),
                "confidence_score": 0.95
            })
            
        # 2. Home Country Address
        # Matches "본국주소 Address House No..."
        # IMPORTANT: Stops at next field header
        addr_pattern = re.compile(
            r'(Address|Home Country Address|본\s*국\s*주\s*소|거\s*주\s*지)[a-zA-Z\s]*[:.]?\s*'
            r'([a-zA-Z0-9\s,.\-가-힣]{5,150}?)'  # Non-greedy
            r'(?=\s*(?:\([^)]*Country[^)]*\)|성\s*명|Name|전\s*화|Phone|생\s*년|Birthdate|사\s*용\s*자|근\s*로\s*자|Employer|Employee|$))',  # Lookahead
            re.IGNORECASE
        )
        for match in addr_pattern.finditer(text):
            val = match.group(2).strip()
            # Allow newline in capture for multi-line addresses
            if len(val) < 5: continue
            
            # Exclude if it's just a label "Address"
            if self._is_safe_keyword(val): continue

            start_idx = match.start(2)
            results.append({
                "text": val,
                "category": "Address",
                "subcategory": "HomeAddress",
                "offset": start_idx,
                "length": len(val),
                "confidence_score": 0.9
            })
        return results

    def _detect_labor_locations(self, text: str) -> List[Dict[str, Any]]:
        results = []
        # Matches: "소재지: 경기도...", "주소 : 서울...", "소 재 지 : ..."
        # Regex captures: Header -> Separator -> Value
        # IMPORTANT: Value stops at next field header (lookahead)
        loc_pattern = re.compile(
            r'(소\s*재\s*지|주\s*소|Location|Address|Employer)\s*[:.]?\s*'
            r'([가-힣0-9\s,\(\)로길동읍면시구군\-a-zA-Z]{5,120}?)'  # Non-greedy
            r'(?=\s*(?:성\s*명|전\s*화|사\s*업\s*자|주\s*민|생\s*년|본\s*국|근\s*로\s*자|Employee|Name|Phone|Identification|Birthdate|Address|$))',  # Lookahead: stop before next header
            re.IGNORECASE
        )
        
        for match in loc_pattern.finditer(text):
            val = match.group(2).strip()
            if len(val) < 5: continue
            
            # AGGRESSIVE FILTERING for garbage addresses
            # 1. Skip if contains English sentence words
            english_sentence_words = ['must', 'shall', 'and', 'or', 'the', 'of', 'in', 'to', 'is', 'are', 
                                     'can', 'will', 'comply', 'agreement', 'collective']
            if any(word in val.lower() for word in english_sentence_words):
                continue
            
            # 2. For Korean text, must contain address keywords
            korean_chars = sum(1 for c in val if '가' <= c <= '힣')
            if korean_chars > 3:
                # It's Korean text - must have address components
                if not any(c in val for c in '시도군구읍면로길동'):
                    continue
            
            # 3. Skip if it's just "signature" or Korean equivalent
            if '서명' in val or 'signature' in val.lower():
                continue
            
            # Simple validation
            # Must contain address keywords OR be numeric? No, usually text.
            header = match.group(1).replace(" ", "")
            
            start_idx = match.start(2)
            results.append({
                "text": val,
                "category": "Address",
                "subcategory": "WorkplaceAddress",
                "offset": start_idx,
                "length": len(val),
                "confidence_score": 0.95
            })
        return results

    # =========================================================================
    # COMMON HELPERS
    # =========================================================================
    
    def _find_all_names(self, text: str, names: Set[str]) -> List[Dict[str, Any]]:
        """
        Scans the text for all occurrences of the found names and masks them.
        Uses Regex to match names even if OCR inserted spaces (e.g. '김 서 연').
        Exceptions: Leaves the FIRST CHAR visible (e.g. Hong Gil Dong -> H***).
        """
        results = []
        if not names: return []
        
        print(f"DEBUG: Searching text for names: {names}")
        
        for name in names:
            if len(name) < 2: continue
            
            # Create Spacing-Safe Regex: "김서연" -> "김\s*서\s*연"
            # Remove spaces from the name itself to build a purely character-sequence regex
            # This ensures "Muhammad Asif" matches "MuhammadAsif" or "Muhammad  Asif"
            clean_chars = [c for c in name if not c.isspace()]
            safe_chars = [re.escape(c) for c in clean_chars]
            pattern_str = r'\s*'.join(safe_chars)
            name_pattern = re.compile(pattern_str, re.IGNORECASE) # Added IGNORECASE for safety
            
            count = 0
            for match in name_pattern.finditer(text):
                count += 1
                full_match = match.group()
                # Skip if it's part of a safe keyword (simple check)
                if self._is_safe_keyword(full_match.replace(" ", "")):
                    continue
                
                # Mask Start: We want to keep the FIRST character visible.
                # Problem: If "김 서 연", first char is match.start() to match.start()+1?
                # We need to identify the span of the first character.
                
                # Simple approach: Mask from match.start() + 1 to match.end()
                # Use sub-masking logic? 
                # Better: Let's mask everything AFTER the first character.
                # We need to find the length of the first character in the match.
                # Usually 1, but if spaces? "김  서 연" -> First char "김".
                
                # Find length of first char in the match string
                first_char = name[0]
                # In the match string, find where the first char ends.
                # Actually, easier: Just mask from match.start() + 1.
                # Unless the first char is followed by space. 
                # If "김 서 연", match.start()+1 is " ".
                
                # Refined: Mask from (Start + Length of First Char Token)
                # But verifying token length in OCR text is hard. 
                # Heuristic: Mask from match.start()+1. 
                # Visualizer maps to boxes. If box covers space, no big deal.
                
                mask_start = match.start() + 1
                mask_len = match.end() - match.start() - 1
                
                if mask_len > 0:
                     results.append({
                        "text": full_match[1:], 
                        "category": "Person",
                        "subcategory": "Name",
                        "offset": mask_start,
                        "length": mask_len,
                        "confidence_score": 0.99
                    })
            
            print(f"DEBUG: Found {count} occurrences of '{name}'")

        return results

    def _detect_addresses_strict(self, text: str, target_address: str, is_registry=False) -> List[Dict[str, Any]]:
        """
        Detects addresses but EXCLUDES significant matches to Target Address.
        1. Refined Regex: Supports spaces in city names (e.g. '서 울') and newlines.
        2. Normalization: Removes punctuation for exclusion check.
        """
        results = []
        
        # Space-tolerant City Pattern
        cities = ["서울", "부산", "대구", "인천", "광주", "대전", "울산", "세종", "경기", "강원", "충북", "충남", "전북", "전남", "경북", "경남", "제주"]
        city_regex_parts = []
        for c in cities:
            safe_c = "".join([f"{char}\\s*" for char in c]).rstrip("\\s*") 
            city_regex_parts.append(safe_c)
        city_pattern_str = "|".join(city_regex_parts)

        # Korean Address Regex
        k_addr_pattern = re.compile(
            f'({city_pattern_str})'
            r'([가-힣\s]*[시도군구]?)' 
            r'([가-힣0-9 \t,\(\)\-\n]*?)' 
            r'(로|길|동|읍|면|가)'
            r'([ \t\d,\-\(\)호층번지a-zA-Z\n]*)|$',
            re.IGNORECASE
        )
        
        # Robust Normalization: Remove Space, Newline, AND Punctuation (Comma, Dash, etc)
        def robust_normalize(s):
            return re.sub(r'[^\w가-힣]', '', str(s))

        target_clean = robust_normalize(target_address)
        
        print(f"DEBUG: Scanning for addresses strict... TargetClean: {target_clean[:20]}...")
        
        for match in k_addr_pattern.finditer(text):
            full_addr = match.group().strip()
            if not full_addr: continue
            if len(full_addr) < 5: continue
            
            # False Positive Filtering
            if full_addr.endswith("가"):
                bad_suffixes = ["전문가", "평가", "허가", "불가", "참가", "증가", "추가"]
                if any(full_addr.endswith(bad) for bad in bad_suffixes):
                    continue
            
            # Registry Specific Keywords
            if is_registry:
                 bad_keywords = ["철근", "콘크리트", "벽돌", "구조", "기와", "슬라브", "면적"]
                 if any(bk in full_addr for bk in bad_keywords):
                     continue 

            clean_check = full_addr.replace(" ", "").replace("\n", "")
            if len(clean_check) < 4: continue

            # EXCLUSION LOGIC (Numeric Fingerprint)
            # 1. Extract numbers from Target and Candidate
            def extract_numbers(s):
                return set(re.findall(r'\d+', s))

            target_nums = extract_numbers(target_address)
            candidate_nums = extract_numbers(full_addr)
            
            match_found = False
            
            # A. Robust String Match (Existing)
            candidate_norm = robust_normalize(full_addr)
            if target_clean and len(target_clean) > 5:
                if candidate_norm in target_clean or target_clean in candidate_norm:
                    match_found = True
            
            # B. Numeric Fingerprint Match (New - Higher Recalls)
            # If target has numbers (e.g. 724, 18), check if candidate has them.
            if not match_found and target_nums:
                # If target has 2+ numbers (e.g. 724-18), require ALL to be present.
                if len(target_nums) >= 2:
                    if target_nums.issubset(candidate_nums):
                        match_found = True
                # If target has 1 number (e.g. 724), it must be present.
                # Risk: matching "Room 724" unrelated. Add context check? 
                # For Lease/Registry, matching the Main Number is usually sufficient for exclusion safety.
                elif len(target_nums) == 1:
                    num = list(target_nums)[0]
                    # Only strict if number is significant (>=2 digits)
                    if len(num) >= 2 and num in candidate_nums:
                        match_found = True

            if match_found:
                # It's the target property -> VISIBLE (Do not Mask)
                print(f"DEBUG: Exclusion Match (Target): {full_addr}")
                continue
            else:
                # It's another address -> MASK
                results.append({
                    "text": full_addr, 
                    "category": "Address",
                    "subcategory": None,
                    "offset": match.start(),
                    "length": len(match.group()), 
                    "confidence_score": 0.85
                })
        return results

    def _detect_id_numbers(self, text: str) -> List[Dict[str, Any]]:
        results = []
        # 1. Resident / Alien Registration (XXXXXX-XXXXXXX) or (XXXXXX-1******)
        # Robust Regex: Allow optional spaces around hyphen and flexible masking chars
        patterns = [
            r'(\d{6})\s*[-–—]\s*([1-8])\s*([\d\*\s]{6})', # Resident/Alien
            r'(\d{3})\s*[-–—]\s*(\d{2})\s*[-–—]\s*(\d{5})' # Business
        ]
        
        for pat in patterns:
            for match in re.finditer(pat, text):
                results.append({
                    "text": match.group(),
                    "category": "Person",
                    "subcategory": "IdentificationNumber",
                    "offset": match.start(),
                    "length": len(match.group()),
                    "confidence_score": 1.0
                })
        return results
        
    def _detect_phone_numbers(self, text: str) -> List[Dict[str, Any]]:
        results = []
        # Support Landlines (02, 031, etc) and Mobile (010)
        # Allow dot, space, hyphen separators
        phone_pattern = re.compile(r'0\d{1,2}[\s\-\.]?\d{3,4}[\s\-\.]?\d{4}')
        for match in phone_pattern.finditer(text):
             results.append({
                "text": match.group(),
                "category": "PhoneNumber",
                "subcategory": None,
                "offset": match.start(),
                "length": len(match.group()),
                "confidence_score": 1.0
            })
        return results

    def _is_safe_keyword(self, text: str) -> bool:
        SAFE_KEYWORDS = {
            "성명", "이름", "주소", "주민등록번호", "연락처", "전화번호", "서명", "인", 
            "임대인", "임차인", "소유자", "근로자", "사용자", "대표자",
            "NAME", "ADDRESS", "EMPLOYER", "EMPLOYEE", "SIGNATURE", "BIRTHDATE",
            "소재지", "생년월일", "본국주소", "LOCATION", "거주지", "사업자등록번호",
            "부담금액", "금액", "업체명", "전화번호", "비용"
        }
        clean = text.replace(" ", "").replace(":", "")
        return clean in SAFE_KEYWORDS

    # =========================================================================
    # MAP TO BOXES (Preserved)
    # =========================================================================
    def map_pii_to_boxes(self, pii_entities: List[Dict], ocr_pages: List[Dict], full_text_map: List[Tuple[int, int, Dict]]) -> List[Dict]:
        """
        Maps detected PII entities to bounding boxes using Geometric Sub-Masking.
        IMPROVEMENT: Merges fragmented sub-boxes into a single clean bounding box per entity.
        Safety: Performs a final check on the masked text to ensure we aren't masking Safe Keywords.
        """
        print("DEBUG: Executing COMPLETE REFACTORED map_pii_to_boxes v4")
        print(f"DEBUG: Total PII entities to map: {len(pii_entities)}")
        print(f"DEBUG: Full text map length: {len(full_text_map)}")
        pii_boxes = []
        
        for idx, entity in enumerate(pii_entities):
            e_start = entity['offset']
            e_end = e_start + entity['length']
            print(f"\nDEBUG: Entity {idx}: '{entity['text'][:30]}...' offset={e_start}, len={entity['length']}")
            
            # 1. Collect all sub-boxes for this entity
            entity_sub_boxes = [] # (page_idx, [x1, y1, x2, y2])
            
            for (w_start, w_end, w_obj) in full_text_map:
                overlap_start = max(e_start, w_start)
                overlap_end = min(e_end, w_end)
                
                if overlap_start < overlap_end:
                    pidx = w_obj.get('page_idx', 0)
                    if pidx < len(ocr_pages):
                        p_w = ocr_pages[pidx].get('width', 1) or 1
                        p_h = ocr_pages[pidx].get('height', 1) or 1
                    else:
                        p_w, p_h = 1, 1

                    poly = w_obj.get('polygon', [])
                    if not poly: continue
                    xs = poly[0::2]
                    ys = poly[1::2]
                    if not xs or not ys: continue
                    
                    w_x1, w_y1, w_x2, w_y2 = min(xs), min(ys), max(xs), max(ys)
                    
                    # Normalize
                    nx1 = w_x1 / p_w
                    ny1 = w_y1 / p_h
                    nx2 = w_x2 / p_w
                    ny2 = w_y2 / p_h
                    w_width = nx2 - nx1
                    
                    # Ratio
                    word_len = w_end - w_start
                    if word_len <= 0: word_len = 1
                    rel_start = overlap_start - w_start
                    rel_end = overlap_end - w_start
                    ratio_start = rel_start / word_len
                    ratio_end = rel_end / word_len
                    
                    # Sub-box
                    mask_x1 = nx1 + (w_width * ratio_start)
                    mask_x2 = nx1 + (w_width * ratio_end)
                    
                    # Store sub-box
                    entity_sub_boxes.append((pidx, [mask_x1, ny1, mask_x2, ny2]))

            print(f"DEBUG: Found {len(entity_sub_boxes)} sub-boxes for this entity")
            if not entity_sub_boxes:
                print(f"DEBUG: SKIPPING entity - no matching words found in text_map")
                continue

            # 2. Group by page and Merge into ONE Box per page
            by_page_boxes = {}
            for pidx, box in entity_sub_boxes:
                if pidx not in by_page_boxes: by_page_boxes[pidx] = []
                by_page_boxes[pidx].append(box)
                
            for pidx, boxes in by_page_boxes.items():
                if not boxes: continue
                
                # Calculate Union Box
                u_x1 = min(b[0] for b in boxes)
                u_y1 = min(b[1] for b in boxes)
                u_x2 = max(b[2] for b in boxes)
                u_y2 = max(b[3] for b in boxes)
                
                if self._is_safe_keyword(entity['text']):
                    print(f"DEBUG: FILTERING OUT box for safe keyword: '{entity['text'][:40]}...'")
                    continue
                
                print(f"DEBUG: CREATING BOX for: '{entity['text'][:40]}...' page={pidx}, category={entity['category']}, box=[{u_x1:.3f}, {u_y1:.3f}, {u_x2:.3f}, {u_y2:.3f}]")
                pii_boxes.append({
                    "box_norm": [u_x1, u_y1, u_x2, u_y2],
                    "page_idx": pidx,
                    "category": entity['category'],
                    "text": entity['text']
                })

        print(f"\nDEBUG: Total boxes created: {len(pii_boxes)}")
        return pii_boxes
