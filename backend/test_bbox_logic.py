
import re

def map_risk_to_box_mock(ocr_result, evidence_detail):
    print(f"Testing Evidence: '{evidence_detail}'")
    if not evidence_detail or not ocr_result: return []
    
    # --- Exact Code Logic Copy ---
    quoted_keywords = re.findall(r"'(.*?)'", evidence_detail)
    number_matches = re.findall(r'\b\d{1,3}(?:,\d{3})*(?:\.\d+)?\b', evidence_detail)
    target_numbers = [n.replace(",", "") for n in number_matches if len(n.replace(",", "")) > 1]
    raw_tokens = re.split(r'[^\w]', evidence_detail)
    text_keywords = [t for t in raw_tokens if len(t) >= 2 and not t.isdigit()]

    print(f"Debug Targets -> Quoted: {quoted_keywords}, Numbers: {target_numbers}, Keywords: {text_keywords}")

    boxes = []
    pages = ocr_result.get('pages', [])
    
    for p_idx, page in enumerate(pages):
        for line in page.get('lines', []):
            line_content = line.get('content', '')
            if not line_content: continue
            
            is_match = False
            
            # A. Check Quoted
            for q in quoted_keywords:
                if q.replace(" ", "") in line_content.replace(" ", ""):
                    is_match = True
                    break
            
            # B. Check Numeric
            if not is_match and target_numbers:
                for t_num in target_numbers:
                    if t_num in line_content.replace(",", ""):
                        is_match = True
                        break
            
            # C. Check Text Keyword
            if not is_match and text_keywords:
                line_tokens = set(re.split(r'[^\w]', line_content))
                target_set = set(text_keywords)
                overlap = target_set.intersection(line_tokens)
                
                if len(overlap) >= 2:
                    is_match = True
                elif len(overlap) == 1 and len(target_set) < 3:
                    is_match = True
                    
            if is_match:
                print(f"MATCH FOUND in line: '{line_content}'")
                boxes.append(line_content)
    
    return boxes

# Test Cases
ocr_data = {
    "pages": [{
        "lines": [
            {"content": "월 급여는 2,060,740원 으로 한다."},
            {"content": "근로 계약 기간은 2025년 부터이다."},
            {"content": "임금 지급일은 매월 10일이다."}
        ]
    }]
}

# 1. User Scenario: Punctuation attached to number
print("--- TEST 1: Number with punctuation ---")
map_risk_to_box_mock(ocr_data, "계약된 급여(2,060,740원)는 최저임금보다 부족합니다.")

# 2. Text Keyword
print("\n--- TEST 2: Text Keywords ---")
map_risk_to_box_mock(ocr_data, "근로 계약 기간이 명시되지 않음")
