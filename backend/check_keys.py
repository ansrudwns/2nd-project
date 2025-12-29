
from app.core.config import settings
import os
try:
    from dotenv import load_dotenv, find_dotenv
except ImportError:
    print("python-dotenv library is NOT installed.")
    load_dotenv = None

print("--- Environment Variable Check ---")
print(f"Current Working Directory: {os.getcwd()}")
print(f"Checking .env file existence: {os.path.exists('.env')}")

if load_dotenv:
    print(f"Finding .env: {find_dotenv()}")
    loaded = load_dotenv(override=True)
    print(f"Direct load_dotenv result: {loaded}")
    
    # Check OS environ after load
    ep = os.environ.get("AZURE_LANGUAGE_ENDPOINT")
    key = os.environ.get("AZURE_LANGUAGE_KEY")
    print(f"OS Environ AZURE_LANGUAGE_ENDPOINT: {'[FOUND]' if ep else '[MISSING]'}")
    print(f"OS Environ AZURE_LANGUAGE_KEY: {'[FOUND]' if key else '[MISSING]'}")

print("\n--- Pydantic Settings Check ---")
print(f"settings.AZURE_LANGUAGE_ENDPOINT: {'[FOUND]' if settings.AZURE_LANGUAGE_ENDPOINT else '[MISSING]'}")
print(f"settings.AZURE_LANGUAGE_KEY: {'[FOUND]' if settings.AZURE_LANGUAGE_KEY else '[MISSING]'}")

try:
    from azure.ai.textanalytics import TextAnalyticsClient
    print(f"Azure SDK (TextAnalyticsClient): [INSTALLED]")
except ImportError:
    print(f"Azure SDK (TextAnalyticsClient): [MISSING] - Please run 'pip install azure-ai-textanalytics'")
