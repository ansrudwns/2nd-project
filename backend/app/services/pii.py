
import logging
from typing import List, Dict, Any, Tuple
from app.core.config import settings
from app.core.exceptions import AnalysisException, Stage

# Azure SDK
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

    def detect_pii(self, text: str, language="ko") -> List[Dict[str, Any]]:
        """
        Detects PII entities in the given text using Azure AI Language.
        Returns list of {text, category, subcategory, offset, length, confidence_score}.
        """
        if not self.client:
            return []

        try:
            # Azure limits doc length, usually 5000 chars. Truncate for MVP if needed.
            # Real impl should chunk.
            truncated_text = text[:5000] 
            
            # Call Azure PII
            # client.recognize_pii_entities -> list of RecognizePiiEntitiesResult
            # We pass a list of documents (just 1 here)
            poller = self.client.recognize_pii_entities(documents=[truncated_text], language=language)
            
            entities = []
            # iterate over document results
            for doc in poller:
                if not doc.is_error:
                    for entity in doc.entities:
                        entities.append({
                            "text": entity.text,
                            "category": entity.category,
                            "subcategory": entity.subcategory,
                            "offset": entity.offset,
                            "length": entity.length,
                            "confidence_score": entity.confidence_score
                        })
                else:
                    logger.error(f"PII Doc Error: {doc.error.code} {doc.error.message}")
            
            return entities

        except Exception as e:
            logger.error(f"Azure PII Service Failed: {e}")
            return []

    def map_pii_to_boxes(self, pii_entities: List[Dict], ocr_pages: List[Dict], full_text_map: List[Tuple[int, int, Dict]]) -> List[Dict]:
        """
        Maps extracted PII entities (with offsets in full_text) back to OCR bounding boxes.
        
        full_text_map: List of (start_index, end_index, word_obj) mapping the concatenated text back to original words.
        word_obj comes from OCR 'words' list.
        
        Returns: List of {box_norm, page_idx, category, text}
        """
        pii_boxes = []
        
        for entity in pii_entities:
            e_start = entity['offset']
            e_end = e_start + entity['length']
            
            # Find words in full_text_map that intersect with [e_start, e_end]
            matched_words = []
            for (w_start, w_end, w_obj) in full_text_map:
                # Intersection check
                if max(e_start, w_start) < min(e_end, w_end):
                    matched_words.append(w_obj)
            
            if not matched_words:
                continue
            
            # Group matched words by page_idx, because an entity could theoretically span pages (unlikely but safe)
            # Actually OCR service usually separates pages, so full_text construction logic matters.
            # Assuming full_text is per-document, spanning pages.
            
            by_page = {}
            for w in matched_words:
                # OCR word object usually doesn't have page_idx inside it in standard Azure response structure,
                # unless we added it during flattening.
                # The caller must ensure 'word_obj' has 'page_idx'.
                pidx = w.get('page_idx', 0)
                if pidx not in by_page:
                    by_page[pidx] = []
                by_page[pidx].append(w)
            
            for pidx, words in by_page.items():
                if not words: continue
                
                # Get page dimensions for normalization
                # Caller passes ocr_pages[pidx] with width/height
                if pidx < len(ocr_pages):
                    p_w = ocr_pages[pidx].get('width', 1)
                    p_h = ocr_pages[pidx].get('height', 1)
                else:
                    p_w, p_h = 1, 1
                
                # Calculate bounding box covering all words
                xs = []
                ys = []
                for w in words:
                    poly = w.get('polygon', []) # [x1, y1, x2, y2, ...]
                    if poly:
                        xs.extend(poly[0::2])
                        ys.extend(poly[1::2])
                
                if xs and ys:
                    # Normalized coords
                    box = [
                        min(xs) / p_w,
                        min(ys) / p_h,
                        max(xs) / p_w,
                        max(ys) / p_h
                    ]
                    
                    pii_boxes.append({
                        "box_norm": box,
                        "page_idx": pidx,
                        "category": entity['category'],
                        "text": entity['text'] # Original text
                    })
                    
        return pii_boxes
