import os
import sys
import glob 
import uuid
import logging
import re
import json
import base64

# Verify PyPDF2 or pypdf
try:
    from pypdf import PdfReader
except ImportError:
    print("Installing pypdf...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pypdf"])
    from pypdf import PdfReader

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app.core.config import settings
from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from openai import AzureOpenAI

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Config mapping: folder_name -> index_name
INDEX_MAP = {
    "laws": settings.AZURE_SEARCH_INDEX_LAWS,
    "cases": settings.AZURE_SEARCH_INDEX_CASES,
    "forms": settings.AZURE_SEARCH_INDEX_FORMS,
    "labor_laws": settings.AZURE_SEARCH_INDEX_LABOR_LAWS,
    "labor_cases": settings.AZURE_SEARCH_INDEX_LABOR_CASES,
    "labor_forms": settings.AZURE_SEARCH_INDEX_LABOR_FORMS
}

def get_openai_client():
    if settings.AZURE_OPENAI_API_KEY and settings.AZURE_OPENAI_ENDPOINT:
        return AzureOpenAI(
            api_key=settings.AZURE_OPENAI_API_KEY,
            api_version=settings.AZURE_OPENAI_EMBEDDING_API_VERSION,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT
        )
    return None

def generate_embedding(client, text):
    if not client:
        return []
    try:
        response = client.embeddings.create(
            input=text,
            model=settings.AZURE_OPENAI_EMBEDDING_MODEL
        )
        return response.data[0].embedding
    except Exception as e:
        logger.error(f"Embedding failed: {e}")
        return []

def extract_text_from_pdf(filepath):
    text = ""
    try:
        reader = PdfReader(filepath)
        for page in reader.pages:
            text += page.extract_text() + "\n"
    except Exception as e:
        logger.error(f"Text extraction failed for {filepath}: {e}")
    return text

# --- Specialized Parsers ---

def safe_split_text(text: str, max_chars: int = 4000) -> list[str]:
    """
    Split text into chunks that are safely under the character limit.
    Tries to split by newlines first to preserve sentence structure.
    """
    if len(text) <= max_chars:
        return [text]
    
    chunks = []
    current_chunk = ""
    
    lines = text.split('\n')
    for line in lines:
        if len(current_chunk) + len(line) + 1 > max_chars:
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = ""
            # If a single line is too huge, hard split it
            if len(line) > max_chars:
                for i in range(0, len(line), max_chars):
                    chunks.append(line[i:i+max_chars])
            else:
                current_chunk = line
        else:
            if current_chunk:
                current_chunk += "\n" + line
            else:
                current_chunk = line
                
    if current_chunk:
        chunks.append(current_chunk)
    return chunks

def parse_laws(text: str, source: str):
    """
    Split by '제N조' regex. Fallback to safe splitting.
    """
    chunks = []
    pattern = re.compile(r'(제\s*\d+(?:의\d+)?조)\s*(?:\((.*?)\))?')
    matches = list(pattern.finditer(text))
    
    if not matches:
        # Fallback: Safe Split
        raw_chunks = safe_split_text(text)
        for i, chunk in enumerate(raw_chunks):
            safe_id = base64.urlsafe_b64encode(f"{source}-part{i}-{uuid.uuid4().hex[:8]}".encode()).decode()
            chunks.append({
                "current_id": safe_id,
                "content": chunk,
                "metadata": json.dumps({"law_name": source, "rag_type": "law", "section": f"Part {i+1}"}, ensure_ascii=False)
            })
        return chunks

    for i, match in enumerate(matches):
        start_idx = match.start()
        end_idx = matches[i+1].start() if i + 1 < len(matches) else len(text)
        
        article_text = text[start_idx:end_idx].strip()
        
        # Double check: Is this chunk too big?
        sub_chunks = safe_split_text(article_text)
        
        for j, sub_text in enumerate(sub_chunks):
            article_num = match.group(1).replace(" ", "")
            title = match.group(2) if match.group(2) else ""
            
            meta = {
                "rag_type": "law",
                "law_name": source.replace(".pdf", ""),
                "article": article_num,
                "title": title,
                "part": j + 1
            }
            
            safe_id = base64.urlsafe_b64encode(f"{source}-{article_num}-{j}-{uuid.uuid4().hex[:8]}".encode()).decode()
            
            chunks.append({
                "current_id": safe_id,
                "content": sub_text, 
                "metadata": json.dumps(meta, ensure_ascii=False)
            })
    return chunks

def parse_forms(text: str, source: str):
    pattern = re.compile(r'(제\s*\d+\s*조)')
    matches = list(pattern.finditer(text))
    chunks = []
    
    if not matches:
        raw_chunks = safe_split_text(text)
        for i, chunk in enumerate(raw_chunks):
            safe_id = base64.urlsafe_b64encode(f"{source}-part{i}-{uuid.uuid4().hex[:8]}".encode()).decode()
            chunks.append({
                "current_id": safe_id,
                "content": chunk,
                "metadata": json.dumps({"template_name": source, "rag_type": "template", "section": f"Part {i+1}"}, ensure_ascii=False)
            })
        return chunks

    for i, match in enumerate(matches):
        start_idx = match.start()
        end_idx = matches[i+1].start() if i + 1 < len(matches) else len(text)
        
        clause_text = text[start_idx:end_idx].strip()
        sub_chunks = safe_split_text(clause_text)
        
        for j, sub_text in enumerate(sub_chunks):
            clause_title = match.group(1).replace(" ", "")
            meta = {
                "rag_type": "template",
                "template_name": source.replace(".pdf", ""),
                "clause": clause_title
            }
            safe_id = base64.urlsafe_b64encode(f"{source}-{clause_title}-{j}-{uuid.uuid4().hex[:8]}".encode()).decode()
            chunks.append({
                "current_id": safe_id,
                "content": sub_text,
                "metadata": json.dumps(meta, ensure_ascii=False)
            })
    return chunks

def parse_cases(text: str, source: str):
    chunks = []
    pattern = re.compile(r'((?:\[|\b)(?:사례|Case|유형)\s*\d+(?:\]|\b|\.))')
    matches = list(pattern.finditer(text))
    
    if not matches:
        raw_chunks = safe_split_text(text)
        for i, chunk in enumerate(raw_chunks):
            safe_id = base64.urlsafe_b64encode(f"{source}-part{i}-{uuid.uuid4().hex[:8]}".encode()).decode()
            chunks.append({
                "current_id": safe_id,
                "content": chunk, 
                "metadata": json.dumps({"rag_type": "case", "case_title": source.replace(".pdf", ""), "lesson": "General Case", "part": i+1}, ensure_ascii=False)
            })
        return chunks

    for i, match in enumerate(matches):
        start_idx = match.start()
        end_idx = matches[i+1].start() if i + 1 < len(matches) else len(text)
        
        case_content = text[start_idx:end_idx].strip()
        sub_chunks = safe_split_text(case_content)
        
        for j, sub_text in enumerate(sub_chunks):
            case_title = match.group(1).strip()
            lines = sub_text.split('\n')
            lesson_guess = lines[0] if lines else "Check details"
            
            meta = {
                "rag_type": "case",
                "case_title": f"{source} - {case_title}",
                "lesson": lesson_guess[:100],
                "part": j + 1
            }
            
            safe_id = base64.urlsafe_b64encode(f"{source}-{case_title}-{j}-{uuid.uuid4().hex[:8]}".encode()).decode()
            chunks.append({
                "current_id": safe_id,
                "content": sub_text,
                "metadata": json.dumps(meta, ensure_ascii=False)
            })
    return chunks

def ingest_data(data_dir, scope="all"):
    openai_client = get_openai_client()
    if not openai_client:
        logger.warning("Amazon OpenAI not configured. Embeddings will be skipped.")

    # Process each category
    parsers = {
        "laws": parse_laws,
        "forms": parse_forms,
        "cases": parse_cases,
        "labor_laws": parse_laws,
        "labor_cases": parse_cases,
        "labor_forms": parse_forms
    }
    
    # Define scopes
    scopes = {
        "lease": ["laws", "cases", "forms"],
        "labor": ["labor_laws", "labor_cases", "labor_forms"]
    }

    target_categories = []
    if scope == "all":
        target_categories = list(INDEX_MAP.keys())
    elif scope in scopes:
        target_categories = scopes[scope]

    logger.info(f"Starting ingestion with scope: {scope}")

    for category in target_categories:
        index_name = INDEX_MAP.get(category)
        if not index_name: continue

        folder_path = os.path.join(data_dir, category)
        if not os.path.exists(folder_path):
            logger.warning(f"Skipping {category}: Folder not found at {folder_path}")
            continue
            
        logger.info(f"Processing {category} -> {index_name}")
        search_client = SearchClient(
            endpoint=settings.AZURE_SEARCH_ENDPOINT,
            index_name=index_name,
            credential=AzureKeyCredential(settings.AZURE_SEARCH_KEY)
        )

        pdf_files = glob.glob(os.path.join(folder_path, "*.pdf"))
        documents = []

        for pdf in pdf_files:
            filename = os.path.basename(pdf)
            text = extract_text_from_pdf(pdf)
            
            # Apply Specialized Parser
            parser = parsers.get(category)
            if parser:
                 chunks = parser(text, filename)
                 
                 for chunk in chunks:
                     doc = {
                         "id": chunk["current_id"],
                         "content": chunk["content"],
                         "source": filename,
                         "metadata": chunk["metadata"]
                     }
                     if openai_client:
                         v = generate_embedding(openai_client, chunk["content"])
                         if v:
                             doc["vector"] = v
                     documents.append(doc)

        if documents:
            # Batch upload (max 1000 per batch usually)
            batch_size = 500
            for i in range(0, len(documents), batch_size):
                batch = documents[i:i+batch_size]
                try:
                    search_client.upload_documents(documents=batch)
                    logger.info(f"Uploaded batch {i//batch_size + 1}")
                except Exception as e:
                    logger.error(f"Batch upload failed: {e}")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Ingest Data into Azure AI Search")
    parser.add_argument("--scope", type=str, default="all", choices=["all", "lease", "labor"], help="Scope of data to ingest")
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) # backend/
    project_root = os.path.dirname(base_dir) # 2nd_project2/
    target_data_dir = os.path.join(project_root, "data")
    
    ingest_data(target_data_dir, scope=args.scope)
