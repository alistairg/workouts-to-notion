"""Manual full sync endpoint for Notion button."""

import azure.functions as func
import asyncio
import aiohttp
import logging
import json
import os
from datetime import datetime
from typing import Optional, List, Dict, Any


def full_sync_handler(req: func.HttpRequest) -> func.HttpResponse:
    """
    Full sync endpoint: Exercise Templates -> Routines -> Workouts + Sets.

    This endpoint is designed to be triggered from a Notion button or
    manual API call to perform a complete sync of all Hevy data.

    Returns:
        JSON response with sync statistics
    """
    logging.info("Full sync requested")

    try:
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
                json.dumps({"error": "HEVY_API_KEY not configured"}),
                status_code=500,
                mimetype="application/json"
            )

        if not notion_api_key:
            logging.error("NOTION_API_KEY not configured")
            return func.HttpResponse(
                json.dumps({"error": "NOTION_API_KEY not configured"}),
                status_code=500,
                mimetype="application/json"
            )

        if not notion_workouts_db_id:
            logging.error("NOTION_WORKOUTS_DATABASE_ID not configured")
            return func.HttpResponse(
                json.dumps({"error": "NOTION_WORKOUTS_DATABASE_ID not configured"}),
                status_code=500,
                mimetype="application/json"
            )

        # Run the async full sync
        try:
            result = asyncio.run(
                perform_full_sync(
                    notion_api_key,
                    notion_workouts_db_id,
                    notion_routines_db_id,
                    notion_templates_db_id,
                    notion_sets_db_id
                )
            )
        except Exception as e:
            logging.error(f"Error during full sync: {str(e)}", exc_info=True)
            return func.HttpResponse(
                json.dumps({
                    "status": "error",
                    "error": str(e),
                    "timestamp": datetime.utcnow().isoformat()
                }),
                status_code=500,
                mimetype="application/json"
            )

        logging.info("Full sync completed successfully")

        return func.HttpResponse(
            json.dumps(result),
            status_code=200,
            mimetype="application/json"
        )

    except Exception as e:
        logging.error(f"Unexpected error during full sync: {str(e)}", exc_info=True)
        return func.HttpResponse(
            json.dumps({
                "status": "error",
                "error": "Internal server error",
                "timestamp": datetime.utcnow().isoformat()
            }),
            status_code=500,
            mimetype="application/json"
        )


async def perform_full_sync(
    notion_api_key: str,
    workouts_db_id: str,
    routines_db_id: Optional[str],
    templates_db_id: Optional[str],
    sets_db_id: Optional[str]
) -> dict:
    """
    Perform a full sync of all Hevy data to Notion.

    Sync order:
    1. Exercise Templates (these are referenced by Sets)
    2. Routines (these are referenced by Workouts)
    3. Workouts + Sets (workouts reference routines, sets reference templates)

    Args:
        notion_api_key: Notion API key
        workouts_db_id: Workouts database ID
        routines_db_id: Routines database ID (optional)
        templates_db_id: Exercise Templates database ID (optional)
        sets_db_id: Sets database ID (optional)

    Returns:
        Dictionary with sync statistics
    """
    from hevy_webhook.hevy_api import (
        get_all_exercise_templates,
        get_all_routines,
        get_all_workouts
    )
    from hevy_webhook.notion_handler import (
        sync_exercise_templates,
        sync_routines,
        sync_workouts_and_sets
    )

    start_time = datetime.utcnow()
    template_count = 0
    routine_count = 0
    workout_count = 0
    set_count = 0
    template_mapping = {}
    routine_mapping = {}

    async with aiohttp.ClientSession() as session:
        # Step 1: Sync Exercise Templates
        if templates_db_id:
            logging.info("Fetching all exercise templates from Hevy...")
            templates = await get_all_exercise_templates()
            logging.info(f"Found {len(templates)} exercise templates")

            if templates:
                template_count, template_mapping = await sync_exercise_templates(
                    templates, session, notion_api_key, templates_db_id
                )
                logging.info(f"Synced {template_count} exercise templates")

        # Step 2: Sync Routines
        if routines_db_id:
            logging.info("Fetching all routines from Hevy...")
            routines = await get_all_routines()
            logging.info(f"Found {len(routines)} routines")

            if routines:
                routine_count, routine_mapping = await sync_routines(
                    routines, session, notion_api_key, routines_db_id
                )
                logging.info(f"Synced {routine_count} routines")

        # Step 3: Sync Workouts and Sets
        logging.info("Fetching all workouts from Hevy...")
        workouts = await get_all_workouts()
        logging.info(f"Found {len(workouts)} workouts")

        if workouts:
            workout_count, set_count = await sync_workouts_and_sets(
                workouts,
                session,
                notion_api_key,
                workouts_db_id,
                sets_db_id,
                routine_mapping,
                template_mapping
            )
            logging.info(f"Synced {workout_count} workouts and {set_count} sets")

    end_time = datetime.utcnow()
    duration_seconds = (end_time - start_time).total_seconds()

    return {
        "status": "success",
        "exercise_templates": template_count,
        "routines": routine_count,
        "workouts": workout_count,
        "sets": set_count,
        "duration_seconds": round(duration_seconds, 2),
        "timestamp": end_time.isoformat()
    }


def debug_sets_handler(req: func.HttpRequest) -> func.HttpResponse:
    """
    Debug endpoint to sync sets from a single workout.

    Fetches one workout and tries to create just ONE set to debug property mappings.

    Returns:
        JSON response with the set data being sent and any errors
    """
    logging.info("Debug sets sync requested")

    try:
        notion_api_key = os.environ.get("NOTION_API_KEY")
        notion_sets_db_id = os.environ.get("NOTION_SETS_DATABASE_ID")

        if not notion_api_key or not notion_sets_db_id:
            return func.HttpResponse(
                json.dumps({"error": "Missing NOTION_API_KEY or NOTION_SETS_DATABASE_ID"}),
                status_code=500,
                mimetype="application/json"
            )

        try:
            result = asyncio.run(
                perform_debug_set_sync(notion_api_key, notion_sets_db_id)
            )
        except Exception as e:
            logging.error(f"Error during debug sync: {str(e)}", exc_info=True)
            return func.HttpResponse(
                json.dumps({
                    "status": "error",
                    "error": str(e),
                    "timestamp": datetime.utcnow().isoformat()
                }),
                status_code=500,
                mimetype="application/json"
            )

        return func.HttpResponse(
            json.dumps(result, indent=2),
            status_code=200,
            mimetype="application/json"
        )

    except Exception as e:
        logging.error(f"Unexpected error: {str(e)}", exc_info=True)
        return func.HttpResponse(
            json.dumps({"status": "error", "error": str(e)}),
            status_code=500,
            mimetype="application/json"
        )


async def perform_debug_set_sync(notion_api_key: str, sets_db_id: str) -> dict:
    """
    Fetch one workout and try to create exactly one set for debugging.

    Returns detailed info about what we're trying to send.
    """
    from hevy_webhook.hevy_api import get_all_workouts, get_all_exercise_templates
    from hevy_webhook.notion_handler import get_notion_headers, sync_exercise_templates

    # First, build the template mapping by syncing templates
    templates_db_id = os.environ.get("NOTION_EXERCISE_TEMPLATES_DATABASE_ID")

    # Fetch workouts
    workouts = await get_all_workouts()
    if not workouts:
        return {"error": "No workouts found"}

    # Get first workout with exercises
    workout = None
    for w in workouts:
        workout_data = w.get("workout", w)
        exercises = workout_data.get("exercises", [])
        if exercises and exercises[0].get("sets"):
            workout = workout_data
            break

    if not workout:
        return {"error": "No workout with sets found"}

    # Extract first exercise and first set
    exercise = workout["exercises"][0]
    set_data = exercise["sets"][0]
    workout_id = workout.get("id", "unknown")

    # Build the properties we'd send
    composite_set_id = f"{workout_id}-0-0"
    exercise_name = exercise.get("title", "Unknown Exercise")
    set_type = set_data.get("set_type", "normal")
    weight_kg = set_data.get("weight_kg")
    reps = set_data.get("reps")

    properties = {
        "Exercise Name": {
            "title": [{"text": {"content": exercise_name}}]
        },
        "Hevy ID": {
            "rich_text": [{"text": {"content": composite_set_id}}]
        },
        "Exercise Order": {
            "number": 1
        },
        "Set Number": {
            "number": 1
        },
        "Set Type": {
            "select": {"name": set_type}
        },
        "Last Synced": {
            "date": {"start": datetime.utcnow().isoformat()}
        }
    }

    if weight_kg is not None:
        weight_lbs = float(weight_kg) * 2.20462
        properties["Weight (lb)"] = {"number": round(weight_lbs, 2)}

    if reps is not None:
        properties["Reps"] = {"number": int(reps)}

    # Try to create the page
    async with aiohttp.ClientSession() as session:
        headers = get_notion_headers(notion_api_key)
        payload = {
            "parent": {"database_id": sets_db_id},
            "properties": properties
        }

        async with session.post(
            "https://api.notion.com/v1/pages",
            headers=headers,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=30)
        ) as response:
            response_text = await response.text()

            # Get the exercise_template_id from the exercise
            exercise_template_id = exercise.get("exercise_template_id", "NOT_FOUND")

            return {
                "workout_id": workout_id,
                "workout_title": workout.get("title", "Unknown"),
                "exercise_name": exercise_name,
                "exercise_template_id": exercise_template_id,
                "full_exercise_data": exercise,  # Show all exercise fields
                "set_data_from_hevy": {
                    "set_type": set_type,
                    "weight_kg": weight_kg,
                    "weight_lbs": round(float(weight_kg) * 2.20462, 2) if weight_kg else None,
                    "reps": reps
                },
                "properties_sent_to_notion": properties,
                "notion_response_status": response.status,
                "notion_response": json.loads(response_text) if response_text else None
            }
