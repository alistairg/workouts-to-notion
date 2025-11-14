"""Main webhook handler for processing running workout data."""

import azure.functions as func
import logging
import os
import json
import uuid
from datetime import datetime

from shared.validators import (
    validate_file_upload,
    validate_image_file,
    sanitize_text_input,
    MAX_REQUEST_SIZE
)
from shared.rate_limiter import check_rate_limit
from .image_handler import upload_image_to_blob_storage
from .openai_handler import analyze_workout_image
from .notion_handler import add_to_notion_database


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
        
        # Analyze image with Azure OpenAI
        try:
            ai_response = analyze_workout_image(image_data)
            
            if not ai_response:
                logging.error("No response from Azure OpenAI")
                return func.HttpResponse(
                    "Failed to get response from AI service",
                    status_code=500
                )
            
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
