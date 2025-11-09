"""Helper module for interacting with Hevy API."""

import logging
import os
import requests
import asyncio
import aiohttp
from typing import Optional, Dict, Any, List
from datetime import datetime


def get_workout_details(workout_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch workout details from Hevy API.
    
    Args:
        workout_id: UUID of the workout to fetch
        
    Returns:
        Dictionary containing workout details, or None if error
    """
    hevy_api_key = os.environ.get("HEVY_API_KEY")
    
    if not hevy_api_key:
        logging.error("HEVY_API_KEY not configured")
        return None
    
    headers = {
        "api-key": hevy_api_key,
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(
            f"https://api.hevyapp.com/v1/workouts/{workout_id}",
            headers=headers,
            timeout=10
        )
        
        if response.status_code != 200:
            logging.error(f"Hevy API error: {response.status_code} - {response.text}")
            return None
        
        return response.json()
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to fetch workout from Hevy API: {str(e)}")
        return None


def get_routine_details(routine_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch routine details from Hevy API.
    
    Args:
        routine_id: UUID of the routine to fetch
        
    Returns:
        Dictionary containing routine details, or None if error
    """
    hevy_api_key = os.environ.get("HEVY_API_KEY")
    
    if not hevy_api_key:
        logging.error("HEVY_API_KEY not configured")
        return None
    
    headers = {
        "api-key": hevy_api_key,
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(
            f"https://api.hevyapp.com/v1/routines/{routine_id}",
            headers=headers,
            timeout=10
        )
        
        if response.status_code != 200:
            logging.error(f"Hevy API error for routine: {response.status_code} - {response.text}")
            return None
        
        return response.json()
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to fetch routine from Hevy API: {str(e)}")
        return None


def get_exercise_template(exercise_template_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch exercise template details from Hevy API.
    
    Args:
        exercise_template_id: ID of the exercise template to fetch
        
    Returns:
        Dictionary containing exercise template details, or None if error
    """
    hevy_api_key = os.environ.get("HEVY_API_KEY")
    
    if not hevy_api_key:
        logging.error("HEVY_API_KEY not configured")
        return None
    
    headers = {
        "api-key": hevy_api_key,
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(
            f"https://api.hevyapp.com/v1/exercise_templates/{exercise_template_id}",
            headers=headers,
            timeout=10
        )
        
        if response.status_code != 200:
            logging.error(f"Hevy API error for exercise template: {response.status_code} - {response.text}")
            return None
        
        return response.json()
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to fetch exercise template from Hevy API: {str(e)}")
        return None


def calculate_workout_duration(workout_data: Dict[str, Any]) -> Optional[float]:
    """
    Calculate workout duration in minutes from workout data.
    
    Args:
        workout_data: Workout data from Hevy API
        
    Returns:
        Duration in minutes, or None if cannot be calculated
    """
    try:
        # Try to get duration_seconds if available
        if 'duration_seconds' in workout_data:
            return workout_data['duration_seconds'] / 60.0
        
        # Try to calculate from start_time and end_time
        start_time_str = workout_data.get('start_time')
        end_time_str = workout_data.get('end_time')
        
        if start_time_str and end_time_str:
            start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
            end_time = datetime.fromisoformat(end_time_str.replace('Z', '+00:00'))
            duration_seconds = (end_time - start_time).total_seconds()
            return round(duration_seconds / 60.0, 0)
        
        logging.warning("Could not calculate workout duration from available data")
        return None
    except (ValueError, TypeError, KeyError) as e:
        logging.error(f"Error calculating workout duration: {str(e)}")
        return None


def extract_unique_exercises(workout_data: Dict[str, Any]) -> list[Dict[str, Any]]:
    """
    Extract unique exercises from workout data.
    
    Args:
        workout_data: Workout data from Hevy API
        
    Returns:
        List of unique exercise dictionaries with exercise_template_id and title
    """
    exercises = workout_data.get("exercises", [])
    unique_exercises = {}
    
    for exercise in exercises:
        exercise_template_id = exercise.get("exercise_template_id")
        if exercise_template_id and exercise_template_id not in unique_exercises:
            unique_exercises[exercise_template_id] = {
                "exercise_template_id": exercise_template_id,
                "title": exercise.get("title", "Unknown Exercise")
            }
    
    return list(unique_exercises.values())


def extract_exercise_performances(workout_data: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Extract and aggregate exercise performances from workout data.
    
    Groups sets by exercise and calculates total weight and total reps for each exercise.
    
    Args:
        workout_data: Workout data from Hevy API
        
    Returns:
        List of exercise performance dictionaries with aggregated data
    """
    exercises = workout_data.get("exercises", [])
    performances = {}
    
    for exercise in exercises:
        exercise_template_id = exercise.get("exercise_template_id")
        title = exercise.get("title", "Unknown Exercise")
        sets = exercise.get("sets", [])
        
        if not exercise_template_id:
            continue
        
        # Initialize performance entry if not exists
        if exercise_template_id not in performances:
            performances[exercise_template_id] = {
                "exercise_template_id": exercise_template_id,
                "title": title,
                "total_weight_kg": 0.0,
                "total_reps": 0,
                "set_count": 0
            }
        
        # Aggregate sets data
        for set_data in sets:
            # Skip warm-up sets or failed sets
            set_type = set_data.get("set_type", "normal")
            if set_type in ["warmup", "failure"]:
                continue
            
            reps = set_data.get("reps")
            weight_kg = set_data.get("weight_kg")
            
            # Skip sets with missing data
            if reps is None or weight_kg is None:
                logging.debug(f"Skipping set with missing data: reps={reps}, weight_kg={weight_kg}")
                continue
            
            # Convert to appropriate types
            try:
                reps = int(reps) if reps else 0
                weight_kg = float(weight_kg) if weight_kg else 0.0
            except (ValueError, TypeError):
                logging.warning(f"Invalid set data: reps={reps}, weight_kg={weight_kg}")
                continue
            
            # Calculate volume (weight * reps)
            volume = weight_kg * reps
            
            performances[exercise_template_id]["total_weight_kg"] += volume
            performances[exercise_template_id]["total_reps"] += reps
            performances[exercise_template_id]["set_count"] += 1
    
    return list(performances.values())


# ============================================================================
# Async API Functions for Parallel Processing
# ============================================================================

async def fetch_hevy_api_async(url: str, session: aiohttp.ClientSession) -> Optional[Dict[str, Any]]:
    """
    Fetch data from Hevy API asynchronously.
    
    Args:
        url: Full URL to fetch
        session: aiohttp ClientSession
        
    Returns:
        Dictionary containing API response, or None if error
    """
    hevy_api_key = os.environ.get("HEVY_API_KEY")
    
    if not hevy_api_key:
        logging.error("HEVY_API_KEY not configured")
        return None
    
    headers = {
        "api-key": hevy_api_key,
        "Content-Type": "application/json"
    }
    
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as response:
            if response.status != 200:
                text = await response.text()
                logging.error(f"Hevy API error for {url}: {response.status} - {text}")
                return None
            
            return await response.json()
    except asyncio.TimeoutError:
        logging.error(f"Timeout fetching from Hevy API: {url}")
        return None
    except Exception as e:
        logging.error(f"Failed to fetch from Hevy API: {url} - {str(e)}")
        return None


async def get_workout_and_routine_async(workout_id: str) -> tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Fetch workout and routine details in parallel.
    
    Args:
        workout_id: UUID of the workout to fetch
        
    Returns:
        Tuple of (workout_data, routine_data). routine_data may be None if workout has no routine.
    """
    async with aiohttp.ClientSession() as session:
        # Fetch workout first
        workout_url = f"https://api.hevyapp.com/v1/workouts/{workout_id}"
        workout_response = await fetch_hevy_api_async(workout_url, session)
        
        if not workout_response:
            return None, None
        
        # Extract workout data
        workout_data = workout_response.get("workout", workout_response)
        
        # Check if workout has a routine
        routine_id = workout_data.get("routine_id")
        routine_data = None
        
        if routine_id:
            routine_url = f"https://api.hevyapp.com/v1/routines/{routine_id}"
            routine_response = await fetch_hevy_api_async(routine_url, session)
            if routine_response:
                routine_data = routine_response.get("routine", {})
        
        return workout_data, routine_data


async def get_exercise_templates_async(exercise_template_ids: List[str]) -> List[Dict[str, Any]]:
    """
    Fetch multiple exercise templates in parallel.
    
    Args:
        exercise_template_ids: List of exercise template IDs to fetch
        
    Returns:
        List of exercise template data dictionaries
    """
    async with aiohttp.ClientSession() as session:
        tasks = []
        for template_id in exercise_template_ids:
            url = f"https://api.hevyapp.com/v1/exercise_templates/{template_id}"
            tasks.append(fetch_hevy_api_async(url, session))
        
        # Fetch all exercise templates in parallel
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Filter out None results and exceptions
        exercise_templates = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logging.error(f"Exception fetching exercise template {exercise_template_ids[i]}: {str(result)}")
            elif result is not None:
                exercise_templates.append(result)
        
        return exercise_templates
