# Workouts to Notion

An Azure Function-based webhook service that syncs workout information from Apple Fitness and Hevy to Notion. The function uses Azure OpenAI to intelligently parse and categorize workout data, storing workout images in Azure Blob Storage with automatic lifecycle management.

## Overview

This project provides an HTTP-triggered Azure Function that:

- Receives workout data via webhook (POST requests)
- Processes workout screenshots using Azure OpenAI's vision capabilities
- Extracts exercise details, sets, reps, and weights
- Uploads workout images to Azure Blob Storage
- Creates or updates entries in a Notion database
- Automatically manages image lifecycle (90-day retention)

## Architecture

### Azure Resources

- **Azure Function App** (Flex Consumption) - Python 3.11 runtime
- **Azure OpenAI** - GPT-5-mini Vision for workout image analysis
- **Azure Storage Account** - Blob storage for workout images
- **Azure Key Vault** - Secure storage for Notion API credentials
- **Application Insights** - Monitoring and diagnostics

### Key Features

- System-assigned managed identity for secure Azure service access
- RBAC-based permissions (no connection strings)
- Automatic image deletion after 90 days
- Rate limiting (10 requests/minute per client)
- Image validation and size limits (10MB max)
- Support for JPEG, PNG, and HEIC formats

## Prerequisites

- Azure CLI installed and configured
- Azure subscription with appropriate permissions
- VS Code with Azure Functions extension
- Python 3.11
- Notion API key and database ID

## Deployment

### 1. Deploy Infrastructure

The infrastructure is defined using Bicep (Infrastructure as Code) in the `infrastructure/` directory.

```bash
# Login to Azure
az login

# Set your subscription (if you have multiple)
az account set --subscription "your-subscription-id"

# Deploy infrastructure to Azure
az deployment sub create \
  --location switzerlandnorth \
  --template-file infrastructure/main.bicep \
  --parameters infrastructure/main.bicepparam
```

This will create:

- Resource group: `rg-workouts-to-notion`
- Azure OpenAI account with GPT-5-mini deployment
- Azure Function App with Flex Consumption plan
- Storage account for workout images
- Key Vault for secrets
- All necessary RBAC role assignments

**Note**: After deployment, you need to manually update the Key Vault secrets:

- `NOTION-API-KEY` - Your Notion integration API key
- `NOTION-DATABASE-ID` - Your Notion database ID


For detailed infrastructure documentation, see [docs/infra-README.md](docs/infra-README.md).

### 2. Deploy Azure Function Code

The Azure Function code is deployed manually through VS Code:

1. **Open the project in VS Code**

   ```bash
   code .
   ```

2. **Install Azure Functions extension**

   - Search for "Azure Functions" in VS Code extensions
   - Install the extension from Microsoft

3. **Deploy the function**

   - Open the Azure Functions extension panel
   - Sign in to Azure if not already signed in
   - Right-click on the `function` folder
   - Select "Deploy to Function App..."
   - Choose your subscription
   - Select the function app created by the infrastructure deployment (`func-workouts-to-notion`)
   - Confirm the deployment

4. **Verify deployment**

   - Once deployed, get the function URL from the Azure portal or VS Code
   - The webhook endpoint will be available at: `https://func-workouts-to-notion.azurewebsites.net/api/workout_webhook`


## Configuration

### Notion Setup

1. Create a Notion integration at <https://www.notion.so/my-integrations>
2. Create a database in Notion with the following properties:
   - Title (title type)
   - Date (date type)
   - Exercises (text type)
   - Image URL (url type)
   - Any additional properties you want

3. Share the database with your integration
4. Copy the API key and database ID
5. Update the Key Vault secrets in Azure:

   ```bash
   az keyvault secret set --vault-name kv-workouts-to-notion --name NOTION-API-KEY --value "your-api-key"
   az keyvault secret set --vault-name kv-workouts-to-notion --name NOTION-DATABASE-ID --value "your-database-id"
   ```


### Webhook Setup

Configure your workout app (Apple Fitness, Hevy, etc.) to send POST requests to:

```text
https://func-workouts-to-notion.azurewebsites.net/api/workout_webhook?code=<function-key>
```

Get the function key from:

- Azure Portal → Function App → Functions → workout_webhook → Function Keys
- Or from VS Code Azure Functions extension


## Usage

Send a POST request with workout data:

```json
{
  "image": "base64-encoded-image-data",
  "filename": "workout.png",
  "date": "2025-10-26"
}
```

The function will:

1. Validate the image (format, size)
2. Upload to Azure Blob Storage
3. Analyze with Azure OpenAI
4. Create/update Notion entry
5. Return the Notion page URL


## Local Development

1. **Install dependencies**

   ```bash
   cd function
   pip install -r requirements.txt
   ```

2. **Configure local settings**

   - Copy `function/local.settings.json.example` to `function/local.settings.json` (if exists)
   - Configure Azure OpenAI, Storage, and Notion credentials

3. **Run locally**

   - Use VS Code's "Run Task" → "func: host start"
   - Or run: `func host start` in the `function/` directory

4. **Test locally**

   ```bash
   curl -X POST http://localhost:7071/api/workout_webhook \
     -H "Content-Type: application/json" \
     -d '{"image": "...", "filename": "test.png"}'
   ```


## Project Structure

```
workouts-to-notion/
├── function/              # Azure Function code
│   ├── function_app.py   # Main function logic
│   ├── requirements.txt  # Python dependencies
│   └── host.json        # Function host configuration
├── infrastructure/       # Bicep IaC files
│   ├── main.bicep       # Main deployment
│   ├── main.bicepparam  # Parameters
│   └── modules/         # Modular Bicep files
├── docs/                # Documentation
│   └── infra-README.md  # Infrastructure details
└── scripts/             # Utility scripts
```

## Security

- All Azure resources use managed identities (no connection strings)
- RBAC-based access control throughout
- Secrets stored in Azure Key Vault
- HTTPS-only endpoints
- TLS 1.2 minimum
- No public blob access
- Rate limiting enabled

## Monitoring

Application Insights is automatically configured. View metrics in:

- Azure Portal → Function App → Application Insights
- Logs, performance, failures, and dependencies are tracked


## License

See [LICENSE](LICENSE) file for details.
