"""
Azure Functions App Entry Point
================================
This module serves as the main entry point for Azure Functions.
The actual business logic is organized in the running-webhook and hevy-webhook packages.
"""

import azure.functions as func
from running_webhook import workout_webhook as running_webhook_handler
from hevy_webhook import hevy_workout_webhook as hevy_webhook_handler
from full_sync import full_sync_handler, debug_sets_handler

# Initialize Azure Functions app
app = func.FunctionApp(http_auth_level=func.AuthLevel.FUNCTION)


@app.route(route="workout_webhook", methods=["POST"])
def workout_webhook(req: func.HttpRequest) -> func.HttpResponse:
    """
    Webhook endpoint to receive running workout data from iOS Shortcuts.
    
    This is the main entry point that delegates to the running_webhook handler.
    
    Accepts multipart/form-data with:
    - knee_pain: text field (0-5)
    - comment: text field5
    - screenshot: image file
    
    Returns:
        JSON response with workout data and Notion page ID
    """
    return running_webhook_handler(req)


@app.route(route="hevy_webhook", methods=["POST"], auth_level=func.AuthLevel.ANONYMOUS)
def hevy_webhook(req: func.HttpRequest) -> func.HttpResponse:
    """
    Webhook endpoint to receive workout data from Hevy app.

    This is the main entry point that delegates to the hevy_webhook handler.

    Accepts JSON payload with:
    - id: webhook event ID (string)
    - payload.workoutId: UUID of the workout (string)

    Returns:
        JSON response with processing status
    """
    return hevy_webhook_handler(req)


@app.route(route="full_sync", methods=["POST"])
def full_sync(req: func.HttpRequest) -> func.HttpResponse:
    """
    Manual full sync endpoint for Notion button.

    Syncs all data from Hevy to Notion in order:
    1. Exercise Templates
    2. Routines
    3. Workouts + Sets

    Returns:
        JSON response with sync statistics
    """
    return full_sync_handler(req)


@app.route(route="debug_sets", methods=["POST"])
def debug_sets(req: func.HttpRequest) -> func.HttpResponse:
    """
    Debug endpoint for testing sets sync.

    Fetches one workout and tries to create exactly ONE set.
    Returns detailed info about what properties are being sent
    and what Notion responds with.

    Use this to debug property name mismatches.
    """
    return debug_sets_handler(req)