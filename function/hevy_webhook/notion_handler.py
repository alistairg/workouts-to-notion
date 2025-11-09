"""Notion database integration for Hevy workout entries."""

import logging
import os
import requests
import asyncio
import aiohttp
from typing import Dict, Any, Optional, List


def add_workout_to_notion(workout_data: Dict[str, Any], routine_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Add or update a Hevy workout entry in the Notion Workouts database.
    
    If a workout with the same Hevy ID already exists, it will be updated.
    Otherwise, a new workout will be created.
    
    Args:
        workout_data: Workout data from Hevy API
        routine_name: Name of the routine (e.g., "Upper Body 💪")
        
    Returns:
        Response from Notion API
        
    Raises:
        ValueError: If required environment variables are not set
        requests.HTTPError: If Notion API request fails
    """
    notion_api_key = os.environ.get("NOTION_API_KEY")
    notion_workouts_db_id = os.environ.get("NOTION_WORKOUTS_DATABASE_ID")
    
    if not notion_api_key or not notion_workouts_db_id:
        raise ValueError("NOTION_API_KEY and NOTION_WORKOUTS_DATABASE_ID environment variables must be set")
    
    # Prepare Notion API headers
    headers = {
        "Authorization": f"Bearer {notion_api_key}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    
    # Extract workout ID
    workout_id = workout_data.get("id", "")
    
    # Extract and format workout date
    workout_date = None
    start_time = workout_data.get("start_time")
    if start_time:
        # Hevy uses ISO 8601 format
        workout_date = start_time.split('T')[0]  # Extract just the date part
    
    # Calculate duration in minutes
    duration_minutes = None
    if "duration_seconds" in workout_data:
        duration_minutes = workout_data["duration_seconds"] / 60.0
    
    # Build properties according to Notion database schema
    properties = {
        "Hevy ID": {
            "title": [
                {
                    "text": {
                        "content": workout_id
                    }
                }
            ]
        }
    }
    
    # Add workout date if available
    if workout_date:
        properties["Workout Date"] = {
            "date": {
                "start": workout_date
            }
        }
    
    # Add duration if available
    if duration_minutes is not None:
        properties["Duration"] = {
            "number": round(duration_minutes, 2)
        }
    
    # Add routine as select option if provided
    if routine_name:
        properties["Routine"] = {
            "select": {
                "name": routine_name
            }
        }
    
    # Check if workout already exists by searching for Hevy ID
    search_payload = {
        "filter": {
            "property": "Hevy ID",
            "title": {
                "equals": workout_id
            }
        }
    }
    
    try:
        search_response = requests.post(
            f"https://api.notion.com/v1/databases/{notion_workouts_db_id}/query",
            headers=headers,
            json=search_payload,
            timeout=10
        )
        
        if search_response.status_code == 200:
            results = search_response.json().get("results", [])
            if results:
                # Workout already exists, update it
                page_id = results[0]["id"]
                logging.info(f"Updating existing workout: Hevy ID {workout_id}")
                
                update_response = requests.patch(
                    f"https://api.notion.com/v1/pages/{page_id}",
                    headers=headers,
                    json={"properties": properties},
                    timeout=10
                )
                
                if update_response.status_code != 200:
                    logging.error(f"Failed to update workout: {update_response.status_code} - {update_response.text}")
                    update_response.raise_for_status()
                
                return update_response.json()
    except requests.exceptions.RequestException as e:
        logging.warning(f"Could not search for existing workout: {str(e)}. Will create new entry.")
    
    # Create new workout entry
    logging.info(f"Creating new workout: Hevy ID {workout_id}")
    
    # Prepare the request payload
    payload = {
        "parent": {
            "database_id": notion_workouts_db_id
        },
        "properties": properties
    }
    
    # Make the API request to create a page in the database
    response = requests.post(
        "https://api.notion.com/v1/pages",
        headers=headers,
        json=payload,
        timeout=10
    )
    
    if response.status_code != 200:
        logging.error(f"Notion API error: {response.status_code} - {response.text}")
        response.raise_for_status()
    
    return response.json()


def add_exercise_to_notion(exercise_template_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Add or update an exercise entry in the Notion Exercises database.
    
    Args:
        exercise_template_data: Exercise template data from Hevy API
        
    Returns:
        Response from Notion API
        
    Raises:
        ValueError: If required environment variables are not set
        requests.HTTPError: If Notion API request fails
    """
    notion_api_key = os.environ.get("NOTION_API_KEY")
    notion_exercises_db_id = os.environ.get("NOTION_EXERCISES_DATABASE_ID")
    
    if not notion_api_key or not notion_exercises_db_id:
        raise ValueError("NOTION_API_KEY and NOTION_EXERCISES_DATABASE_ID environment variables must be set")
    
    # Prepare Notion API headers
    headers = {
        "Authorization": f"Bearer {notion_api_key}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    
    # Extract exercise template fields
    # Hevy API returns exercise_template wrapped in "exercise_template" object
    exercise_template = exercise_template_data.get("exercise_template", exercise_template_data)
    
    exercise_id = exercise_template.get("id", "")
    exercise_title = exercise_template.get("title", "Unknown Exercise")
    primary_muscle = exercise_template.get("primary_muscle_group", "")
    secondary_muscles = exercise_template.get("secondary_muscle_groups", [])
    
    # Build properties according to Notion database schema
    properties = {
        "Name": {
            "title": [
                {
                    "text": {
                        "content": exercise_title
                    }
                }
            ]
        },
        "Hevy ID": {
            "rich_text": [
                {
                    "text": {
                        "content": exercise_id
                    }
                }
            ]
        }
    }
    
    # Add primary muscle group if available (select type)
    if primary_muscle:
        # Capitalize first letter for consistency
        primary_muscle_formatted = primary_muscle.capitalize()
        properties["Primary Muscle Group"] = {
            "select": {
                "name": primary_muscle_formatted
            }
        }
    
    # Add secondary muscle groups if available
    if secondary_muscles and isinstance(secondary_muscles, list):
        # Filter out empty strings and format
        formatted_muscles = [
            {"name": muscle.capitalize()} 
            for muscle in secondary_muscles 
            if muscle
        ]
        if formatted_muscles:
            properties["Secondary Muscle Groups"] = {
                "multi_select": formatted_muscles
            }
    
    # Check if exercise already exists by searching for Hevy ID
    # First, try to find existing exercise
    search_payload = {
        "filter": {
            "property": "Hevy ID",
            "rich_text": {
                "equals": exercise_id
            }
        }
    }
    
    try:
        search_response = requests.post(
            f"https://api.notion.com/v1/databases/{notion_exercises_db_id}/query",
            headers=headers,
            json=search_payload,
            timeout=10
        )
        
        if search_response.status_code == 200:
            results = search_response.json().get("results", [])
            if results:
                # Exercise already exists, update it
                page_id = results[0]["id"]
                logging.info(f"Updating existing exercise: {exercise_title} (Hevy ID: {exercise_id})")
                
                update_response = requests.patch(
                    f"https://api.notion.com/v1/pages/{page_id}",
                    headers=headers,
                    json={"properties": properties},
                    timeout=10
                )
                
                if update_response.status_code != 200:
                    logging.error(f"Failed to update exercise: {update_response.status_code} - {update_response.text}")
                    update_response.raise_for_status()
                
                return update_response.json()
    except requests.exceptions.RequestException as e:
        logging.warning(f"Could not search for existing exercise: {str(e)}. Will create new entry.")
    
    # Create new exercise entry
    logging.info(f"Creating new exercise: {exercise_title} (Hevy ID: {exercise_id})")
    
    payload = {
        "parent": {
            "database_id": notion_exercises_db_id
        },
        "properties": properties
    }
    
    response = requests.post(
        "https://api.notion.com/v1/pages",
        headers=headers,
        json=payload,
        timeout=10
    )
    
    if response.status_code != 200:
        logging.error(f"Notion API error: {response.status_code} - {response.text}")
        response.raise_for_status()
    
    return response.json()


def ensure_routine_option_exists(routine_name: str) -> bool:
    """
    Check if a routine name exists as a select option in the Notion database.
    If not, the option will be automatically created by Notion when adding the workout.
    
    Args:
        routine_name: Name of the routine to check
        
    Returns:
        True (option will be created automatically if it doesn't exist)
        
    Note:
        Notion automatically creates new select options when you reference them
        in a page creation request, so this function is mainly for logging purposes.
    """
    if routine_name:
        logging.info(f"Routine '{routine_name}' will be added as select option if it doesn't exist")
    return True


# ============================================================================
# Async Notion Functions for Parallel Processing
# ============================================================================

async def process_exercise_async(
    exercise_template: Dict[str, Any],
    session: aiohttp.ClientSession,
    notion_api_key: str,
    notion_exercises_db_id: str
) -> Optional[Dict[str, Any]]:
    """
    Process a single exercise asynchronously (search, update or create in Notion).
    
    Args:
        exercise_template: Exercise template data from Hevy API
        session: aiohttp ClientSession
        notion_api_key: Notion API key
        notion_exercises_db_id: Notion Exercises database ID
        
    Returns:
        Response from Notion API with exercise page info, or None if error
    """
    headers = {
        "Authorization": f"Bearer {notion_api_key}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    
    # Extract exercise template fields
    template_data = exercise_template.get("exercise_template", exercise_template)
    exercise_id = template_data.get("id", "")
    exercise_title = template_data.get("title", "Unknown Exercise")
    primary_muscle = template_data.get("primary_muscle_group", "")
    secondary_muscles = template_data.get("secondary_muscle_groups", [])
    
    # Build properties
    properties = {
        "Name": {
            "title": [{"text": {"content": exercise_title}}]
        },
        "Hevy ID": {
            "rich_text": [{"text": {"content": exercise_id}}]
        }
    }
    
    if primary_muscle:
        properties["Primary Muscle Group"] = {
            "select": {"name": primary_muscle.capitalize()}
        }
    
    if secondary_muscles and isinstance(secondary_muscles, list):
        formatted_muscles = [
            {"name": muscle.capitalize()} 
            for muscle in secondary_muscles 
            if muscle
        ]
        if formatted_muscles:
            properties["Secondary Muscle Groups"] = {
                "multi_select": formatted_muscles
            }
    
    try:
        # Search for existing exercise
        search_payload = {
            "filter": {
                "property": "Hevy ID",
                "rich_text": {"equals": exercise_id}
            }
        }
        
        async with session.post(
            f"https://api.notion.com/v1/databases/{notion_exercises_db_id}/query",
            headers=headers,
            json=search_payload,
            timeout=aiohttp.ClientTimeout(total=10)
        ) as response:
            if response.status == 200:
                data = await response.json()
                results = data.get("results", [])
                
                if results:
                    # Update existing exercise
                    page_id = results[0]["id"]
                    logging.info(f"Updating existing exercise: {exercise_title} (Hevy ID: {exercise_id})")
                    
                    async with session.patch(
                        f"https://api.notion.com/v1/pages/{page_id}",
                        headers=headers,
                        json={"properties": properties},
                        timeout=aiohttp.ClientTimeout(total=10)
                    ) as update_response:
                        if update_response.status == 200:
                            return await update_response.json()
                        else:
                            text = await update_response.text()
                            logging.error(f"Failed to update exercise: {update_response.status} - {text}")
                            return None
        
        # Create new exercise if not found
        logging.info(f"Creating new exercise: {exercise_title} (Hevy ID: {exercise_id})")
        
        payload = {
            "parent": {"database_id": notion_exercises_db_id},
            "properties": properties
        }
        
        async with session.post(
            "https://api.notion.com/v1/pages",
            headers=headers,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=10)
        ) as response:
            if response.status == 200:
                return await response.json()
            else:
                text = await response.text()
                logging.error(f"Failed to create exercise: {response.status} - {text}")
                return None
                
    except Exception as e:
        logging.error(f"Error processing exercise {exercise_title}: {str(e)}")
        return None


async def process_exercises_async(
    exercise_templates: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Process multiple exercises in parallel (search, update or create in Notion).
    
    Args:
        exercise_templates: List of exercise template data from Hevy API
        
    Returns:
        List of successfully processed exercise info dictionaries
    """
    notion_api_key = os.environ.get("NOTION_API_KEY")
    notion_exercises_db_id = os.environ.get("NOTION_EXERCISES_DATABASE_ID")
    
    if not notion_api_key or not notion_exercises_db_id:
        logging.error("NOTION_API_KEY or NOTION_EXERCISES_DATABASE_ID not configured")
        return []
    
    async with aiohttp.ClientSession() as session:
        tasks = []
        for template in exercise_templates:
            task = process_exercise_async(
                template,
                session,
                notion_api_key,
                notion_exercises_db_id
            )
            tasks.append(task)
        
        # Process all exercises in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Build processed exercises list
        processed = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logging.error(f"Exception processing exercise: {str(result)}")
            elif result is not None and isinstance(result, dict):
                template_data = exercise_templates[i].get("exercise_template", exercise_templates[i])
                processed.append({
                    "exercise_template_id": template_data.get("id", ""),
                    "title": template_data.get("title", "Unknown"),
                    "notion_page_id": result.get("id")
                })
        
        return processed


async def process_exercise_performance_async(
    performance_data: Dict[str, Any],
    workout_page_url: str,
    exercise_notion_pages: Dict[str, str],
    session: aiohttp.ClientSession,
    notion_api_key: str,
    notion_performances_db_id: str
) -> Optional[Dict[str, Any]]:
    """
    Process a single exercise performance asynchronously (create in Notion).
    
    Args:
        performance_data: Aggregated performance data with exercise_template_id, title, total_weight_kg, total_reps
        workout_page_url: Notion page URL of the workout
        exercise_notion_pages: Dictionary mapping exercise_template_id to Notion page URLs
        session: aiohttp ClientSession
        notion_api_key: Notion API key
        notion_performances_db_id: Notion Exercise Performances database ID
        
    Returns:
        Response from Notion API with performance page info, or None if error
    """
    headers = {
        "Authorization": f"Bearer {notion_api_key}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }
    
    exercise_template_id = performance_data.get("exercise_template_id", "")
    title = performance_data.get("title", "Unknown Exercise")
    total_weight_kg = performance_data.get("total_weight_kg", 0.0)
    total_reps = performance_data.get("total_reps", 0)
    
    # Get exercise page URL from the mapping
    exercise_page_url = exercise_notion_pages.get(exercise_template_id)
    
    if not exercise_page_url:
        logging.warning(f"No Notion page found for exercise {title} ({exercise_template_id})")
        return None
    
    # Build properties
    properties = {
        "Name": {
            "title": [{"text": {"content": title}}]
        },
        "Total Weight (KG)": {
            "number": round(total_weight_kg, 2)
        },
        "Total Reps": {
            "number": total_reps
        },
        "Workout": {
            "relation": [{"id": workout_page_url}]
        },
        "Exercise": {
            "relation": [{"id": exercise_page_url}]
        }
    }
    
    try:
        # Create exercise performance entry
        logging.info(f"Creating exercise performance: {title} ({total_reps} reps, {total_weight_kg:.2f} kg)")
        
        payload = {
            "parent": {"database_id": notion_performances_db_id},
            "properties": properties
        }
        
        async with session.post(
            "https://api.notion.com/v1/pages",
            headers=headers,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=10)
        ) as response:
            if response.status == 200:
                return await response.json()
            else:
                text = await response.text()
                logging.error(f"Failed to create exercise performance: {response.status} - {text}")
                return None
                
    except Exception as e:
        logging.error(f"Error processing exercise performance {title}: {str(e)}")
        return None


async def process_exercise_performances_async(
    performance_data_list: List[Dict[str, Any]],
    workout_page_id: str,
    exercise_notion_pages: Dict[str, str]
) -> List[Dict[str, Any]]:
    """
    Process multiple exercise performances in parallel (create in Notion).
    
    Args:
        performance_data_list: List of aggregated performance data
        workout_page_id: Notion page ID of the workout (will be converted to URL format)
        exercise_notion_pages: Dictionary mapping exercise_template_id to Notion page IDs
        
    Returns:
        List of successfully processed exercise performance info dictionaries
    """
    notion_api_key = os.environ.get("NOTION_API_KEY")
    notion_performances_db_id = os.environ.get("NOTION_EXERCISE_PERFORMANCES_DATABASE_ID")
    
    if not notion_api_key or not notion_performances_db_id:
        logging.error("NOTION_API_KEY or NOTION_EXERCISE_PERFORMANCES_DATABASE_ID not configured")
        return []
    
    # Convert page IDs to proper format (remove dashes)
    workout_page_url = workout_page_id.replace("-", "")
    exercise_pages_dict = {k: v.replace("-", "") for k, v in exercise_notion_pages.items()}
    
    async with aiohttp.ClientSession() as session:
        tasks = []
        for perf_data in performance_data_list:
            task = process_exercise_performance_async(
                perf_data,
                workout_page_url,
                exercise_pages_dict,
                session,
                notion_api_key,
                notion_performances_db_id
            )
            tasks.append(task)
        
        # Process all performances in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Build processed performances list
        processed = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logging.error(f"Exception processing exercise performance: {str(result)}")
            elif result is not None and isinstance(result, dict):
                perf_data = performance_data_list[i]
                processed.append({
                    "exercise_template_id": perf_data.get("exercise_template_id", ""),
                    "title": perf_data.get("title", "Unknown"),
                    "total_weight_kg": perf_data.get("total_weight_kg", 0.0),
                    "total_reps": perf_data.get("total_reps", 0),
                    "notion_page_id": result.get("id")
                })
        
        return processed
