import os
from pydantic_settings import BaseSettings
from typing import Optional

from pydantic import Field

class Settings(BaseSettings):
    PROJECT_NAME: str = "Real Estate Contract Analysis System"
    API_V1_STR: str = "/api/v1"
    
    # DB
    DATABASE_URL: str = Field(..., env="DATABASE_URL")
    
    # Azure OCR
    AZURE_FORM_ENDPOINT: Optional[str] = None
    AZURE_FORM_KEY: Optional[str] = None
    AZURE_FORM_API_VERSION: str = "2023-10-31-preview"
    
    # Azure Storage
    AZURE_STORAGE_CONNECTION_STRING: Optional[str] = None
    AZURE_CONTAINER_NAME: str = "history"
    
    # Azure Search
    AZURE_SEARCH_ENDPOINT: Optional[str] = None
    AZURE_SEARCH_KEY: Optional[str] = None
    AZURE_SEARCH_INDEX_LAWS: str = "laws-index"
    AZURE_SEARCH_INDEX_CASES: str = "cases-index"
    AZURE_SEARCH_INDEX_FORMS: str = "forms-index"

    # Labor Contract RAG
    AZURE_SEARCH_INDEX_LABOR_LAWS: str = "labor-laws-index"
    AZURE_SEARCH_INDEX_LABOR_CASES: str = "labor-cases-index"
    AZURE_SEARCH_INDEX_LABOR_FORMS: str = "labor-forms-index"
    
    # Azure OpenAI
    AZURE_OPENAI_API_KEY: Optional[str] = None
    AZURE_OPENAI_ENDPOINT: Optional[str] = None
    AZURE_OPENAI_API_VERSION: str = "2023-05-15"
    AZURE_OPENAI_DEPLOYMENT_NAME: Optional[str] = None
    AZURE_OPENAI_EMBEDDING_API_VERSION: Optional[str] = "2023-05-15"
    AZURE_OPENAI_EMBEDDING_MODEL: Optional[str] = "text-embedding-ada-002"

    # Security
    SECRET_KEY: str = "unsafe-secret-key-change-this"

    # Market API
    MARKET_API_URL: Optional[str] = None
    MARKET_API_KEY: Optional[str] = None
    
    # Azure Language (PII)
    AZURE_LANGUAGE_ENDPOINT: Optional[str] = None
    AZURE_LANGUAGE_KEY: Optional[str] = None
    MAX_CONCURRENT_TASKS: int = 10
    USE_PARALLEL_PROCESSING: bool = True
    USE_IMAGE_OPTIMIZATION: bool = True

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"

settings = Settings()
