"""Notion database integration for Hevy workout entries (4-database schema)."""

import logging
import os
import asyncio
import aiohttp
from typing import Dict, Any, Optional, List, Tuple
from datetime import datetime

# Rate limiting: Notion API allows ~3 requests/second
# Use a semaphore to limit concurrent requests
# Note: Semaphore must be created per-event-loop to avoid binding issues in Azure Functions
NOTION_SEMAPHORE_LIMIT = 2  # Reduced from 3 to be safer
NOTION_REQUEST_DELAY = 0.5  # seconds between requests (increased from 0.35)
NOTION_MAX_RETRIES = 5  # max retries on rate limit
NOTION_RETRY_BASE_DELAY = 2  # base delay for exponential backoff (seconds)
NOTION_MAX_RETRY_DELAY = 30  # cap retry delay to 30 seconds max

# Store semaphore per event loop ID to handle Azure Functions reusing/changing loops
_semaphore_cache: Dict[int, asyncio.Semaphore] = {}


def get_notion_semaphore() -> asyncio.Semaphore:
    """Get or create the rate limiting semaphore for the current event loop."""
    global _semaphore_cache
    try:
        loop = asyncio.get_running_loop()
        loop_id = id(loop)
        if loop_id not in _semaphore_cache:
            # Clean up old semaphores from dead loops (keep only current)
            _semaphore_cache = {loop_id: asyncio.Semaphore(NOTION_SEMAPHORE_LIMIT)}
        return _semaphore_cache[loop_id]
    except RuntimeError:
        # No running event loop, create new unbound semaphore
        return asyncio.Semaphore(NOTION_SEMAPHORE_LIMIT)


# ============================================================================
# Helper Functions
# ============================================================================

def get_notion_headers(notion_api_key: str) -> Dict[str, str]:
    """Get standard Notion API headers."""
    return {
        "Authorization": f"Bearer {notion_api_key}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }


async def notion_request_with_retry(
    session: aiohttp.ClientSession,
    method: str,
    url: str,
    headers: Dict[str, str],
    json_data: Optional[Dict] = None
) -> Tuple[int, Optional[Dict], Optional[str]]:
    """
    Make a Notion API request with rate limiting and exponential backoff retry.

    Args:
        session: aiohttp ClientSession
        method: HTTP method (GET, POST, PATCH)
        url: Request URL
        headers: Request headers
        json_data: Optional JSON body

    Returns:
        Tuple of (status_code, response_json, error_text)
    """
    semaphore = get_notion_semaphore()
    for attempt in range(NOTION_MAX_RETRIES):
        async with semaphore:
            await asyncio.sleep(NOTION_REQUEST_DELAY)

            try:
                if method == "GET":
                    async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=30)) as response:
                        status = response.status
                        if status == 200:
                            return status, await response.json(), None
                        elif status == 429:
                            header_delay = int(response.headers.get("Retry-After", NOTION_RETRY_BASE_DELAY * (2 ** attempt)))
                            retry_after = min(header_delay, NOTION_MAX_RETRY_DELAY)
                            logging.warning(f"Rate limited (attempt {attempt + 1}/{NOTION_MAX_RETRIES}), waiting {retry_after}s (header suggested {header_delay}s)...")
                            await asyncio.sleep(retry_after)
                            continue
                        else:
                            return status, None, await response.text()

                elif method == "POST":
                    async with session.post(url, headers=headers, json=json_data, timeout=aiohttp.ClientTimeout(total=30)) as response:
                        status = response.status
                        if status == 200:
                            return status, await response.json(), None
                        elif status == 429:
                            header_delay = int(response.headers.get("Retry-After", NOTION_RETRY_BASE_DELAY * (2 ** attempt)))
                            retry_after = min(header_delay, NOTION_MAX_RETRY_DELAY)
                            logging.warning(f"Rate limited (attempt {attempt + 1}/{NOTION_MAX_RETRIES}), waiting {retry_after}s (header suggested {header_delay}s)...")
                            await asyncio.sleep(retry_after)
                            continue
                        else:
                            return status, None, await response.text()

                elif method == "PATCH":
                    async with session.patch(url, headers=headers, json=json_data, timeout=aiohttp.ClientTimeout(total=30)) as response:
                        status = response.status
                        if status == 200:
                            return status, await response.json(), None
                        elif status == 429:
                            header_delay = int(response.headers.get("Retry-After", NOTION_RETRY_BASE_DELAY * (2 ** attempt)))
                            retry_after = min(header_delay, NOTION_MAX_RETRY_DELAY)
                            logging.warning(f"Rate limited (attempt {attempt + 1}/{NOTION_MAX_RETRIES}), waiting {retry_after}s (header suggested {header_delay}s)...")
                            await asyncio.sleep(retry_after)
                            continue
                        else:
                            return status, None, await response.text()

            except asyncio.TimeoutError:
                logging.warning(f"Request timeout (attempt {attempt + 1}/{NOTION_MAX_RETRIES})")
                if attempt < NOTION_MAX_RETRIES - 1:
                    await asyncio.sleep(NOTION_RETRY_BASE_DELAY * (2 ** attempt))
                    continue
                return 0, None, "Request timeout after retries"

    return 429, None, "Rate limited after max retries"


async def find_page_by_hevy_id(
    database_id: str,
    hevy_id_property: str,
    hevy_id: str,
    session: aiohttp.ClientSession,
    notion_api_key: str,
    property_type: str = "rich_text"
) -> Optional[str]:
    """
    Search Notion DB for existing page by Hevy ID.

    Args:
        database_id: Notion database ID
        hevy_id_property: Name of the property containing Hevy ID
        hevy_id: The Hevy ID to search for
        session: aiohttp ClientSession
        notion_api_key: Notion API key
        property_type: Type of property ("rich_text" or "title")

    Returns:
        Page ID if found, None otherwise
    """
    headers = get_notion_headers(notion_api_key)

    if property_type == "title":
        filter_config = {
            "property": hevy_id_property,
            "title": {"equals": hevy_id}
        }
    else:
        filter_config = {
            "property": hevy_id_property,
            "rich_text": {"equals": hevy_id}
        }

    search_payload = {"filter": filter_config}
    url = f"https://api.notion.com/v1/databases/{database_id}/query"

    status, data, error = await notion_request_with_retry(
        session, "POST", url, headers, search_payload
    )

    if status == 200 and data:
        results = data.get("results", [])
        if results:
            return results[0]["id"]
    elif error:
        logging.warning(f"Search failed for {hevy_id}: {status} - {error}")

    return None


async def create_or_update_page(
    database_id: str,
    page_id: Optional[str],
    properties: Dict[str, Any],
    session: aiohttp.ClientSession,
    notion_api_key: str
) -> Optional[str]:
    """
    Create a new page or update an existing one.

    Args:
        database_id: Notion database ID (for creation)
        page_id: Existing page ID (for update) or None
        properties: Page properties
        session: aiohttp ClientSession
        notion_api_key: Notion API key

    Returns:
        Page ID if successful, None otherwise
    """
    headers = get_notion_headers(notion_api_key)

    if page_id:
        # Update existing page
        url = f"https://api.notion.com/v1/pages/{page_id}"
        payload = {"properties": properties}
        status, data, error = await notion_request_with_retry(
            session, "PATCH", url, headers, payload
        )
    else:
        # Create new page
        url = "https://api.notion.com/v1/pages"
        payload = {
            "parent": {"database_id": database_id},
            "properties": properties
        }
        status, data, error = await notion_request_with_retry(
            session, "POST", url, headers, payload
        )

    if status == 200 and data:
        return data.get("id")
    else:
        action = "update" if page_id else "create"
        logging.error(f"Failed to {action} page: {status} - {error}")
        return None


# ============================================================================
# Exercise Templates
# ============================================================================

async def upsert_exercise_template(
    template: Dict[str, Any],
    session: aiohttp.ClientSession,
    notion_api_key: str,
    database_id: str
) -> Optional[str]:
    """
    Create or update an exercise template in Notion.

    Args:
        template: Exercise template data from Hevy API
        session: aiohttp ClientSession
        notion_api_key: Notion API key
        database_id: Exercise Templates database ID

    Returns:
        Page ID if successful, None otherwise
    """
    # Handle wrapped response
    template_data = template.get("exercise_template", template)

    hevy_id = template_data.get("id", "")
    title = template_data.get("title", "Unknown Exercise")
    exercise_type = template_data.get("type", "")
    primary_muscle = template_data.get("primary_muscle_group", "")
    secondary_muscles = template_data.get("secondary_muscle_groups", [])
    equipment = template_data.get("equipment_category", "")
    is_custom = template_data.get("is_custom", False)

    # Build properties
    properties = {
        "Name": {
            "title": [{"text": {"content": title}}]
        },
        "Hevy ID": {
            "rich_text": [{"text": {"content": hevy_id}}]
        },
        "Last Synced": {
            "date": {"start": datetime.utcnow().isoformat()}
        }
    }

    if exercise_type:
        properties["Exercise Type"] = {"select": {"name": exercise_type}}

    if primary_muscle:
        properties["Primary Muscle"] = {"select": {"name": primary_muscle.replace("_", " ").title()}}

    if secondary_muscles and isinstance(secondary_muscles, list):
        formatted = [{"name": m.replace("_", " ").title()} for m in secondary_muscles if m]
        if formatted:
            properties["Secondary Muscles"] = {"multi_select": formatted}

    if equipment:
        properties["Equipment"] = {"select": {"name": equipment.replace("_", " ").title()}}

    properties["Is Custom"] = {"checkbox": is_custom}

    # Check if exists
    existing_page_id = await find_page_by_hevy_id(
        database_id, "Hevy ID", hevy_id, session, notion_api_key
    )

    action = "Updating" if existing_page_id else "Creating"
    logging.info(f"{action} exercise template: {title} ({hevy_id})")

    return await create_or_update_page(
        database_id, existing_page_id, properties, session, notion_api_key
    )


async def sync_exercise_templates(
    templates: List[Dict[str, Any]],
    session: aiohttp.ClientSession,
    notion_api_key: str,
    database_id: str
) -> Tuple[int, Dict[str, str]]:
    """
    Sync all exercise templates in parallel.

    Returns:
        Tuple of (count of synced templates, dict mapping hevy_id to notion_page_id)
    """
    tasks = [
        upsert_exercise_template(t, session, notion_api_key, database_id)
        for t in templates
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    count = 0
    id_mapping = {}
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logging.error(f"Exception syncing exercise template: {str(result)}")
        elif result is not None:
            count += 1
            template_data = templates[i].get("exercise_template", templates[i])
            hevy_id = template_data.get("id", "")
            id_mapping[hevy_id] = result

    logging.info(f"Synced {count}/{len(templates)} exercise templates")
    # Debug: Log some sample mapping keys
    if id_mapping:
        sample_keys = list(id_mapping.keys())[:3]
        logging.info(f"Sample template mapping keys: {sample_keys}")
    return count, id_mapping


# ============================================================================
# Routines
# ============================================================================

async def upsert_routine(
    routine: Dict[str, Any],
    session: aiohttp.ClientSession,
    notion_api_key: str,
    database_id: str
) -> Optional[str]:
    """
    Create or update a routine in Notion.

    Args:
        routine: Routine data from Hevy API
        session: aiohttp ClientSession
        notion_api_key: Notion API key
        database_id: Routines database ID

    Returns:
        Page ID if successful, None otherwise
    """
    # Handle wrapped response
    routine_data = routine.get("routine", routine)

    hevy_id = routine_data.get("id", "")
    title = routine_data.get("title", "Unnamed Routine")
    folder_id = routine_data.get("folder_id")
    notes = routine_data.get("notes", "")
    exercises = routine_data.get("exercises", [])
    created_at = routine_data.get("created_at")
    updated_at = routine_data.get("updated_at")

    # Build properties
    properties = {
        "Name": {
            "title": [{"text": {"content": title}}]
        },
        "Hevy ID": {
            "rich_text": [{"text": {"content": hevy_id}}]
        },
        "Exercise Count": {
            "number": len(exercises)
        },
        "Last Synced": {
            "date": {"start": datetime.utcnow().isoformat()}
        }
    }

    if folder_id is not None:
        properties["Folder ID"] = {"number": folder_id}

    if notes:
        properties["Notes"] = {
            "rich_text": [{"text": {"content": notes[:2000]}}]  # Notion limit
        }

    if created_at:
        properties["Created"] = {"date": {"start": created_at}}

    if updated_at:
        properties["Updated"] = {"date": {"start": updated_at}}

    # Check if exists
    existing_page_id = await find_page_by_hevy_id(
        database_id, "Hevy ID", hevy_id, session, notion_api_key
    )

    action = "Updating" if existing_page_id else "Creating"
    logging.info(f"{action} routine: {title} ({hevy_id})")

    return await create_or_update_page(
        database_id, existing_page_id, properties, session, notion_api_key
    )


async def sync_routines(
    routines: List[Dict[str, Any]],
    session: aiohttp.ClientSession,
    notion_api_key: str,
    database_id: str
) -> Tuple[int, Dict[str, str]]:
    """
    Sync all routines in parallel.

    Returns:
        Tuple of (count of synced routines, dict mapping hevy_id to notion_page_id)
    """
    tasks = [
        upsert_routine(r, session, notion_api_key, database_id)
        for r in routines
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    count = 0
    id_mapping = {}
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            logging.error(f"Exception syncing routine: {str(result)}")
        elif result is not None:
            count += 1
            routine_data = routines[i].get("routine", routines[i])
            hevy_id = routine_data.get("id", "")
            id_mapping[hevy_id] = result

    logging.info(f"Synced {count}/{len(routines)} routines")
    return count, id_mapping


# ============================================================================
# Workouts
# ============================================================================

async def upsert_workout(
    workout: Dict[str, Any],
    session: aiohttp.ClientSession,
    notion_api_key: str,
    workouts_db_id: str,
    routine_page_id: Optional[str] = None
) -> Optional[str]:
    """
    Create or update a workout in Notion.

    Args:
        workout: Workout data from Hevy API
        session: aiohttp ClientSession
        notion_api_key: Notion API key
        workouts_db_id: Workouts database ID
        routine_page_id: Notion page ID of the associated routine (optional)

    Returns:
        Page ID if successful, None otherwise
    """
    # Handle wrapped response
    workout_data = workout.get("workout", workout)

    hevy_id = workout_data.get("id", "")
    title = workout_data.get("title", "Workout")
    description = workout_data.get("description", "")
    start_time = workout_data.get("start_time")
    end_time = workout_data.get("end_time")
    created_at = workout_data.get("created_at")
    exercises = workout_data.get("exercises", [])

    # Calculate totals
    exercise_count = len(exercises)
    total_sets = sum(len(ex.get("sets", [])) for ex in exercises)

    # Build properties
    # Note: "Name" is the default title property in Notion
    properties = {
        "Name": {
            "title": [{"text": {"content": title}}]
        },
        "Hevy ID": {
            "rich_text": [{"text": {"content": hevy_id}}]
        },
        "Exercise Count": {
            "number": exercise_count
        },
        "Total Sets": {
            "number": total_sets
        },
        "Last Synced": {
            "date": {"start": datetime.utcnow().isoformat()}
        }
    }

    if description:
        properties["Description"] = {
            "rich_text": [{"text": {"content": description[:2000]}}]  # Notion limit
        }

    if start_time:
        properties["Start Time"] = {"date": {"start": start_time}}

    if end_time:
        properties["End Time"] = {"date": {"start": end_time}}

    if created_at:
        properties["Created"] = {"date": {"start": created_at}}

    # Add routine relation if available
    if routine_page_id:
        properties["Routine"] = {
            "relation": [{"id": routine_page_id.replace("-", "")}]
        }

    # Check if exists
    existing_page_id = await find_page_by_hevy_id(
        workouts_db_id, "Hevy ID", hevy_id, session, notion_api_key
    )

    action = "Updating" if existing_page_id else "Creating"
    logging.info(f"{action} workout: {title} ({hevy_id})")

    return await create_or_update_page(
        workouts_db_id, existing_page_id, properties, session, notion_api_key
    )


# ============================================================================
# Exercise Sets
# ============================================================================

async def upsert_set(
    workout_id: str,
    workout_page_id: str,
    exercise: Dict[str, Any],
    exercise_index: int,
    set_data: Dict[str, Any],
    set_index: int,
    session: aiohttp.ClientSession,
    notion_api_key: str,
    sets_db_id: str,
    exercise_template_page_id: Optional[str] = None
) -> Optional[str]:
    """
    Create or update an individual set in Notion.

    Args:
        workout_id: Hevy workout ID
        workout_page_id: Notion page ID of the workout
        exercise: Exercise data containing the set
        exercise_index: 0-based index of exercise in workout
        set_data: Individual set data
        set_index: 0-based index of set in exercise
        session: aiohttp ClientSession
        notion_api_key: Notion API key
        sets_db_id: Sets database ID
        exercise_template_page_id: Notion page ID of the exercise template

    Returns:
        Page ID if successful, None otherwise
    """
    # Composite Set ID for upsert
    composite_set_id = f"{workout_id}-{exercise_index}-{set_index}"
    exercise_name = exercise.get("title", "Unknown Exercise")

    # Extract set properties
    set_type = set_data.get("set_type", "normal")
    weight_kg = set_data.get("weight_kg")
    reps = set_data.get("reps")
    distance_meters = set_data.get("distance_meters")
    duration_seconds = set_data.get("duration_seconds")
    rpe = set_data.get("rpe")
    superset_id = exercise.get("superset_id")
    notes = exercise.get("notes", "")

    # Build properties
    # Title is Exercise Name for readability, Hevy ID stores composite ID for upsert
    properties = {
        "Exercise Name": {
            "title": [{"text": {"content": exercise_name}}]
        },
        "Hevy ID": {
            "rich_text": [{"text": {"content": composite_set_id}}]
        },
        "Exercise Order": {
            "number": exercise_index + 1  # 1-based for display
        },
        "Set Number": {
            "number": set_index + 1  # 1-based for display
        },
        "Set Type": {
            "select": {"name": set_type}
        },
        "Last Synced": {
            "date": {"start": datetime.utcnow().isoformat()}
        }
    }

    # Add workout relation
    if workout_page_id:
        properties["Workout"] = {
            "relation": [{"id": workout_page_id.replace("-", "")}]
        }

    # Add exercise template relation
    if exercise_template_page_id:
        properties["Exercise"] = {
            "relation": [{"id": exercise_template_page_id.replace("-", "")}]
        }

    # Add numeric properties (only if they have values)
    # Convert kg to lbs (1 kg = 2.20462 lbs)
    if weight_kg is not None:
        weight_lbs = float(weight_kg) * 2.20462
        properties["Weight (lb)"] = {"number": round(weight_lbs, 2)}

    if reps is not None:
        properties["Reps"] = {"number": int(reps)}

    if distance_meters is not None:
        properties["Distance (m)"] = {"number": float(distance_meters)}

    if duration_seconds is not None:
        properties["Duration (s)"] = {"number": int(duration_seconds)}

    if rpe is not None:
        properties["RPE"] = {"number": float(rpe)}

    if superset_id is not None:
        properties["Superset ID"] = {"number": superset_id}

    if notes:
        properties["Notes"] = {
            "rich_text": [{"text": {"content": notes[:2000]}}]
        }

    # Check if exists by Hevy ID (rich_text property)
    existing_page_id = await find_page_by_hevy_id(
        sets_db_id, "Hevy ID", composite_set_id, session, notion_api_key
    )

    return await create_or_update_page(
        sets_db_id, existing_page_id, properties, session, notion_api_key
    )


async def sync_workout_sets(
    workout_id: str,
    workout_page_id: str,
    exercises: List[Dict[str, Any]],
    session: aiohttp.ClientSession,
    notion_api_key: str,
    sets_db_id: str,
    exercise_template_mapping: Dict[str, str]
) -> int:
    """
    Sync all sets for a workout in parallel.

    Args:
        workout_id: Hevy workout ID
        workout_page_id: Notion page ID of the workout
        exercises: List of exercises from workout data
        session: aiohttp ClientSession
        notion_api_key: Notion API key
        sets_db_id: Sets database ID
        exercise_template_mapping: Dict mapping exercise_template_id to Notion page ID

    Returns:
        Count of successfully synced sets
    """
    tasks = []

    # Debug: Log the mapping size once per workout set sync
    if exercise_template_mapping:
        logging.info(f"Exercise template mapping has {len(exercise_template_mapping)} entries for workout {workout_id}")
    else:
        logging.warning(f"Exercise template mapping is empty for workout {workout_id}!")

    for exercise_index, exercise in enumerate(exercises):
        exercise_template_id = exercise.get("exercise_template_id", "")
        exercise_template_page_id = exercise_template_mapping.get(exercise_template_id)

        # Debug: Log lookup result for first exercise
        if exercise_index == 0:
            logging.info(f"First exercise template_id: {exercise_template_id}, found page_id: {exercise_template_page_id}")

        if exercise_template_id and not exercise_template_page_id:
            logging.debug(f"No mapping found for exercise_template_id: {exercise_template_id}")

        for set_index, set_data in enumerate(exercise.get("sets", [])):
            tasks.append(
                upsert_set(
                    workout_id,
                    workout_page_id,
                    exercise,
                    exercise_index,
                    set_data,
                    set_index,
                    session,
                    notion_api_key,
                    sets_db_id,
                    exercise_template_page_id
                )
            )

    if not tasks:
        return 0

    results = await asyncio.gather(*tasks, return_exceptions=True)

    count = 0
    for result in results:
        if isinstance(result, Exception):
            logging.error(f"Exception syncing set: {str(result)}")
        elif result is not None:
            count += 1

    return count


# ============================================================================
# Full Sync Functions
# ============================================================================

async def sync_workouts_and_sets(
    workouts: List[Dict[str, Any]],
    session: aiohttp.ClientSession,
    notion_api_key: str,
    workouts_db_id: str,
    sets_db_id: str,
    routine_mapping: Dict[str, str],
    exercise_template_mapping: Dict[str, str]
) -> Tuple[int, int]:
    """
    Sync all workouts and their sets.

    Args:
        workouts: List of workout data from Hevy API
        session: aiohttp ClientSession
        notion_api_key: Notion API key
        workouts_db_id: Workouts database ID
        sets_db_id: Sets database ID
        routine_mapping: Dict mapping routine hevy_id to Notion page ID
        exercise_template_mapping: Dict mapping exercise_template_id to Notion page ID

    Returns:
        Tuple of (workout_count, set_count)
    """
    workout_count = 0
    set_count = 0

    for workout in workouts:
        workout_data = workout.get("workout", workout)
        routine_id = workout_data.get("routine_id")
        routine_page_id = routine_mapping.get(routine_id) if routine_id else None

        # Upsert workout
        workout_page_id = await upsert_workout(
            workout, session, notion_api_key, workouts_db_id, routine_page_id
        )

        if workout_page_id:
            workout_count += 1

            # Sync all sets for this workout
            exercises = workout_data.get("exercises", [])
            sets_synced = await sync_workout_sets(
                workout_data.get("id", ""),
                workout_page_id,
                exercises,
                session,
                notion_api_key,
                sets_db_id,
                exercise_template_mapping
            )
            set_count += sets_synced
            logging.info(f"Synced {sets_synced} sets for workout {workout_data.get('id', '')}")

    logging.info(f"Total: {workout_count} workouts, {set_count} sets")
    return workout_count, set_count


# ============================================================================
# Legacy Compatibility (for running webhook to still work)
# ============================================================================

def add_workout_to_notion(workout_data: Dict[str, Any], routine_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Legacy synchronous wrapper for adding workouts.
    Kept for backwards compatibility with running_webhook.

    Args:
        workout_data: Workout data from Hevy API
        routine_name: Name of the routine (unused in new schema, kept for compat)

    Returns:
        Response dict with page ID
    """
    import requests

    notion_api_key = os.environ.get("NOTION_API_KEY")
    notion_workouts_db_id = os.environ.get("NOTION_WORKOUTS_DATABASE_ID")

    if not notion_api_key or not notion_workouts_db_id:
        raise ValueError("NOTION_API_KEY and NOTION_WORKOUTS_DATABASE_ID must be set")

    headers = get_notion_headers(notion_api_key)

    workout_id = workout_data.get("id", "")
    title = workout_data.get("title", "Workout")
    start_time = workout_data.get("start_time")
    exercises = workout_data.get("exercises", [])

    properties = {
        "Title": {
            "title": [{"text": {"content": title}}]
        },
        "Hevy ID": {
            "rich_text": [{"text": {"content": workout_id}}]
        },
        "Exercise Count": {
            "number": len(exercises)
        },
        "Total Sets": {
            "number": sum(len(ex.get("sets", [])) for ex in exercises)
        },
        "Last Synced": {
            "date": {"start": datetime.utcnow().isoformat()}
        }
    }

    if start_time:
        properties["Start Time"] = {"date": {"start": start_time}}

    # Check if exists
    search_payload = {
        "filter": {
            "property": "Hevy ID",
            "rich_text": {"equals": workout_id}
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
                page_id = results[0]["id"]
                update_response = requests.patch(
                    f"https://api.notion.com/v1/pages/{page_id}",
                    headers=headers,
                    json={"properties": properties},
                    timeout=10
                )
                if update_response.status_code == 200:
                    return update_response.json()
                update_response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logging.warning(f"Could not search for existing workout: {str(e)}")

    # Create new
    payload = {
        "parent": {"database_id": notion_workouts_db_id},
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
