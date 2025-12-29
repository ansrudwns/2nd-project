import os
import sys

# Add backend to path to import app.core.config
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from azure.core.credentials import AzureKeyCredential
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex,
    SimpleField,
    SearchableField,
    SearchField,
    VectorSearch,
    HnswAlgorithmConfiguration,
    VectorSearchProfile
)
from app.core.config import settings

def create_index(client: SearchIndexClient, index_name: str):
    print(f"Creating/Updating index: {index_name}...")
    
    # Define Fields
    fields = [
        SimpleField(name="id", type="Edm.String", key=True),
        SearchableField(name="content", type="Edm.String", analyzer_name="ko.lucene"),
        SimpleField(name="source", type="Edm.String", filterable=True),
        SimpleField(name="metadata", type="Edm.String"), # JSON string for structured info
        SearchField(
            name="vector", 
            type="Collection(Edm.Single)", 
            searchable=True, 
            vector_search_dimensions=1536, # ada-002 dimension
            vector_search_profile_name="my-vector-profile"
        )
    ]

    # Define Vector Search Config
    vector_search = VectorSearch(
        algorithms=[
            HnswAlgorithmConfiguration(
                name="my-hnsw-config",
                parameters={"m": 4, "efConstruction": 400, "efSearch": 500, "metric": "cosine"}
            )
        ],
        profiles=[
            VectorSearchProfile(
                name="my-vector-profile",
                algorithm_configuration_name="my-hnsw-config"
            )
        ]
    )

    index = SearchIndex(name=index_name, fields=fields, vector_search=vector_search)
    
    try:
        client.create_or_update_index(index)
        print(f" -> Success: {index_name}")
    except Exception as e:
        print(f" -> Failed: {e}")

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Initialize Azure Search Indices")
    parser.add_argument("--scope", type=str, default="all", choices=["all", "lease", "labor"], help="Scope of indices to initialize")
    args = parser.parse_args()

    if not settings.AZURE_SEARCH_ENDPOINT or not settings.AZURE_SEARCH_KEY:
        print("Error: Azure Search Endpoint or Key is missing in .env")
        return

    client = SearchIndexClient(
        endpoint=settings.AZURE_SEARCH_ENDPOINT, 
        credential=AzureKeyCredential(settings.AZURE_SEARCH_KEY)
    )

    indices_lease = [
        settings.AZURE_SEARCH_INDEX_LAWS,
        settings.AZURE_SEARCH_INDEX_CASES,
        settings.AZURE_SEARCH_INDEX_FORMS
    ]
    
    indices_labor = [
        settings.AZURE_SEARCH_INDEX_LABOR_LAWS,
        settings.AZURE_SEARCH_INDEX_LABOR_CASES,
        settings.AZURE_SEARCH_INDEX_LABOR_FORMS
    ]

    target_indices = []
    if args.scope == "all":
        target_indices = indices_lease + indices_labor
    elif args.scope == "lease":
        target_indices = indices_lease
    elif args.scope == "labor":
        target_indices = indices_labor

    print(f"Initializing indices for scope: {args.scope}")
    for idx in target_indices:
        create_index(client, idx)

if __name__ == "__main__":
    main()
