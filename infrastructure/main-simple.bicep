targetScope = 'subscription'

metadata description = 'Simplified deployment for Hevy-to-Notion sync (no OpenAI)'

// Parameters
@description('The location for all resources')
param paramLocation string

@description('The name of the resource group')
param paramResourceGroupName string

@description('Tags to apply to all resources')
param paramTags object

@description('The name of the Function App')
param paramFunctionAppName string

@description('The name of the storage account for Function App deployment')
param paramFunctionStorageAccountName string

@description('The name of Application Insights for Function App')
param paramAppInsightsName string

@description('The name of the Key Vault')
param paramKeyVaultName string

@description('Function App instance memory in MB')
param paramInstanceMemoryMB int = 2048

@description('Function App maximum instance count')
param paramMaximumInstanceCount int = 100

@description('The principal ID of the user for RBAC assignment')
param paramUserPrincipalId string

// Deploy Resource Group
resource resResourceGroup 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: paramResourceGroupName
  location: paramLocation
  tags: paramTags
}

// Deploy Function App module
module modFunctionApp 'modules/functionapp-simple.bicep' = {
  scope: resResourceGroup
  name: 'functionapp-deployment'
  params: {
    paramLocation: paramLocation
    paramTags: paramTags
    paramFunctionAppName: paramFunctionAppName
    paramStorageAccountName: paramFunctionStorageAccountName
    paramAppInsightsName: paramAppInsightsName
    paramInstanceMemoryMB: paramInstanceMemoryMB
    paramMaximumInstanceCount: paramMaximumInstanceCount
    paramKeyVaultName: paramKeyVaultName
    paramUserPrincipalId: paramUserPrincipalId
  }
}

// Deploy Key Vault and secrets
module modKeyVault 'modules/keyvault.bicep' = {
  scope: resResourceGroup
  name: 'keyvault-deployment'
  params: {
    paramLocation: paramLocation
    paramTags: paramTags
    paramKeyVaultName: paramKeyVaultName
    paramFunctionAppPrincipalId: modFunctionApp.outputs.outputFunctionAppPrincipalId
    paramUserPrincipalId: paramUserPrincipalId
  }
}

// Outputs
output outputResourceGroupName string = resResourceGroup.name
output outputFunctionAppName string = modFunctionApp.outputs.outputFunctionAppName
output outputFunctionAppDefaultHostName string = modFunctionApp.outputs.outputFunctionAppDefaultHostName
output outputStorageAccountName string = modFunctionApp.outputs.outputStorageAccountName
output outputAppInsightsName string = modFunctionApp.outputs.outputAppInsightsName
output outputKeyVaultName string = modKeyVault.outputs.outputKeyVaultName
output outputKeyVaultUri string = modKeyVault.outputs.outputKeyVaultUri
