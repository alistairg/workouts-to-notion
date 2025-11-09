"""Main webhook handler for processing Hevy workout data."""

import azure.functions as func
import logging
import os
import json
from datetime import datetime

from shared.validators import sanitize_text_input, MAX_REQUEST_SIZE
from shared.rate_limiter import check_rate_limit


def hevy_workout_webhook(req: func.HttpRequest) -> func.HttpResponse:
    """
    Webhook endpoint to receive workout data from Hevy app.
    
    Accepts JSON payload with:
    - id: webhook event ID
    - payload.workoutId: UUID of the workout
    
    Returns:
        JSON response with processing status
    """
    logging.info('Hevy webhook received.')
    
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
                headers={"Retry-After": str(retry_after)}
            )
        
        # Parse JSON payload
        try:
            req_body = req.get_json()
        except ValueError:
            logging.error("Invalid JSON payload")
            return func.HttpResponse(
                "Invalid JSON payload",
                status_code=400
            )
        
        # Validate required fields
        webhook_id = req_body.get('id')
        payload = req_body.get('payload', {})
        workout_id = payload.get('workoutId')
        
        if not webhook_id or not workout_id:
            logging.error("Missing required fields in webhook payload")
            return func.HttpResponse(
                "Missing required fields: 'id' and 'payload.workoutId' are required",
                status_code=400
            )
        
        # Sanitize inputs
        webhook_id = sanitize_text_input(webhook_id, "webhook_id", max_length=100)
        workout_id = sanitize_text_input(workout_id, "workout_id", max_length=100)
        
        logging.info(f"Processing Hevy webhook - ID: {webhook_id}, Workout ID: {workout_id}")
        
        # Check for required environment variables
        hevy_api_key = os.environ.get("HEVY_API_KEY")
        notion_api_key = os.environ.get("NOTION_API_KEY")
        notion_workouts_db_id = os.environ.get("NOTION_WORKOUTS_DATABASE_ID")
        
        if not hevy_api_key:
            logging.error("HEVY_API_KEY not configured")
            return func.HttpResponse(
                "Server configuration error: HEVY_API_KEY not set",
                status_code=500
            )
        
        if not notion_api_key or not notion_workouts_db_id:
            logging.error("Notion environment variables not configured")
            return func.HttpResponse(
                "Server configuration error: NOTION_API_KEY or NOTION_WORKOUTS_DATABASE_ID not set",
                status_code=500
            )
        
        # Import handlers (done here to avoid import errors during validation)
        import asyncio
        from .hevy_api import (
            get_workout_and_routine_async, 
            get_exercise_templates_async,
            extract_unique_exercises,
            extract_exercise_performances,
            calculate_workout_duration
        )
        from .notion_handler import (
            add_workout_to_notion, 
            process_exercises_async,
            process_exercise_performances_async
        )
        
        # Fetch workout and routine in parallel
        logging.info(f"Fetching workout and routine details from Hevy API: {workout_id}")
        try:
            workout_data, routine_data = asyncio.run(get_workout_and_routine_async(workout_id))
        except Exception as e:
            logging.error(f"Error fetching workout/routine data: {str(e)}")
            return func.HttpResponse(
                "Failed to fetch workout data from Hevy API",
                status_code=502
            )
        
        if not workout_data:
            logging.error(f"Failed to fetch workout data for ID: {workout_id}")
            return func.HttpResponse(
                "Failed to fetch workout data from Hevy API",
                status_code=502
            )
        
        # Extract routine name if available
        routine_name = None
        if routine_data:
            routine_name = routine_data.get("title")
            logging.info(f"Retrieved routine name: {routine_name}")
        
        # Calculate duration if not present
        if "duration_seconds" not in workout_data:
            duration = calculate_workout_duration(workout_data)
            if duration:
                workout_data["duration_seconds"] = duration * 60  # Convert back to seconds
        
        # Extract unique exercises and fetch templates in parallel
        unique_exercises = extract_unique_exercises(workout_data)
        logging.info(f"Found {len(unique_exercises)} unique exercises in workout")
        
        processed_exercises = []
        
        if unique_exercises:
            # Extract exercise template IDs
            exercise_template_ids = [ex["exercise_template_id"] for ex in unique_exercises]
            
            # Fetch all exercise templates in parallel
            logging.info(f"Fetching {len(exercise_template_ids)} exercise templates in parallel")
            try:
                exercise_templates = asyncio.run(get_exercise_templates_async(exercise_template_ids))
                logging.info(f"Successfully fetched {len(exercise_templates)} exercise templates")
            except Exception as e:
                logging.error(f"Error fetching exercise templates: {str(e)}")
                exercise_templates = []
            
            # Process all exercises in parallel with Notion
            if exercise_templates:
                logging.info(f"Processing {len(exercise_templates)} exercises in Notion (parallel)")
                try:
                    processed_exercises = asyncio.run(process_exercises_async(exercise_templates))
                    logging.info(f"Successfully processed {len(processed_exercises)} exercises in Notion")
                except Exception as e:
                    logging.error(f"Error processing exercises in Notion: {str(e)}")
                    processed_exercises = []
        
        logging.info(f"Successfully processed {len(processed_exercises)} exercises")
        
        # Create or update Notion page with workout data
        try:
            logging.info("Creating or updating Notion page for workout")
            notion_response = add_workout_to_notion(workout_data, routine_name)
            notion_page_id = notion_response.get("id")
            
            # Determine if it was created or updated based on the response
            # Notion returns 'created_time' and 'last_edited_time' in the response
            created_time = notion_response.get("created_time", "")
            last_edited_time = notion_response.get("last_edited_time", "")
            was_updated = created_time != last_edited_time
            
            action = "updated" if was_updated else "created"
            logging.info(f"Successfully {action} Notion page: {notion_page_id}")
            
            # Process exercise performances in parallel
            processed_performances = []
            exercise_performances = extract_exercise_performances(workout_data)
            
            if exercise_performances and processed_exercises:
                # Build mapping from exercise_template_id to Notion page ID
                exercise_id_to_page = {
                    ex["exercise_template_id"]: ex["notion_page_id"]
                    for ex in processed_exercises
                    if ex.get("notion_page_id")
                }
                
                logging.info(f"Processing {len(exercise_performances)} exercise performances in parallel")
                try:
                    processed_performances = asyncio.run(
                        process_exercise_performances_async(
                            exercise_performances,
                            notion_page_id,
                            exercise_id_to_page
                        )
                    )
                    logging.info(f"Successfully processed {len(processed_performances)} exercise performances")
                except Exception as e:
                    logging.error(f"Error processing exercise performances: {str(e)}")
                    processed_performances = []
            
            response_data = {
                "status": "success",
                "webhook_id": webhook_id,
                "workout_id": workout_id,
                "notion_page_id": notion_page_id,
                "routine_name": routine_name,
                "exercises_processed": len(processed_exercises),
                "exercises": processed_exercises,
                "performances_processed": len(processed_performances),
                "performances": processed_performances,
                "action": action,
                "message": f"Workout successfully {action} in Notion",
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logging.error(f"Failed to create Notion page: {str(e)}")
            return func.HttpResponse(
                f"Failed to create Notion page: {str(e)}",
                status_code=500
            )
        
        logging.info(f"Hevy webhook processed successfully: {webhook_id}")
        
        return func.HttpResponse(
            json.dumps(response_data),
            status_code=200,
            mimetype="application/json"
        )
        
    except Exception as e:
        logging.error(f"Unexpected error processing Hevy webhook: {str(e)}", exc_info=True)
        return func.HttpResponse(
            "Internal server error",
            status_code=500
        )
