# Infrastructure Deployment

This directory contains the Bicep Infrastructure as Code (IaC) files for deploying the workouts-to-notion application infrastructure to Azure.

## Structure

- `main.bicep` - Main deployment file scoped at subscription level
- `main.bicepparam` - Parameter file for the main deployment
- `modules/` - Modular Bicep files for specific resource types
  - `openai.bicep` - Azure OpenAI account and model deployment
  - `functionapp.bicep` - Azure Function App with Flex Consumption plan
  - `imagestorage.bicep` - Storage account for uploaded workout images with lifecycle management
  - `imagestorage-rbac.bicep` - RBAC role assignments for image storage account
  - `keyvault.bicep` - Azure Key Vault for storing application secrets

## Resources Deployed

### Resource Group
- **Name**: `rg-workouts-to-notion`
- **Location**: switzerlandnorth (configurable via parameters)

### Azure OpenAI
- **Account Name**: `openai-workouts-to-notion`
- **Model Deployment**: 
  - Name: `gpt-5-mini`
  - Model: `gpt-5-mini`
  - Version: `latest` (auto-upgrades to new defaults)
  - Capacity: 10 (Standard tier)

### Azure Function App (Flex Consumption)
- **Function App Name**: `func-workouts-to-notion`
- **Runtime**: Python 3.11
- **Plan**: Flex Consumption (FC1)
- **Always Ready Instances**: 1 instance for HTTP triggers
- **Instance Memory**: 2048 MB
- **Max Instance Count**: 100
- **Features**:
  - System-assigned managed identity
  - RBAC access to Azure OpenAI (Cognitive Services OpenAI User role)
  - Application Insights for monitoring
  - Storage account for deployment artifacts
  - Configured environment variables for OpenAI and Notion integration

### Image Storage Account
- **Storage Account Name**: `stimagesworkouts`
- **Container Name**: `uploaded-images`
- **Lifecycle Policy**: Automatically deletes blobs after 90 days
- **Access Control**:
  - Storage Blob Data Contributor role assigned to Function App managed identity
  - Storage Blob Data Contributor role assigned to specified user
- **Features**:
  - Blob endpoint configured as environment variable in Function App
  - TLS 1.2 minimum
  - No public blob access
  - 7-day soft delete retention

### Azure Key Vault
- **Key Vault Name**: `kv-workouts-to-notion`
- **Secrets**:
  - `NOTION-API-KEY` - Notion API key (placeholder value on deployment)
  - `NOTION-DATABASE-ID` - Notion database ID for running webhook (placeholder value on deployment)
  - `HEVY-API-KEY` - Hevy Pro API key (placeholder value on deployment)
  - `NOTION-WORKOUTS-DATABASE-ID` - Notion database ID for workouts (placeholder value on deployment)
  - `NOTION-EXERCISES-DATABASE-ID` - Notion database ID for exercises (placeholder value on deployment)
  - `NOTION-EXERCISE-PERFORMANCES-DATABASE-ID` - Notion database ID for exercise performances (placeholder value on deployment)
- **Access Control**:
  - Key Vault Secrets User role assigned to Function App managed identity
  - Key Vault Administrator role assigned to user `d7324995-64ea-4f26-bcb7-4b0f510ea6f9`
- **Features**:
  - RBAC-based authorization (no access policies)
  - Soft delete enabled with 90-day retention
  - Purge protection enabled
  - TLS 1.2 minimum
  - Function App references secrets via Key Vault integration

## Deployment

### Prerequisites
- Azure CLI installed and authenticated
- Bicep CLI installed
- Appropriate permissions to create resources at subscription level

### Deploy Using Azure CLI

```bash
# Login to Azure
az login

# Set the subscription (if you have multiple)
az account set --subscription "your-subscription-id"

# Deploy the infrastructure
az deployment sub create \
  --location switzerlandnorth \
  --template-file main.bicep \
  --parameters main.bicepparam
```

### Deploy Using Parameter Overrides

```bash
az deployment sub create \
  --location switzerlandnorth \
  --template-file main.bicep \
  --parameters location=westus resourceGroupName=rg-custom-name
```

## Outputs

After deployment, the following outputs are available:

- `outputResourceGroupName` - Name of the created resource group
- `outputOpenAIAccountName` - Name of the OpenAI account
- `outputOpenAIDeploymentName` - Name of the model deployment
- `outputOpenAIEndpoint` - Endpoint URL for the OpenAI service
- `outputFunctionAppName` - Name of the Function App
- `outputFunctionAppDefaultHostName` - Default hostname/URL of the Function App
- `outputStorageAccountName` - Name of the storage account used for Function App deployment
- `outputAppInsightsName` - Name of Application Insights instance
- `outputImageStorageAccountName` - Name of the image storage account
- `outputImageBlobEndpoint` - Blob endpoint URL for the image storage account
- `outputImageContainerName` - Name of the blob container for uploaded images
- `outputKeyVaultName` - Name of the Key Vault
- `outputKeyVaultUri` - URI of the Key Vault

## Clean Up

To delete all deployed resources:

```bash
# Delete the resource group (this will delete all resources within it)
az group delete --name rg-workouts-to-notion --yes
```

## Notes

- The OpenAI account uses a custom subdomain based on the account name
- Public network access is enabled by default
- The deployment uses automatic version upgrades for the GPT-5-mini model
- All resources are tagged for easier management and cost tracking
- **Key Vault Secrets**: After deployment, update the placeholder values in Key Vault:
  1. Navigate to the Key Vault in Azure Portal
  2. Go to Secrets
  3. Update `NOTION-API-KEY` with your actual Notion API key
  4. Update `NOTION-DATABASE-ID` with your actual Notion database ID (for running webhook)
  5. Update `HEVY-API-KEY` with your Hevy Pro API key (from https://hevy.com/settings?developer)
  6. Update `NOTION-WORKOUTS-DATABASE-ID` with your Notion Workouts database ID
  7. Update `NOTION-EXERCISES-DATABASE-ID` with your Notion Exercises database ID
  8. Update `NOTION-EXERCISE-PERFORMANCES-DATABASE-ID` with your Notion Exercise Performances database ID
  9. The Function App will automatically pick up the new values (no restart required)
- The Function App uses managed identity for Azure OpenAI and Key Vault authentication (no API keys needed)
- Storage Blob Data Owner role is automatically assigned to the Function App's managed identity for deployment storage
- **Image Storage**: The `uploaded-images` container automatically deletes files older than 90 days
- The image storage blob endpoint is automatically configured in the Function App as `AZURE_STORAGE_BLOB_ENDPOINT`
- Both the Function App and the specified user have Storage Blob Data Contributor access to the image storage account
- **Deployment Order**: Image storage is deployed first, then Function App (to get managed identity), then Key Vault (to assign RBAC), then storage RBAC assignments
- **Security**: All secrets are stored in Key Vault and referenced by the Function App using Key Vault references in app settings
