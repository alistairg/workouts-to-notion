#!/usr/bin/env python3
"""
Script to sync historical Hevy workouts to Notion via the Azure Function App.

This script fetches all workouts from Hevy API since a specified date and
sends them to the Function App webhook for processing.
"""

import os
import sys
import requests
import time
from datetime import datetime
from typing import List, Dict, Any, Optional

# Configuration
HEVY_API_KEY = os.environ.get("HEVY_API_KEY", "")
FUNCTION_APP_URL = ""
START_DATE = "2024-10-20"  # October 20, 2024

# API settings
HEVY_API_BASE = "https://api.hevyapp.com/v1"
REQUEST_TIMEOUT = 30
RATE_LIMIT_DELAY = 1  # Delay between requests to avoid rate limiting


def fetch_workouts_from_hevy(start_date: str, api_key: str) -> List[Dict[str, Any]]:
    """
    Fetch all workouts from Hevy API since the specified date.
    
    Args:
        start_date: ISO date string (YYYY-MM-DD)
        api_key: Hevy API key
        
    Returns:
        List of workout objects with their IDs
    """
    headers = {
        "api-key": api_key,
        "Content-Type": "application/json"
    }
    
    workouts = []
    page = 1
    page_size = 10  # Hevy API maximum page size
    
    print(f"Fetching workouts from Hevy API since {start_date}...")
    
    while True:
        try:
            response = requests.get(
                f"{HEVY_API_BASE}/workouts",
                headers=headers,
                params={
                    "page": page,
                    "pageSize": page_size
                },
                timeout=REQUEST_TIMEOUT
            )
            
            if response.status_code != 200:
                print(f"Error fetching workouts: {response.status_code} - {response.text}")
                break
            
            data = response.json()
            page_workouts = data.get("workouts", [])
            
            if not page_workouts:
                break
            
            # Filter workouts by date
            start_datetime = datetime.fromisoformat(start_date + "T00:00:00+00:00")
            for workout in page_workouts:
                workout_date_str = workout.get("start_time", "")
                if workout_date_str:
                    workout_datetime = datetime.fromisoformat(workout_date_str.replace('Z', '+00:00'))
                    if workout_datetime >= start_datetime:
                        workouts.append(workout)
                    else:
                        # Workouts are returned in reverse chronological order
                        # so we can stop once we hit an older date
                        print(f"Reached workouts older than {start_date}, stopping pagination")
                        return workouts
            
            print(f"Fetched page {page}: {len(page_workouts)} workouts (total so far: {len(workouts)})")
            
            # Check if there are more pages
            total = data.get("total", 0)
            if len(workouts) >= total or len(page_workouts) < page_size:
                break
            
            page += 1
            time.sleep(0.5)  # Small delay between pagination requests
            
        except requests.exceptions.RequestException as e:
            print(f"Error fetching workouts from Hevy API: {str(e)}")
            break
    
    print(f"Total workouts fetched: {len(workouts)}")
    return workouts


def send_workout_to_function_app(workout_id: str, function_url: str) -> bool:
    """
    Send a workout ID to the Function App webhook.
    
    Args:
        workout_id: UUID of the workout
        function_url: URL of the Function App webhook
        
    Returns:
        True if successful, False otherwise
    """
    # Mimic the webhook payload structure
    payload = {
        "id": f"manual-sync-{workout_id}",
        "payload": {
            "workoutId": workout_id
        }
    }
    
    try:
        response = requests.post(
            function_url,
            json=payload,
            timeout=REQUEST_TIMEOUT
        )
        
        if response.status_code == 200:
            return True
        else:
            print(f"  Error: {response.status_code} - {response.text[:200]}")
            return False
            
    except requests.exceptions.RequestException as e:
        print(f"  Error sending to Function App: {str(e)}")
        return False


def main():
    """Main function to sync workouts."""
    print("=" * 70)
    print("Hevy Workouts Sync Script")
    print("=" * 70)
    print(f"Start Date: {START_DATE}")
    print(f"Function App URL: {FUNCTION_APP_URL[:60]}...")
    print(f"Hevy API Key: {HEVY_API_KEY[:4]}...{HEVY_API_KEY[-4:]}")
    print("=" * 70)
    print()
    
    # Fetch workouts from Hevy
    workouts = fetch_workouts_from_hevy(START_DATE, HEVY_API_KEY)
    
    if not workouts:
        print("No workouts found to sync.")
        return
    
    print(f"\nFound {len(workouts)} workouts to sync")
    print("-" * 70)
    
    # Send each workout to the Function App
    successful = 0
    failed = 0
    
    for i, workout in enumerate(workouts, 1):
        workout_id = workout.get("id", "")
        workout_date = workout.get("start_time", "unknown")[:10]
        workout_title = workout.get("title", "Unnamed Workout")
        
        print(f"[{i}/{len(workouts)}] Processing workout: {workout_title} ({workout_date})")
        print(f"  Workout ID: {workout_id}")
        
        if send_workout_to_function_app(workout_id, FUNCTION_APP_URL):
            print(f"  ✓ Successfully sent to Function App")
            successful += 1
        else:
            print(f"  ✗ Failed to send to Function App")
            failed += 1
        
        # Rate limiting delay
        if i < len(workouts):
            time.sleep(RATE_LIMIT_DELAY)
    
    # Summary
    print()
    print("=" * 70)
    print("Sync Summary")
    print("=" * 70)
    print(f"Total workouts: {len(workouts)}")
    print(f"Successful: {successful}")
    print(f"Failed: {failed}")
    print("=" * 70)
    
    if failed > 0:
        print("\n⚠️  Some workouts failed to sync. Check the logs above for details.")
        sys.exit(1)
    else:
        print("\n✓ All workouts synced successfully!")
        sys.exit(0)


if __name__ == "__main__":
    main()
