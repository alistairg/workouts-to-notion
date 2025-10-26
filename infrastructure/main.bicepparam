using './main.bicep'

// Parameters for the main deployment
param paramLocation = 'switzerlandnorth'
param paramResourceGroupName = 'rg-workouts-to-notion'
param paramTags = {}

// OpenAI parameters
param paramOpenAIAccountName = 'openai-workouts-to-notion'
param paramOpenAIDeploymentName = 'gpt-5-mini'
param paramOpenAISkuName = 'S0'
param paramOpenAIUserPrincipalId = 'd7324995-64ea-4f26-bcb7-4b0f510ea6f9'

// Function App parameters
param paramFunctionAppName = 'func-workouts-to-notion'
param paramFunctionStorageAccountName = 'stworkoutstonotion'
param paramAppInsightsName = 'appi-workouts-to-notion'
param paramInstanceMemoryMB = 2048
param paramMaximumInstanceCount = 100

// Key Vault parameters
param paramKeyVaultName = 'kv-workouts-to-notion'

// Image Storage parameters
param paramImageStorageAccountName = 'stimagesworkouts'
