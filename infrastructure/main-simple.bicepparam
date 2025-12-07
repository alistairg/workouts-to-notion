using './main-simple.bicep'

// Parameters for the simplified deployment (no OpenAI)
param paramLocation = 'westus2'
param paramResourceGroupName = 'hevy-notion'
param paramTags = {}

// Function App parameters
param paramFunctionAppName = 'func-hevy-notion'
param paramFunctionStorageAccountName = 'sthevynotion'
param paramAppInsightsName = 'appi-hevy-notion'
param paramInstanceMemoryMB = 2048
param paramMaximumInstanceCount = 100

// Key Vault parameters
param paramKeyVaultName = 'kv-hevy-notion'

// User principal ID for RBAC (get yours with: az ad signed-in-user show --query id -o tsv)
param paramUserPrincipalId = 'YOUR_AZURE_USER_PRINCIPAL_ID'
