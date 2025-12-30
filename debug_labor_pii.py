
import sys
import os
import re
from dotenv import load_dotenv

# Load env vars
load_dotenv(os.path.join(os.getcwd(), 'backend', '.env'))

# Add backend to path to import PiiService
sys.path.append(os.path.join(os.getcwd(), 'backend'))

from app.services.pii import PiiService

def test_labor_pii():
    pii = PiiService()
    
    # Mock Text matching the User's Image (approximate linearizion)
    # Note: OCR often inserts spaces for table columns
    mock_text = """
    표준근로계약서
    Standard Labor Contract
    (앞쪽)
    아래 당사자는 다음과 같이 근로계약을 체결하고 이를 성실히 이행할 것을 약정한다.
    The following parties to the contract agree to fully comply with the terms of the contract stated hereinafter.
    
    사용자    전화번호 031-491-1234
    Employer
    소재지 경기도 안산시 단원구 산단로 123 (원시동)
    성명 김철수 (Kim Cheol-su)    사업자등록번호(주민등록번호) 123456-1234567
    Identification number
    
    근로자    성명 무함마드 아시프    생년월일 Birthdate 1995년 5월 20일
    Employee    Muhammad Asif
    본국주소 Address House No. 12, Street 4, Sector G-9, Islamabad, Pakistan (Home Country)
    """
    
    print("--- 1. Testing Document Classification (Simulation) ---")
    doc_type = "RENT"
    if re.search(r'근\s*로\s*계\s*약|Standard\s*Labor', mock_text, re.IGNORECASE):
        doc_type = "LABOR"
    print(f"Detected Doc Type: {doc_type}")
    
    if doc_type != "LABOR":
        print("FAIL: Doc Type not detected as LABOR")
        return

    print("\n--- 2. Testing PII Detection (Labor Mode) ---")
    # Simulate analysis.py calling detect_pii
    entities = pii.detect_pii(mock_text, doc_type="LABOR", context={})
    
    # Check Findings
    found = {
        "Phone": False,
        "EmployerAddress": False,
        "EmployerName": False,
        "EmployeeName": False,
        "Birthdate": False,
        "HomeAddress": False
    }
    
    print(f"Entities Found: {len(entities)}")
    for e in entities:
        txt = e['text']
        cat = e['category']
        sub = e.get('subcategory')
        print(f" - [{cat}/{sub}] {txt}")
        
        if "031-491-1234" in txt: found['Phone'] = True
        if "경기도 안산시" in txt: found['EmployerAddress'] = True
        if "김철수" in txt: found['EmployerName'] = True
        if "무함마드" in txt or "Muhammad" in txt: found['EmployeeName'] = True
        if "1995" in txt: found['Birthdate'] = True
        if "Islamabad" in txt: found['HomeAddress'] = True
        
    print("\n--- 3. Verification Report ---")
    all_pass = True
    for k, v in found.items():
        status = "PASS" if v else "FAIL <<<<"
        print(f"{k}: {status}")
        if not v: all_pass = False
        
    if all_pass:
        print("\nSUCCESS: All PII fields detected locally!")
    else:
        print("\nFAILURE: Some fields were missed.")

if __name__ == "__main__":
    test_labor_pii()
