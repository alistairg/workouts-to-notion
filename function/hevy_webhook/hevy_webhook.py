"""Main webhook handler for processing Hevy workout data (4-database schema)."""

import azure.functions as func
import logging
import os
import json
import asyncio
import aiohttp
from datetime import datetime
from typing import Optional

from shared.validators import sanitize_text_input, MAX_REQUEST_SIZE


def hevy_workout_webhook(req: func.HttpRequest) -> func.HttpResponse:
    """
    Webhook endpoint to receive workout data from Hevy app.

    Accepts JSON payload with:
    - id: webhook event ID
    - payload.workoutId: UUID of the workout

    Requires Authorization header with Bearer token matching WEBHOOK_AUTH_TOKEN.

    Returns:
        JSON response with processing status
    """
    logging.info('Hevy webhook received.')

    try:
        # Validate authorization
        webhook_auth_token = os.environ.get("WEBHOOK_AUTH_TOKEN")
        if webhook_auth_token:
            auth_header = req.headers.get("Authorization", "")
            expected_auth = f"Bearer {webhook_auth_token}"
            if auth_header != expected_auth:
                logging.warning("Unauthorized webhook request - invalid or missing Authorization header")
                return func.HttpResponse(
                    "Unauthorized",
                    status_code=401
                )
        else:
            logging.warning("WEBHOOK_AUTH_TOKEN not configured - webhook is unprotected!")

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
        notion_routines_db_id = os.environ.get("NOTION_ROUTINES_DATABASE_ID")
        notion_templates_db_id = os.environ.get("NOTION_EXERCISE_TEMPLATES_DATABASE_ID")
        notion_sets_db_id = os.environ.get("NOTION_SETS_DATABASE_ID")

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

        # Run the async processing
        try:
            result = asyncio.run(
                process_workout_webhook(
                    workout_id,
                    webhook_id,
                    notion_api_key,
                    notion_workouts_db_id,
                    notion_routines_db_id,
                    notion_templates_db_id,
                    notion_sets_db_id
                )
            )
        except Exception as e:
            logging.error(f"Error processing workout: {str(e)}", exc_info=True)
            return func.HttpResponse(
                f"Failed to process workout: {str(e)}",
                status_code=500
            )

        logging.info(f"Hevy webhook processed successfully: {webhook_id}")

        return func.HttpResponse(
            json.dumps(result),
            status_code=200,
            mimetype="application/json"
        )

    except Exception as e:
        logging.error(f"Unexpected error processing Hevy webhook: {str(e)}", exc_info=True)
        return func.HttpResponse(
            "Internal server error",
            status_code=500
        )


async def process_workout_webhook(
    workout_id: str,
    webhook_id: str,
    notion_api_key: str,
    workouts_db_id: str,
    routines_db_id: Optional[str],
    templates_db_id: Optional[str],
    sets_db_id: Optional[str]
) -> dict:
    """
    Process a workout webhook asynchronously.

    Args:
        workout_id: Hevy workout ID
        webhook_id: Webhook event ID
        notion_api_key: Notion API key
        workouts_db_id: Workouts database ID
        routines_db_id: Routines database ID (optional)
        templates_db_id: Exercise Templates database ID (optional)
        sets_db_id: Sets database ID (optional)

    Returns:
        Result dictionary with processing stats
    """
    from .hevy_api import (
        get_workout_and_routine_async,
        get_exercise_templates_async,
        extract_unique_exercises
    )
    from .notion_handler import (
        upsert_workout,
        upsert_routine,
        sync_exercise_templates,
        sync_workout_sets
    )

    async with aiohttp.ClientSession() as session:
        # Fetch workout and routine from Hevy
        logging.info(f"Fetching workout and routine details from Hevy API: {workout_id}")
        workout_data, routine_data = await get_workout_and_routine_async(workout_id)

        if not workout_data:
            raise ValueError(f"Failed to fetch workout data for ID: {workout_id}")

        # Track results
        routine_page_id = None
        template_count = 0
        template_mapping = {}
        set_count = 0

        # Sync routine if available
        if routine_data and routines_db_id:
            logging.info(f"Syncing routine: {routine_data.get('title', 'Unknown')}")
            routine_page_id = await upsert_routine(
                routine_data, session, notion_api_key, routines_db_id
            )

        # Extract and sync exercise templates
        if templates_db_id:
            unique_exercises = extract_unique_exercises(workout_data)
            if unique_exercises:
                exercise_template_ids = [ex["exercise_template_id"] for ex in unique_exercises]
                logging.info(f"Fetching {len(exercise_template_ids)} exercise templates")

                exercise_templates = await get_exercise_templates_async(exercise_template_ids)
                if exercise_templates:
                    template_count, template_mapping = await sync_exercise_templates(
                        exercise_templates, session, notion_api_key, templates_db_id
                    )

        # Upsert the workout
        logging.info(f"Syncing workout: {workout_data.get('title', 'Workout')}")
        workout_page_id = await upsert_workout(
            workout_data, session, notion_api_key, workouts_db_id, routine_page_id
        )

        if not workout_page_id:
            raise ValueError("Failed to create/update workout in Notion")

        # Sync all sets if sets database is configured
        if sets_db_id and workout_page_id:
            exercises = workout_data.get("exercises", [])
            set_count = await sync_workout_sets(
                workout_data.get("id", ""),
                workout_page_id,
                exercises,
                session,
                notion_api_key,
                sets_db_id,
                template_mapping
            )
            logging.info(f"Synced {set_count} sets")

        return {
            "status": "success",
            "webhook_id": webhook_id,
            "workout_id": workout_id,
            "notion_page_id": workout_page_id,
            "routine_name": routine_data.get("title") if routine_data else None,
            "routine_page_id": routine_page_id,
            "exercise_templates_synced": template_count,
            "sets_synced": set_count,
            "message": "Workout successfully synced to Notion",
            "timestamp": datetime.utcnow().isoformat()
        }
