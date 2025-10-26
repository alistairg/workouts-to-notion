metadata description = 'Deploys Azure OpenAI account and gpt-5-mini model deployment'

// Parameters
@description('The location for the OpenAI resources')
param paramLocation string

@description('Tags to apply to resources')
param paramTags object

@description('The name of the OpenAI account')
param paramAccountName string

@description('The name of the model deployment')
param paramDeploymentName string

@description('The SKU name for the OpenAI account')
param paramSkuName string

@description('The principal ID of the user to assign OpenAI User role')
param paramUserPrincipalId string

// Variables
var varCognitiveServicesOpenAIUserRoleId = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'

// Deploy Azure OpenAI Account
resource resOpenAIAccount 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' = {
  name: paramAccountName
  location: paramLocation
  tags: paramTags
  kind: 'OpenAI'
  sku: {
    name: paramSkuName
  }
  properties: {
    customSubDomainName: paramAccountName
    publicNetworkAccess: 'Enabled'
    networkAcls: {
      defaultAction: 'Allow'
    }
  }
}

// Deploy GPT-5-mini model
resource resGpt5MiniDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-04-01-preview' = {
  parent: resOpenAIAccount
  name: paramDeploymentName
  sku: {
    name: 'GlobalStandard'
    capacity: 10
  }
  properties: {
    model: {
      format: 'OpenAI'
      name: 'gpt-5-mini'
      version: '2025-08-07'
    }
    versionUpgradeOption: 'OnceNewDefaultVersionAvailable'
  }
}

// RBAC Role Assignment - Cognitive Services OpenAI User
resource resOpenAIUserRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resOpenAIAccount.id, paramUserPrincipalId, varCognitiveServicesOpenAIUserRoleId)
  scope: resOpenAIAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', varCognitiveServicesOpenAIUserRoleId)
    principalId: paramUserPrincipalId
    principalType: 'User'
  }
}

// Outputs
output outputAccountName string = resOpenAIAccount.name
output outputAccountId string = resOpenAIAccount.id
output outputDeploymentName string = resGpt5MiniDeployment.name
output outputEndpoint string = resOpenAIAccount.properties.endpoint
