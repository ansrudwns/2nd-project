import logging
from typing import Dict, Any
from app.core.exceptions import AnalysisException, Stage

logger = logging.getLogger(__name__)

# Constants
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
MIN_DPI = 150
SUPPORTED_MIME = ["application/pdf", "image/jpeg", "image/png", "image/webp"]

class FileValidator:
    @staticmethod
    def validate(file_content: bytes, filename: str, mime_type: str):
        # 1. Size
        if len(file_content) > MAX_FILE_SIZE:
            raise AnalysisException(
                Stage.FILE_VALIDATE, "FILE_TOO_LARGE", "파일 크기는 10MB를 초과할 수 없습니다."
            )
        
        # 2. MIME
        if mime_type not in SUPPORTED_MIME:
            raise AnalysisException(
                Stage.FILE_VALIDATE, "UNSUPPORTED_FORMAT", f"지원하지 않는 포맷입니다: {mime_type}"
            )
            
        # 3. DPI Check (Placeholder - requires Image lib to read header)
        # In MVP, this is often skipped or done by reading the first few bytes.
        pass

class DocTypeClassifier:
    SCORES = {
        "lease_contract": ["임대차", "전세", "월세", "보증금", "임대인", "임차인", "월차임"],
        "labor_contract": ["근로계약", "사용자", "근로자", "임금", "연봉", "시급", "수습", "퇴직금", "근로기준법"],
        "registry": ["등기사항", "전부증명서", "표제부", "갑구", "을구", "소유자", "대지권"],
        "building_ledger": ["건축물대장", "전유부", "총괄표제부", "용도", "주구조"]
    }
    
    @staticmethod
    def classify(extracted_text: str) -> str:
        """
        Returns: 'contract' | 'registry' | 'building_ledger'
        Throws DOC_TYPE_UNDETERMINED
        """
        counts = {"lease_contract": 0, "labor_contract": 0, "registry": 0, "building_ledger": 0}
        
        for k, keywords in DocTypeClassifier.SCORES.items():
            for kw in keywords:
                if kw in extracted_text:
                    counts[k] += 1
        
        # Max score
        best_match = max(counts, key=counts.get)
        max_score = counts[best_match]
        
        logger.info(f"Doc Classification Scores: {counts}")
        
        if max_score < 3: # Threshold
            raise AnalysisException(
                Stage.DOC_TYPE_DETECT, 
                "DOC_TYPE_UNDETERMINED", 
                "문서 유형을 식별할 수 없습니다.",
                {"scores": counts},
                "계약서, 등기부등본, 건축물대장 중 하나를 업로드해주세요."
            )
            
        return best_match
