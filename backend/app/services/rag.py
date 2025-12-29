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

logger = logging.getLogger(__name__)

class RAGService:
    def __init__(self):
        self.endpoint = settings.AZURE_SEARCH_ENDPOINT
        self.key = settings.AZURE_SEARCH_KEY
        self.credential = AzureKeyCredential(self.key) if self.key else None
        
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
        Targeted search for specific category: 'laws', 'cases', 'forms'
        """
        mapping = {
            "laws": (settings.AZURE_SEARCH_INDEX_LAWS, "법령"),
            "cases": (settings.AZURE_SEARCH_INDEX_CASES, "판례/사례"),
            "forms": (settings.AZURE_SEARCH_INDEX_FORMS, "표준계약서 해설")
        }
        
        if category_key not in mapping:
            return []
            
        index_name, label = mapping[category_key]
        
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

    def _search_index(self, index_name: str, query: str, category: str, vector: List[float] = []) -> List[str]:
        client = self._get_client(index_name)
        if not client:
             return [f"[{category} Mock] '{query}' 관련 내용..."]
        
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
