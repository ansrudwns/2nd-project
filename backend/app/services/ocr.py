import logging
import json
from typing import List, Dict, Any
from app.core.config import settings
from app.core.exceptions import AnalysisException, Stage

# Azure SDK
try:
    from azure.ai.documentintelligence import DocumentIntelligenceClient
    from azure.core.credentials import AzureKeyCredential
except ImportError:
    DocumentIntelligenceClient = None

logger = logging.getLogger(__name__)

class OCRService:
    def __init__(self):
        self.client = None
        if settings.AZURE_FORM_KEY and settings.AZURE_FORM_ENDPOINT and DocumentIntelligenceClient:
            self.client = DocumentIntelligenceClient(
                endpoint=settings.AZURE_FORM_ENDPOINT, 
                credential=AzureKeyCredential(settings.AZURE_FORM_KEY),
                api_version=settings.AZURE_FORM_API_VERSION
            )

    def extract(self, file_content: bytes, mime_type: str) -> Dict[str, Any]:
        """
        Extract detailed result including text, lines (coords), and tables.
        Returns generic dict structure from Azure.
        """
        if not self.client:
            logger.warning("Azure OCR Client not initialized. Using Mock.")
            return self._mock_extract()

        try:
            logger.info("Sending request to Azure Document Intelligence (Layout Model)...")
            poller = self.client.begin_analyze_document(
                "prebuilt-layout", # Optimized for Forms/Tables
                analyze_request=file_content,
                content_type=mime_type,
                locale="ko-KR"
            )
            result = poller.result()
            
            # Simple validation of confidence is hard on 'read' model as it gives standard text.
            # Using content length check.
            if len(result.content) < 50:
                 raise AnalysisException(
                    Stage.OCR, "OCR_LOW_CONFIDENCE", "문서 내용이 너무 적거나 인식되지 않았습니다."
                )
            
            # Convert to dict for serialization and Normalize Coordinates to Points (72 DPI)
            extracted_pages = []
            
            for page in result.pages:
                # Determine scale factor to convert to Points (ReportLab uses Points)
                # Azure unit: 'pixel', 'inch'
                unit = page.unit
                scale = 1.0
                if unit == "inch":
                    scale = 72.0 # 1 inch = 72 points
                
                # Normalize Lines
                lines = []
                for line in page.lines:
                    # Polygon is list of points
                    poly = [float(p) * scale for p in line.polygon]
                    lines.append({
                        "content": line.content,
                        "polygon": poly
                    })
                
                # Normalize Words (For Precise PII Masking)
                words = []
                if hasattr(page, 'words'):
                     for word in page.words:
                        poly = [float(p) * scale for p in word.polygon]
                        words.append({
                            "content": word.content,
                            "polygon": poly
                        })
                
                extracted_pages.append({
                    "lines": lines,
                    "words": words,
                    "width": page.width * scale,
                    "height": page.height * scale,
                    "unit": "point" # Now normalized
                })

            return {
                "content": result.content,
                "pages": extracted_pages
            }

        except Exception as e:
            logger.error(f"OCR Failed: {e}")
            raise AnalysisException(
                Stage.OCR, "OCR_FAILED", "문서 인식 중 오류가 발생했습니다.", 
                {"detail": str(e)}, "잠시 후 다시 시도하거나 이미지를 선명하게 하여 업로드해주세요."
            )

    def _mock_extract(self):
        # Return a fake result structure that conforms to what we expect downstream
        return {
            "content": "임대차 계약서 ... 보증금 1억 2천만원 ...",
            "pages": [
                {
                    "lines": [
                        {"content": "임대차 계약서", "polygon": [0,0,1,1]}
                    ]
                }
            ]
        }
