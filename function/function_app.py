import azure.functions as func
import logging
import os
import json
import base64
import uuid
import imghdr
from datetime import datetime, timedelta
from collections import defaultdict
from azure.identity import DefaultAzureCredential
from azure.storage.blob import BlobServiceClient
from openai import AzureOpenAI
import requests

app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)

# Define maximum file size (10MB for screenshots)
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB in bytes

# Define maximum request size (10MB)
MAX_REQUEST_SIZE = 10 * 1024 * 1024  # 10MB in bytes

# Rate limiting configuration
MAX_REQUESTS_PER_MINUTE = 10
_request_counts = defaultdict(list)

# Initialize Azure OpenAI client
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

def validate_file_upload(file_obj, req):
    """
    Validate uploaded file size.
    
    Args:
        file_obj: File object from request
        req: HTTP request object for header access
        
    Returns:
        tuple: (is_valid, error_message)
    """
    # Check content length from headers first
    content_length = req.headers.get('Content-Length')
    if content_length and int(content_length) > MAX_FILE_SIZE:
        return False, f"File too large. Maximum size is {MAX_FILE_SIZE / (1024*1024):.0f}MB"
    
    # Read file with size limit
    file_obj.stream.seek(0, 2)  # Seek to end
    file_size = file_obj.stream.tell()
    file_obj.stream.seek(0)  # Reset to beginning
    
    if file_size > MAX_FILE_SIZE:
        return False, f"File too large. Maximum size is {MAX_FILE_SIZE / (1024*1024):.0f}MB"
    
    if file_size == 0:
        return False, "File is empty"
    
    return True, None

def validate_image_file(file_obj, filename):
    """
    Validate that uploaded file is actually an image.
    
    Args:
        file_obj: File object to validate
        filename: Original filename
        
    Returns:
        tuple: (is_valid, error_message, detected_type)
    """
    ALLOWED_EXTENSIONS = {'.jpg', '.jpeg', '.png', '.heic'}
    
    # Check file extension
    ext = os.path.splitext(filename)[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        return False, f"Invalid file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}", None
    
    # Read first bytes to detect actual file type
    file_obj.stream.seek(0)
    header = file_obj.stream.read(512)
    file_obj.stream.seek(0)
    
    # Detect image type from magic bytes
    detected_type = imghdr.what(None, h=header)
    
    if detected_type not in ['jpeg', 'png']:
        return False, "File content does not match image format", detected_type
    
    return True, None, detected_type

def sanitize_text_input(text, field_name, max_length=1000):
    """
    Sanitize and validate text input.
    
    Args:
        text: Input text to sanitize
        field_name: Name of the field (for logging)
        max_length: Maximum allowed length
        
    Returns:
        Sanitized text or None
    """
    if not text:
        return None
    
    # Convert to string and strip whitespace
    text = str(text).strip()
    
    # Check length
    if len(text) > max_length:
        logging.warning(f"{field_name} exceeded max length ({len(text)} > {max_length})")
        text = text[:max_length]
    
    # Remove null bytes and other control characters
    text = ''.join(char for char in text if char.isprintable() or char.isspace())
    
    return text if text else None

def check_rate_limit(identifier):
    """
    Check if request should be rate limited.
    
    Args:
        identifier: IP address or user identifier
        
    Returns:
        tuple: (is_allowed, retry_after_seconds)
    """
    now = datetime.now()
    cutoff = now - timedelta(minutes=1)
    
    # Clean old entries
    _request_counts[identifier] = [
        req_time for req_time in _request_counts[identifier]
        if req_time > cutoff
    ]
    
    # Check limit
    if len(_request_counts[identifier]) >= MAX_REQUESTS_PER_MINUTE:
        oldest = min(_request_counts[identifier])
        retry_after = int((oldest + timedelta(minutes=1) - now).total_seconds())
        return False, retry_after
    
    # Add current request
    _request_counts[identifier].append(now)
    return True, 0

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

def map_knee_pain_to_notion(knee_pain_value):
    """Map knee pain numeric value to Notion select option."""
    if not knee_pain_value:
        return None
    
    try:
        pain_level = int(knee_pain_value)
        pain_mapping = {
            0: "None 🥳",
            1: "🔥",
            2: "🔥🔥",
            3: "🔥🔥🔥",
            4: "🔥🔥🔥🔥",
            5: "🔥🔥🔥🔥🔥"
        }
        return pain_mapping.get(pain_level)
    except (ValueError, TypeError):
        logging.warning(f"Invalid knee pain value: {knee_pain_value}")
        return None

def add_to_notion_database(workout_data, knee_pain, comment, blob_url=None):
    """Add workout entry to Notion database."""
    notion_api_key = os.environ.get("NOTION_API_KEY")
    notion_database_id = os.environ.get("NOTION_DATABASE_ID")
    
    if not notion_api_key or not notion_database_id:
        raise ValueError("NOTION_API_KEY and NOTION_DATABASE_ID environment variables must be set")
    
    # Prepare Notion API headers
    headers = {
        "Authorization": f"Bearer {notion_api_key}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    
    # Build properties according to field mapping
    properties = {
        "Time (min)": {
            "number": workout_data.get("duration")
        },
        "Distance": {
            "number": workout_data.get("distance")
        },
        "Avg. Cadence (SPM)": {
            "number": workout_data.get("cadence")
        },
        "Avg. BPM": {
            "number": workout_data.get("bpm")
        },
        "Date": {
            "date": {
                "start": workout_data.get("date")
            }
        }
    }
    
    # Add knee pain if provided
    knee_pain_option = map_knee_pain_to_notion(knee_pain)
    if knee_pain_option:
        properties["Knee Pain"] = {
            "select": {
                "name": knee_pain_option
            }
        }
    
    # Add comment if provided
    if comment:
        properties["Comment"] = {
            "rich_text": [
                {
                    "text": {
                        "content": comment
                    }
                }
            ]
        }
    
    # Add blob URL if provided
    if blob_url:
        properties["Image Blob URL"] = {
            "url": blob_url
        }
    
    # Prepare the request payload
    payload = {
        "parent": {
            "database_id": notion_database_id
        },
        "properties": properties
    }
    
    # Make the API request to create a page in the database
    response = requests.post(
        "https://api.notion.com/v1/pages",
        headers=headers,
        json=payload
    )
    
    if response.status_code != 200:
        logging.error(f"Notion API error: {response.status_code} - {response.text}")
        response.raise_for_status()
    
    return response.json()

@app.route(route="workout_webhook", methods=["POST"])
def workout_webhook(req: func.HttpRequest) -> func.HttpResponse:
    """
    Webhook endpoint to receive workout data from iOS Shortcuts.
    Accepts multipart/form-data with:
    - knee_pain: text field
    - comment: text field
    - screenshot: image file
    """
    logging.info('Workout webhook received.')
    
    try:
        # Validate request size
        content_length = req.headers.get('Content-Length')
        if content_length:
            content_length_int = int(content_length)
            if content_length_int > MAX_REQUEST_SIZE:
                logging.warning(f"Request too large: {content_length_int} bytes")
                return func.HttpResponse(
                    f"Request too large. Maximum size is {MAX_REQUEST_SIZE / (1024*1024):.0f}MB",
                    status_code=413
                )
        
        # Rate limiting check
        client_ip = req.headers.get('X-Forwarded-For', 'unknown').split(',')[0].strip()
        is_allowed, retry_after = check_rate_limit(client_ip)
        if not is_allowed:
            logging.warning(f"Rate limit exceeded for {client_ip}")
            return func.HttpResponse(
                f"Rate limit exceeded. Retry after {retry_after} seconds.",
                status_code=429,
                headers={'Retry-After': str(retry_after)}
            )
        
        # Log request details
        logging.info(f"Content-Type: {req.headers.get('Content-Type')}")
        logging.info(f"Content-Length: {req.headers.get('Content-Length')}")
        
        # Extract form fields
        knee_pain = sanitize_text_input(req.form.get('knee_pain'), 'knee_pain', max_length=10)
        comment = sanitize_text_input(req.form.get('comment'), 'comment', max_length=500)
        
        # Validate knee_pain is numeric if provided
        if knee_pain:
            try:
                pain_value = int(knee_pain)
                if pain_value < 0 or pain_value > 5:
                    logging.warning(f"Invalid knee pain value: {pain_value}")
                    return func.HttpResponse(
                        "Knee pain must be between 0 and 5",
                        status_code=400
                    )
            except ValueError:
                logging.warning(f"Knee pain is not a valid number: {knee_pain}")
                return func.HttpResponse(
                    "Knee pain must be a number",
                    status_code=400
                )
        
        # Log form data
        logging.info(f"Knee Pain: {knee_pain}")
        logging.info(f"Comment: {comment}")
        
        # Extract file upload
        screenshot = req.files.get('screenshot')
        
        if not screenshot:
            logging.error("No screenshot file found in request")
            return func.HttpResponse(
                "Screenshot is required",
                status_code=400
            )
        
        # Validate file size
        is_valid, error_msg = validate_file_upload(screenshot, req)
        if not is_valid:
            logging.warning(f"File validation failed: {error_msg}")
            return func.HttpResponse(error_msg, status_code=400)
        
        # Validate file type (magic bytes)
        is_valid, error_msg, img_type = validate_image_file(screenshot, screenshot.filename)
        if not is_valid:
            logging.warning(f"Image validation failed: {error_msg}")
            return func.HttpResponse(error_msg, status_code=400)
        
        logging.info(f"Image type validated: {img_type}")
        
        # Log file information
        logging.info(f"Screenshot filename: {screenshot.filename}")
        logging.info(f"Screenshot content type: {screenshot.content_type}")
        
        # Read image data
        image_data = screenshot.stream.read()
        logging.info(f"Screenshot size: {len(image_data)} bytes")
        
        # Generate filename with timestamp and UUID
        timestamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
        unique_id = str(uuid.uuid4())
        file_extension = os.path.splitext(screenshot.filename)[1] or '.jpg'
        blob_filename = f"{timestamp}_{unique_id}{file_extension}"
        
        # Upload image to blob storage
        blob_url = upload_image_to_blob_storage(image_data, blob_filename)
        if blob_url:
            logging.info(f"Image uploaded to blob storage: {blob_url}")
        else:
            logging.warning("Failed to upload image to blob storage, continuing without blob URL")
        
        # Encode image to base64
        base64_image = base64.b64encode(image_data).decode('utf-8')
        
        # Get Azure OpenAI client and deployment name
        try:
            client = get_openai_client()
            deployment_name = os.environ.get("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o-mini")
        except Exception as e:
            logging.error(f"Failed to initialize Azure OpenAI client: {str(e)}")
            return func.HttpResponse(
                f"Configuration error: {str(e)}",
                status_code=500
            )
        
        # Call Azure OpenAI to analyze the image
        try:
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
            
            # Parse and validate the JSON response
            try:
                workout_data = json.loads(ai_response)
                
                # Validate required fields
                required_fields = ["duration", "distance", "cadence", "bpm", "date"]
                missing_fields = [field for field in required_fields if field not in workout_data]
                
                if missing_fields:
                    logging.warning(f"Missing fields in AI response: {missing_fields}")
                    return func.HttpResponse(
                        f"AI response missing required fields: {missing_fields}",
                        status_code=500
                    )
                
                # Log parsed workout data
                logging.info("=== Parsed Workout Data ===")
                logging.info(f"Duration: {workout_data['duration']} minutes")
                logging.info(f"Distance: {workout_data['distance']} km")
                logging.info(f"Cadence: {workout_data['cadence']}")
                logging.info(f"Heart Rate: {workout_data['bpm']} bpm")
                logging.info(f"Date: {workout_data['date']}")
                
                # Also log additional form data if present
                if knee_pain:
                    logging.info(f"Knee Pain: {knee_pain}")
                if comment:
                    logging.info(f"Comment: {comment}")
                
                logging.info("=========================")
                
                # Add to Notion database
                try:
                    logging.info("Adding workout entry to Notion database...")
                    notion_response = add_to_notion_database(workout_data, knee_pain, comment, blob_url)
                    notion_page_id = notion_response.get("id")
                    logging.info(f"Successfully created Notion page: {notion_page_id}")
                    
                    # Prepare response data
                    response_data = {
                        "status": "success",
                        "message": "Workout data processed and added to Notion successfully",
                        "data": workout_data,
                        "notion_page_id": notion_page_id
                    }
                    
                    # Include additional fields in response
                    if knee_pain:
                        response_data["data"]["knee_pain"] = knee_pain
                    if comment:
                        response_data["data"]["comment"] = comment
                    if blob_url:
                        response_data["data"]["image_blob_url"] = blob_url
                    
                    return func.HttpResponse(
                        json.dumps(response_data, indent=2),
                        status_code=200,
                        mimetype="application/json"
                    )
                    
                except Exception as e:
                    logging.error(f"Error adding to Notion: {str(e)}", exc_info=True)
                    return func.HttpResponse(
                        json.dumps({
                            "status": "partial_success",
                            "message": "Workout data processed but failed to add to Notion",
                            "data": workout_data,
                            "error": str(e)
                        }, indent=2),
                        status_code=500,
                        mimetype="application/json"
                    )
                
            except json.JSONDecodeError as e:
                logging.error(f"Failed to parse AI response as JSON: {str(e)}")
                logging.error(f"AI response was: {ai_response}")
                return func.HttpResponse(
                    f"Failed to parse AI response as JSON: {str(e)}",
                    status_code=500
                )
        
        except Exception as e:
            logging.error(f"Error calling Azure OpenAI: {str(e)}", exc_info=True)
            return func.HttpResponse(
                f"Error analyzing image: {str(e)}",
                status_code=500
            )
    
    except Exception as e:
        logging.error(f"Error processing webhook: {str(e)}", exc_info=True)
        return func.HttpResponse(
            f"Error processing webhook: {str(e)}",
            status_code=500
        )