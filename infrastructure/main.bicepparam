using './main.bicep'

// Parameters for the main deployment
param paramLocation = 'westus2'
param paramResourceGroupName = 'hevy-notion'
param paramTags = {}

// OpenAI parameters
param paramOpenAIAccountName = 'openai-hevy-notion'
param paramOpenAIDeploymentName = 'gpt-4o-mini'
param paramOpenAISkuName = 'S0'
// Get your principal ID with: az ad signed-in-user show --query id -o tsv
param paramOpenAIUserPrincipalId = 'YOUR_AZURE_USER_PRINCIPAL_ID'

// Function App parameters
param paramFunctionAppName = 'func-hevy-notion'
param paramFunctionStorageAccountName = 'sthevynotion'
param paramAppInsightsName = 'appi-hevy-notion'
param paramInstanceMemoryMB = 2048
param paramMaximumInstanceCount = 100

// Key Vault parameters
param paramKeyVaultName = 'kv-hevy-notion'

// Image Storage parameters
param paramImageStorageAccountName = 'stimageshevy'
