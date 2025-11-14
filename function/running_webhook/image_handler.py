"""Image upload and storage handling."""

import logging
import os
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient


def upload_image_to_blob_storage(image_data, filename):
    """
    Upload image to Azure Blob Storage.
    
    Args:
        image_data: Binary image data
        filename: Name for the blob file
        
    Returns:
        Blob URL if successful, None if failed
    """
    try:
        blob_endpoint = os.environ.get("AZURE_STORAGE_BLOB_ENDPOINT")
        if not blob_endpoint:
            logging.warning("AZURE_STORAGE_BLOB_ENDPOINT environment variable is not set")
            return None
        
        container_name = "uploaded-images"
        
        # Initialize BlobServiceClient with DefaultAzureCredential
        credential = DefaultAzureCredential()
        blob_service_client = BlobServiceClient(
            account_url=blob_endpoint,
            credential=credential
        )
        
        # Get blob client
        blob_client = blob_service_client.get_blob_client(
            container=container_name,
            blob=filename
        )
        
        # Upload the image
        blob_client.upload_blob(image_data, overwrite=True)
        
        # Return the blob URL
        blob_url = blob_client.url
        logging.info(f"Successfully uploaded image to blob storage: {blob_url}")
        return blob_url
        
    except Exception as e:
        logging.error(f"Failed to upload image to blob storage: {str(e)}", exc_info=True)
        return None
