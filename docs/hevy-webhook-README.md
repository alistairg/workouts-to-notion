# Hevy Webhook Integration

This document describes the Hevy webhook integration that automatically syncs workout data from the Hevy app to the Notion "Workouts" database.

## Overview

When a workout is completed in the Hevy app, a webhook is triggered that:
1. Receives the workout ID from Hevy
2. Fetches complete workout details from the Hevy API
3. Fetches routine information (if the workout was part of a routine)
4. Creates or updates entries in three Notion databases:
   - **Workouts Database**: Main workout entry
   - **Exercises Database**: Exercise templates used
   - **Exercise Performances Database**: Individual exercise performances with aggregated stats

## Webhook Flow

```
Hevy App → Webhook Trigger → Azure Function → Hevy API → Notion Databases
                                                           ├─ Workouts
                                                           ├─ Exercises
                                                           └─ Exercise Performances
```

### Step-by-Step Process

1. **Webhook Reception**: The Azure Function receives a POST request with the workout ID
2. **Validation**: Request size and rate limiting checks are performed
3. **Parallel Fetch - Workout & Routine**: 
   - Workout details are fetched from Hevy API (`GET /v1/workouts/{workoutId}`)
   - If routine ID exists, routine details are fetched in parallel (`GET /v1/routines/{routineId}`)
4. **Extract Unique Exercises**: Identifies all unique exercises from the workout
5. **Parallel Fetch - Exercise Templates**: All exercise templates are fetched concurrently
6. **Parallel Process - Exercises**: Each exercise is created/updated in Notion Exercises database
7. **Calculate Duration**: Workout duration is calculated from timestamps or provided directly
8. **Create/Update Workout Entry**: Workout is created or updated in Notion "Workouts" database
9. **Aggregate Performance Data**: Sets are grouped by exercise, calculating total weight (volume) and total reps
10. **Parallel Process - Exercise Performances**: Individual exercise performances are created in Notion with relations to workout and exercise

**⚡ Performance Optimization**: The function uses parallel HTTP requests (`asyncio` + `aiohttp`) to ensure completion within 5 seconds even for workouts with many exercises and performances.

## Performance

The webhook is optimized for speed with parallel processing:

### Parallel Execution Strategy

**Phase 1: Workout & Routine (Parallel)**
- Workout details and routine details are fetched simultaneously
- If no routine exists, only workout is fetched

**Phase 2: Exercise Templates (Parallel)**
- All unique exercise templates are fetched concurrently
- Uses `asyncio.gather()` for maximum parallelism

### Performance Metrics

| Scenario | Sequential Time | Parallel Time | Speedup |
|----------|----------------|---------------|---------|
| 5 exercises | ~3-4 seconds | ~1-2 seconds | 2-3x |
| 10 exercises | ~6-8 seconds | ~1-2 seconds | 4-6x |
| 15 exercises | ~9-12 seconds | ~2-3 seconds | 4-5x |

**Note**: Times include API calls to both Hevy and Notion. Actual times may vary based on network latency and API response times.

## Webhook Payload

The webhook receives a JSON payload from Hevy in the following format:

```json
{
  "id": "00000000-0000-0000-0000-000000000001",
  "payload": {
    "workoutId": "f1085cdb-32b2-4003-967d-53a3af8eaecb"
  }
}
```

## Notion Database Mapping

The following fields are populated in the Notion "Workouts" database:

| Notion Field | Type | Source | Description |
|--------------|------|--------|-------------|
| `Hevy ID` | title | workout.id | Unique workout identifier from Hevy |
| `Workout Date` | date | workout.start_time | Date when the workout was performed |
| `Duration` | number | workout.duration_seconds | Duration in minutes (calculated from seconds) |
| `Routine` | select | routine.title | Name of the routine (e.g., "Upper Body 💪") |
| `Exercise Performances` | relation | (future) | Links to individual exercise performances |
| `Total Weight (KG)` | rollup | (calculated) | Automatically calculated from exercise performances |

## Environment Variables

The following environment variables must be configured:

### Hevy API Configuration
- `HEVY_API_KEY`: Your Hevy Pro API key (get it from https://hevy.com/settings?developer)

### Notion Configuration
- `NOTION_API_KEY`: Your Notion integration API key
- `NOTION_WORKOUTS_DATABASE_ID`: Database ID for the Workouts database (`2a4c2516b45880cbaec1f51bdf647061`)
- `NOTION_EXERCISES_DATABASE_ID`: Database ID for the Exercises database (`2a4c2516b4588044ada1c6c7b072c192`)
- `NOTION_EXERCISE_PERFORMANCES_DATABASE_ID`: Database ID for the Exercise Performances database (`2a4c2516b45880fb9f9ed477db7eefd9`)

## Files

### `hevy_webhook.py`
Main webhook handler that orchestrates the entire workflow:
- Validates incoming requests
- Coordinates API calls to Hevy and Notion
- Handles error cases and logging

### `hevy_api.py`
Helper functions for interacting with the Hevy API:

- `get_workout_details(workout_id)`: Fetches complete workout data
- `get_routine_details(routine_id)`: Fetches routine information
- `get_exercise_template(exercise_template_id)`: Fetches exercise template details
- `calculate_workout_duration(workout_data)`: Calculates duration from timestamps
- `extract_unique_exercises(workout_data)`: Extracts unique exercises from workout
- `extract_exercise_performances(workout_data)`: Aggregates sets by exercise, calculating total weight (volume) and total reps
- Async functions for parallel API calls: `get_workout_and_routine_async()`, `get_exercise_templates_async()`

### `notion_handler.py`
Notion integration for creating workout, exercise, and performance entries:

- `add_workout_to_notion(workout_data, routine_name)`: Creates or updates a workout page in the Workouts database
- `add_exercise_to_notion(exercise_template_data)`: Creates or updates an exercise in the Exercises database
- `process_exercises_async(exercise_templates)`: Processes multiple exercises in parallel
- `process_exercise_performances_async(performance_data_list, workout_page_id, exercise_notion_pages)`: Creates exercise performance entries in parallel with relations to workout and exercises
- `ensure_routine_option_exists(routine_name)`: Logs routine option creation

## API Reference

### Hevy API Endpoints Used

- **GET /v1/workouts/{workoutId}**
  - Retrieves complete workout details
  - Authentication: `api-key` header
  - Response includes: id, start_time, duration_seconds, routine_id, exercises, sets

- **GET /v1/routines/{routineId}**
  - Retrieves routine details
  - Authentication: `api-key` header
  - Response includes: id, title, exercises

- **GET /v1/exercise_templates/{exerciseTemplateId}**
  - Retrieves exercise template details
  - Authentication: `api-key` header
  - Response includes: id, title, type, primary_muscle_group, secondary_muscle_groups, is_custom

### Notion API Endpoints Used

- **POST /v1/pages**
  - Creates a new page in a database
  - Authentication: Bearer token
  - Automatically creates new select/multi_select options if they don't exist

- **POST /v1/databases/{database_id}/query**
  - Queries a database to find existing pages
  - Used to check if exercises already exist before creating duplicates
  - Authentication: Bearer token

- **PATCH /v1/pages/{page_id}**
  - Updates an existing page's properties
  - Used to update exercise information when it already exists
  - Authentication: Bearer token

## Error Handling

The webhook handles various error scenarios:

| Error | HTTP Status | Description |
|-------|-------------|-------------|
| Missing required fields | 400 | Webhook payload is missing `id` or `workoutId` |
| Invalid JSON | 400 | Request body is not valid JSON |
| Request too large | 413 | Request exceeds 10MB limit |
| Rate limit exceeded | 429 | Too many requests from the same IP |
| HEVY_API_KEY not set | 500 | Missing Hevy API configuration |
| Notion config missing | 500 | Missing Notion API configuration |
| Failed to fetch workout | 502 | Hevy API returned an error |
| Failed to create Notion page | 500 | Notion API returned an error |

## Testing

### Local Testing

1. Start the Azure Functions locally:
   ```bash
   cd function
   func start
   ```

2. Send a test webhook payload:
   ```bash
   curl -X POST http://localhost:7071/api/hevy_workout_webhook \
     -H "Content-Type: application/json" \
     -d '{
       "id": "test-webhook-001",
       "payload": {
         "workoutId": "f1085cdb-32b2-4003-967d-53a3af8eaecb"
       }
     }'
   ```

### Webhook Setup in Hevy

1. Log in to Hevy Pro at https://hevy.com/settings?developer
2. Get your API key
3. Set up a webhook subscription using the API:
   ```bash
   curl -X POST https://api.hevyapp.com/v1/webhook-subscription \
     -H "api-key: YOUR_HEVY_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{
       "webhook_subscription": {
         "url": "https://func-workouts-to-notion.azurewebsites.net/api/hevy_workout_webhook",
         "events": ["workout.created", "workout.updated"]
       }
     }'
   ```

## Logging

The webhook logs the following information:

- Webhook reception and validation
- Workout and routine fetch operations
- Notion page creation
- All errors with detailed messages

View logs in Azure Portal:
1. Navigate to your Function App
2. Go to "Monitoring" > "Logs"
3. Or use Application Insights for advanced querying

## Exercise Processing

When a workout is synced, the function also processes all unique exercises:

1. **Extract Unique Exercises**: Identifies all unique exercises by `exercise_template_id`
2. **Fetch Exercise Templates**: Retrieves detailed exercise information from Hevy API
3. **Create/Update in Notion**: Adds or updates exercises in the "Exercises" database

### Exercise Data Mapping

| Notion Field | Type | Source | Description |
|--------------|------|--------|-------------|
| `Name` | title | exercise_template.title | Exercise name (e.g., "Bench Press (Barbell)") |
| `Hevy ID` | text | exercise_template.id | Unique exercise template identifier |
| `Primary Muscle Group` | select | exercise_template.primary_muscle_group | Primary muscle worked (e.g., "Chest") |
| `Secondary Muscle Groups` | multi_select | exercise_template.secondary_muscle_groups | Additional muscles worked |
| `Exercise Performances` | relation | (future) | Links to individual performances |

### Exercise Deduplication

The function automatically handles duplicate exercises:
- Searches for existing exercises by Hevy ID
- Updates existing entries if found
- Creates new entries only if exercise doesn't exist

This ensures each exercise template appears only once in the database, even if used in multiple workouts.

## Future Enhancements

The following features are planned for future implementation:

1. **Exercise Performances**: Create linked entries in the "Exercise Performances" database with set-by-set data
2. **Update Support**: Handle workout updates (currently only creates new entries)
3. **Bulk Sync**: Add ability to sync historical workouts
4. **Custom Fields**: Support for custom fields in Hevy (e.g., notes, tags)
5. **Exercise Images**: Fetch and store exercise demonstration images

## Troubleshooting

### Workout not syncing

1. Check that the webhook is properly configured in Hevy
2. Verify environment variables are set correctly
3. Check Function App logs for errors
4. Ensure Hevy API key has not expired
5. Verify Notion database ID is correct

### Routine name not appearing

1. Check that the workout was created from a routine in Hevy
2. Verify the routine still exists in your Hevy account
3. Check logs for routine fetch errors

### Duration not calculated

1. Ensure workout has `start_time` and `end_time` fields
2. Or check that `duration_seconds` is provided by Hevy API
3. Review logs for calculation errors

## Security Considerations

- API keys are stored as environment variables and never logged
- Rate limiting prevents abuse of the webhook endpoint
- Request size limits prevent memory exhaustion
- All external API calls have timeouts configured
- Input validation prevents injection attacks

## Related Documentation

- [Hevy API Documentation](https://api.hevyapp.com/docs)
- [Notion API Documentation](https://developers.notion.com)
- [Azure Functions Python Developer Guide](https://learn.microsoft.com/azure/azure-functions/functions-reference-python)
