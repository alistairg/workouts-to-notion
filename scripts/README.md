# Hevy Workouts Sync Scripts

This directory contains utility scripts for syncing Hevy workout data to Notion.

## Scripts

### `sync_hevy_workouts.py`

Syncs historical Hevy workouts to Notion via the Azure Function App.

**What it does:**
1. Fetches all workouts from Hevy API since October 20, 2024
2. Sends each workout to the Function App webhook for processing
3. The Function App then creates/updates entries in Notion databases:
   - Workouts
   - Exercises
   - Exercise Performances

**Prerequisites:**
```bash
pip install -r requirements.txt
```

**Environment Variables:**
- `HEVY_API_KEY` - Your Hevy Pro API key (optional, defaults to the one in the script)

**Usage:**
```bash
# Run the sync
python sync_hevy_workouts.py
```

**Configuration:**
You can modify these constants in the script:
- `START_DATE` - Start date for fetching workouts (default: "2024-10-20")
- `RATE_LIMIT_DELAY` - Delay between requests in seconds (default: 1)
- `HEVY_API_KEY` - Hevy API key (can also use environment variable)

**Output:**
The script will:
- Show progress for each workout being processed
- Display a summary at the end with success/failure counts
- Exit with code 0 on success, 1 if any workouts failed

**Example Output:**
```
======================================================================
Hevy Workouts Sync Script
======================================================================
Start Date: 2024-10-20
Function App URL: https://func-workouts-to-notion.azurewebsites.net...
Hevy API Key: 5eba...8653
======================================================================

Fetching workouts from Hevy API since 2024-10-20...
Fetched page 1: 50 workouts (total so far: 50)
Fetched page 2: 30 workouts (total so far: 80)
Total workouts fetched: 80

Found 80 workouts to sync
----------------------------------------------------------------------
[1/80] Processing workout: Upper Body 💪 (2024-11-08)
  Workout ID: e5c2aed1-ed04-48f2-a20d-d2090ba9180e
  ✓ Successfully sent to Function App
[2/80] Processing workout: Lower Body 🦵 (2024-11-07)
  Workout ID: 33d86225-580a-4f19-a0e8-4ed4808dc81c
  ✓ Successfully sent to Function App
...

======================================================================
Sync Summary
======================================================================
Total workouts: 80
Successful: 80
Failed: 0
======================================================================

✓ All workouts synced successfully!
```

**Notes:**
- The script handles pagination automatically
- Workouts are sent one at a time with a delay to avoid rate limiting
- The Function App will automatically deduplicate workouts, exercises, and performances
- Each workout triggers the full processing pipeline (fetch from Hevy, process exercises, create performances)
- Progress is shown in real-time

**Troubleshooting:**
- If you get a 401 error, check that your Hevy API key is correct
- If you get a 500 error from the Function App, check the Azure logs
- The script will stop at older workouts automatically based on the start date
- You can re-run the script safely - duplicates will be updated, not created

## Other Scripts

### `webhook-capture/` (Development)
Scripts for capturing webhook payloads during development/testing.
