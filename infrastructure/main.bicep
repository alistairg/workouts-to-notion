targetScope = 'subscription'

metadata description = 'Main deployment for workouts-to-notion infrastructure'

// Parameters
@description('The location for all resources')
param paramLocation string

@description('The name of the resource group')
param paramResourceGroupName string

@description('Tags to apply to all resources')
param paramTags object

@description('The name of the OpenAI account')
param paramOpenAIAccountName string

@description('The name of the OpenAI model deployment')
param paramOpenAIDeploymentName string

@description('The SKU name for the OpenAI account')
param paramOpenAISkuName string

@description('The principal ID of the user to assign OpenAI User role')
param paramOpenAIUserPrincipalId string

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

@description('The name of the storage account for uploaded images')
param paramImageStorageAccountName string

// Deploy Resource Group
resource resResourceGroup 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: paramResourceGroupName
  location: paramLocation
  tags: paramTags
}

// Deploy OpenAI resources within the Resource Group
module modOpenAI 'modules/openai.bicep' = {
  scope: resResourceGroup
  name: 'openai-deployment'
  params: {
    paramLocation: paramLocation
    paramTags: paramTags
    paramAccountName: paramOpenAIAccountName
    paramDeploymentName: paramOpenAIDeploymentName
    paramSkuName: paramOpenAISkuName
    paramUserPrincipalId: paramOpenAIUserPrincipalId
  }
}

// Deploy Image Storage Account first (no dependencies)
module modImageStorage 'modules/imagestorage.bicep' = {
  scope: resResourceGroup
  name: 'imagestorage-deployment'
  params: {
    paramLocation: paramLocation
    paramTags: paramTags
    paramImageStorageAccountName: paramImageStorageAccountName
  }
}

// Deploy Function App with Flex Consumption plan (with image storage blob endpoint)
module modFunctionApp 'modules/functionapp.bicep' = {
  scope: resResourceGroup
  name: 'functionapp-deployment'
  params: {
    paramLocation: paramLocation
    paramTags: paramTags
    paramFunctionAppName: paramFunctionAppName
    paramStorageAccountName: paramFunctionStorageAccountName
    paramAppInsightsName: paramAppInsightsName
    paramOpenAIEndpoint: modOpenAI.outputs.outputEndpoint
    paramOpenAIDeploymentName: modOpenAI.outputs.outputDeploymentName
    paramOpenAIAccountId: modOpenAI.outputs.outputAccountId
    paramInstanceMemoryMB: paramInstanceMemoryMB
    paramMaximumInstanceCount: paramMaximumInstanceCount
    paramImageBlobEndpoint: modImageStorage.outputs.outputBlobEndpoint
    paramKeyVaultName: paramKeyVaultName
    paramUserPrincipalId: paramOpenAIUserPrincipalId
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
    paramUserPrincipalId: paramOpenAIUserPrincipalId
  }
}

// Assign RBAC roles for image storage
module modImageStorageRBAC 'modules/imagestorage-rbac.bicep' = {
  scope: resResourceGroup
  name: 'imagestorage-rbac-deployment'
  params: {
    paramImageStorageAccountId: modImageStorage.outputs.outputStorageAccountId
    paramFunctionAppPrincipalId: modFunctionApp.outputs.outputFunctionAppPrincipalId
    paramUserPrincipalId: paramOpenAIUserPrincipalId
  }
}

// Outputs
output outputResourceGroupName string = resResourceGroup.name
output outputOpenAIAccountName string = modOpenAI.outputs.outputAccountName
output outputOpenAIDeploymentName string = modOpenAI.outputs.outputDeploymentName
output outputOpenAIEndpoint string = modOpenAI.outputs.outputEndpoint
output outputFunctionAppName string = modFunctionApp.outputs.outputFunctionAppName
output outputFunctionAppDefaultHostName string = modFunctionApp.outputs.outputFunctionAppDefaultHostName
output outputStorageAccountName string = modFunctionApp.outputs.outputStorageAccountName
output outputAppInsightsName string = modFunctionApp.outputs.outputAppInsightsName
output outputImageStorageAccountName string = modImageStorage.outputs.outputStorageAccountName
output outputImageBlobEndpoint string = modImageStorage.outputs.outputBlobEndpoint
output outputImageContainerName string = modImageStorage.outputs.outputContainerName
output outputKeyVaultName string = modKeyVault.outputs.outputKeyVaultName
output outputKeyVaultUri string = modKeyVault.outputs.outputKeyVaultUri
