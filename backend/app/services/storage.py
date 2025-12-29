from azure.storage.blob import BlobServiceClient, ContentSettings
from azure.storage.blob import BlobServiceClient, ContentSettings, generate_blob_sas, BlobSasPermissions
from app.core.config import settings
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class BlobStorageService:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(BlobStorageService, cls).__new__(cls)
            cls._instance.client = cls._connect()
        return cls._instance

    @staticmethod
    def _connect():
        try:
            if not settings.AZURE_STORAGE_CONNECTION_STRING:
                logger.warning("AZURE_STORAGE_CONNECTION_STRING not set. Blob storage will fail.")
                return None
            return BlobServiceClient.from_connection_string(settings.AZURE_STORAGE_CONNECTION_STRING)
        except Exception as e:
            logger.error(f"Failed to connect to Azure Blob Storage: {e}")
            return None

    def upload_file(self, data: bytes, filename: str, content_type: str = "application/pdf") -> str:
        """
        Uploads bytes to Azure Blob Storage and returns the public URL.
        """
        if not self.client:
            raise Exception("Azure Blob Storage client is not initialized.")

        try:
            container_name = getattr(settings, "AZURE_CONTAINER_NAME", "history")
            
            # Create container if not exists
            container_client = self.client.get_container_client(container_name)
            if not container_client.exists():
                container_client.create_container() # Private by default

            blob_client = container_client.get_blob_client(filename)
            
            # Upload
            blob_client.upload_blob(
                data,
                overwrite=True,
                content_settings=ContentSettings(content_type=content_type)
            )
            
            # Generate SAS Token for access (valid for 24 hours)
            # We need to extract account_name and account_key from connection string
            # Simplified parsing (assuming standard format)
            conn_str = settings.AZURE_STORAGE_CONNECTION_STRING
            account_key = None
            account_name = self.client.account_name
            
            # Parse key manually if possible or trust the client logic? 
            # Client doesn't expose key easily. Let's parse string.
            for part in conn_str.split(";"):
                if part.startswith("AccountKey="):
                    account_key = part.replace("AccountKey=", "")
                    break
            
            if account_key:
                sas_token = generate_blob_sas(
                    account_name=account_name,
                    container_name=container_name,
                    blob_name=filename,
                    account_key=account_key,
                    permission=BlobSasPermissions(read=True),
                    expiry=datetime.utcnow() + timedelta(hours=24)
                )
                return f"{blob_client.url}?{sas_token}"
            else:
                # Fallback if key parse fail (should not happen with valid conn str)
                return blob_client.url
            
        except Exception as e:
            logger.error(f"Failed to upload file {filename} to Azure Blob: {e}")
            raise e
            raise e

    def delete_file(self, filename: str) -> bool:
        """
        Deletes a file from Azure Blob Storage.
        """
        if not self.client:
            logger.warning("Azure Blob Storage client is not initialized.")
            return False

        try:
            container_name = getattr(settings, "AZURE_CONTAINER_NAME", "history")
            container_client = self.client.get_container_client(container_name)
            
            if not container_client.exists():
                return False

            blob_client = container_client.get_blob_client(filename)
            if blob_client.exists():
                blob_client.delete_blob()
                return True
            return False
            
        except Exception as e:
            logger.error(f"Failed to delete file {filename} from Azure Blob: {e}")
            return False
