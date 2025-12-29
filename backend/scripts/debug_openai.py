import os
import sys
import httpx

# Add backend to path
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from app.core.config import settings

def list_deployments():
    endpoint = settings.AZURE_OPENAI_ENDPOINT.rstrip('/')
    api_key = settings.AZURE_OPENAI_API_KEY
    # Try a known stable API version for listing models, unrelated to the one in .env if possible,
    # but we will use the one in .env simply to check connectivity.
    # Actually, listing deployments is often strictly management API, but we can try listing models if supported.
    # Better approach: Just try a standard embedding test with common names.
    
    print(f"Checking Endpoint: {endpoint}")
    print("-" * 20)
    
    # Common names to test
    candidates = [
        "text-embedding-ada-002",
        "embedding",
        "embeddings",
        "ada-002",
        "text-embedding-3-small",
        "text-embedding-3-large"
    ]
    
    for deploy_name in candidates:
        url = f"{endpoint}/openai/deployments/{deploy_name}/embeddings?api-version=2023-05-15"
        print(f"Testing Embedding: '{deploy_name}' ... ", end="")
        
        try:
            # We send a dummy payload. If 404 -> Not Found. If 400 or 200 -> Found.
            resp = httpx.post(
                url, 
                headers={"api-key": api_key},
                json={"input": "test"}
            )
            if resp.status_code == 404:
                print("❌ Not Found")
            elif resp.status_code == 200:
                print("✅ Found & Working!")
            else:
                print(f"⚠️  Existed but error {resp.status_code} (Likely found)")
        except Exception as e:
            print(f"Error: {e}")

    print("-" * 20)
    print("Checking Chat Models (GPT-4/GPT-3.5)...")
    
    chat_candidates = [
        "gpt-4o",
        "gpt-4",
        "gpt-4-32k",
        "gpt-35-turbo",
        "gpt-3.5-turbo",
        "chat"
    ]
    
    for deploy_name in chat_candidates:
        # Use config version for chat
        ver = settings.AZURE_OPENAI_API_VERSION 
        url = f"{endpoint}/openai/deployments/{deploy_name}/chat/completions?api-version={ver}"
        print(f"Testing Chat: '{deploy_name}' (ver={ver}) ... ", end="")
        
        try:
            resp = httpx.post(
                url, 
                headers={"api-key": api_key},
                json={
                    "messages": [{"role": "user", "content": "Hello"}],
                    "max_tokens": 5
                }
            )
            if resp.status_code == 404:
                print("❌ Not Found")
            elif resp.status_code == 200:
                print("✅ Found & Working!")
            else:
                print(f"⚠️  Existed but error {resp.status_code} (Likely found)")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    list_deployments()
