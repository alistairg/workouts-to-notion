"""Azure OpenAI integration for image analysis."""

import logging
import os
import base64
from azure.identity import DefaultAzureCredential
from openai import AzureOpenAI

# Image analysis prompt
IMAGE_ANALYSIS_PROMPT = """Analyze the provided image of an iOS running workout.
Extract the following information and output it in json format (example can be found at the end).

Required information:
- Workout time in minutes
- Distance in km (2 decimals)
- Avg. Cadence (only number)
- Avg heart rate (only number)
- Date

json should look like this:

{
    "duration": 62.5,
    "distance": 4.82,
    "cadence": 175,
    "bpm": 145,
    "date": "2024-06-15"
}"""


def get_openai_client():
    """
    Initialize and return Azure OpenAI client with automatic token refresh.
    
    The SDK handles token refresh automatically using azure_ad_token_provider.
    """
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
    if not endpoint:
        raise ValueError("AZURE_OPENAI_ENDPOINT environment variable is not set")
    
    # Pass credential directly - SDK will handle token refresh automatically
    credential = DefaultAzureCredential()
    
    return AzureOpenAI(
        azure_endpoint=endpoint,
        api_version="2024-02-15-preview",
        azure_ad_token_provider=lambda: credential.get_token(
            "https://cognitiveservices.azure.com/.default"
        ).token
    )


def analyze_workout_image(image_data):
    """
    Analyze workout image using Azure OpenAI.
    
    Args:
        image_data: Binary image data
        
    Returns:
        dict: Parsed workout data from the image
        
    Raises:
        Exception: If analysis fails or response is invalid
    """
    # Get Azure OpenAI client and deployment name
    client = get_openai_client()
    deployment_name = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o-mini")
    
    # Encode image to base64
    base64_image = base64.b64encode(image_data).decode('utf-8')
    
    # Call Azure OpenAI to analyze the image
    logging.info(f"Sending image to Azure OpenAI (deployment: {deployment_name})")
    
    response = client.chat.completions.create(
        model=deployment_name,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": IMAGE_ANALYSIS_PROMPT
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{base64_image}"
                        }
                    }
                ]
            }
        ]
    )
    
    # Extract the response content
    ai_response = response.choices[0].message.content
    logging.info(f"Raw Azure OpenAI response: {ai_response}")
    
    return ai_response
