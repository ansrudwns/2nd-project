import logging
from typing import List
from app.core.config import settings
from app.core.exceptions import AnalysisException, Stage

try:
    from azure.search.documents import SearchClient
    from azure.search.documents.models import VectorizedQuery
    from azure.core.credentials import AzureKeyCredential
    from openai import AzureOpenAI
except ImportError:
    SearchClient = None
    VectorizedQuery = None
    AzureOpenAI = None
    AzureKeyCredential = None

logger = logging.getLogger(__name__)

class RAGService:
    CATEGORY_INDEXES = {
        "laws": ("AZURE_SEARCH_INDEX_LAWS", "법령"),
        "cases": ("AZURE_SEARCH_INDEX_CASES", "판례/사례"),
        "forms": ("AZURE_SEARCH_INDEX_FORMS", "표준계약서 해설"),
        "labor_laws": ("AZURE_SEARCH_INDEX_LABOR_LAWS", "노동법령"),
        "labor_cases": ("AZURE_SEARCH_INDEX_LABOR_CASES", "노동 판례/사례"),
        "labor_forms": ("AZURE_SEARCH_INDEX_LABOR_FORMS", "표준근로계약서 해설"),
    }

    def __init__(self):
        self.endpoint = settings.AZURE_SEARCH_ENDPOINT
        self.key = settings.AZURE_SEARCH_KEY
        self.credential = AzureKeyCredential(self.key) if self.key and AzureKeyCredential else None
        
        self.openai_client = None
        if settings.AZURE_OPENAI_API_KEY and settings.AZURE_OPENAI_ENDPOINT:
            self.openai_client = AzureOpenAI(
                api_key=settings.AZURE_OPENAI_API_KEY,
                api_version=settings.AZURE_OPENAI_EMBEDDING_API_VERSION,
                azure_endpoint=settings.AZURE_OPENAI_ENDPOINT
            )
        
    def _get_client(self, index_name: str):
        if self.endpoint and self.credential and SearchClient:
             return SearchClient(
                endpoint=self.endpoint,
                index_name=index_name,
                credential=self.credential
            )
        return None

    def _generate_embedding(self, text: str) -> List[float]:
        if not self.openai_client or not settings.AZURE_OPENAI_EMBEDDING_MODEL:
            return []
        # Generate embedding
        response = self.openai_client.embeddings.create(
            input=text,
            model=settings.AZURE_OPENAI_EMBEDDING_MODEL
        )
        return response.data[0].embedding

    def search_category(self, category_key: str, query: str, vector: List[float] = None) -> List[str]:
        """
        Targeted search for lease or labor legal sources.
        """
        category = self.CATEGORY_INDEXES.get(category_key)
        if not category:
            logger.warning("Unsupported RAG category requested: %s", category_key)
            return []

        setting_name, label = category
        index_name = getattr(settings, setting_name, None)
        if not index_name:
            logger.warning("RAG index is not configured for category: %s", category_key)
            return []
        
        # If vector not provided, generate it
        if not vector:
            vector = self._generate_embedding(query)
            
        return self._search_index(index_name, query, label, vector)

    def search_all(self, query: str) -> List[str]:
        """
        Search across Laws, Cases, and Standard Forms using Hybrid Search (if possible).
        """
        # ... (rest of search_all logic is same in structure but calls _search_index)
        results = []
        # Pre-calculate embedding once if possible? 
        # Actually _search_index calls client search. 
        # For efficiency, we can generate embedding ONCE here and pass it.
        
        vector = self._generate_embedding(query)
        
        results.extend(self.search_category("laws", query, vector))
        results.extend(self.search_category("cases", query, vector))
        results.extend(self.search_category("forms", query, vector))
        
        return results

    def _search_index(self, index_name: str, query: str, category: str, vector: List[float] = None) -> List[str]:
        client = self._get_client(index_name)
        if not client:
             logger.warning("RAG search unavailable for category: %s", category)
             return []
        
        vector_queries = None
        if vector and VectorizedQuery:
            # Assuming the vector field in index is named 'vector' or 'content_vector'
            # We typically use 'embedding' or 'vector'. Let's assume 'vector'.
            vector_queries = [VectorizedQuery(vector=vector, k_nearest_neighbors=3, fields="vector")]
        
        # Hybrid Search
        found = client.search(
            search_text=query, 
            vector_queries=vector_queries,
            top=2
        )
        return [f"[{category}] {r.get('source', '')}: {r.get('content', '')}" for r in found]

    # Deprecated single search, kept for compatibility if needed or redirect
    def search_laws(self, query: str) -> List[str]:
        return self._search_index(settings.AZURE_SEARCH_INDEX_LAWS, query, "법령")
