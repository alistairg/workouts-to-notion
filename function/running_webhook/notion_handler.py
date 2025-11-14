"""Notion database integration for workout entries."""

import logging
import os
import requests


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
