metadata description = 'Deploys Azure Function App with Flex Consumption plan for workouts-to-notion'

// Parameters
@description('The location for the Function App resources')
param paramLocation string

@description('Tags to apply to resources')
param paramTags object

@description('The name of the Function App')
param paramFunctionAppName string

@description('The name of the storage account for deployment')
param paramStorageAccountName string

@description('The name of the Application Insights instance')
param paramAppInsightsName string

@description('The Azure OpenAI endpoint')
param paramOpenAIEndpoint string

@description('The Azure OpenAI deployment name')
param paramOpenAIDeploymentName string

@description('The Azure OpenAI account resource ID for RBAC assignment')
param paramOpenAIAccountId string

@description('The name of the Key Vault containing secrets')
param paramKeyVaultName string

@description('Instance memory in MB')
param paramInstanceMemoryMB int = 2048

@description('Maximum instance count')
param paramMaximumInstanceCount int = 100

@description('The blob endpoint URL for uploaded images storage')
param paramImageBlobEndpoint string

@description('The principal ID of the user for RBAC assignment')
param paramUserPrincipalId string

// Variables
var varCognitiveServicesOpenAIUserRoleId = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'
var varStorageBlobDataContributorRoleId = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'

// Storage Account for Function App deployment
resource resStorageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: paramStorageAccountName
  location: paramLocation
  tags: paramTags
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    supportsHttpsTrafficOnly: true
    encryption: {
      services: {
        blob: {
          enabled: true
        }
        file: {
          enabled: true
        }
      }
      keySource: 'Microsoft.Storage'
    }
  }

  resource resBlobService 'blobServices' = {
    name: 'default'

    resource resDeploymentsContainer 'containers' = {
      name: 'deployments'
      properties: {
        publicAccess: 'None'
      }
    }
  }
}

// Application Insights
resource resAppInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: paramAppInsightsName
  location: paramLocation
  tags: paramTags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    publicNetworkAccessForIngestion: 'Enabled'
    publicNetworkAccessForQuery: 'Enabled'
  }
}

// App Service Plan (Flex Consumption)
resource resAppServicePlan 'Microsoft.Web/serverfarms@2023-12-01' = {
  name: 'asp-${paramFunctionAppName}'
  location: paramLocation
  tags: paramTags
  sku: {
    name: 'FC1'
    tier: 'FlexConsumption'
  }
  properties: {
    reserved: true // Linux
  }
}

// Function App
resource resFunctionApp 'Microsoft.Web/sites@2023-12-01' = {
  name: paramFunctionAppName
  location: paramLocation
  tags: paramTags
  kind: 'functionapp,linux'
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    serverFarmId: resAppServicePlan.id
    reserved: true
    httpsOnly: true
    functionAppConfig: {
      deployment: {
        storage: {
          type: 'blobContainer'
          value: '${resStorageAccount.properties.primaryEndpoints.blob}deployments'
          authentication: {
            type: 'SystemAssignedIdentity'
          }
        }
      }
      scaleAndConcurrency: {
        instanceMemoryMB: paramInstanceMemoryMB
        maximumInstanceCount: paramMaximumInstanceCount
        alwaysReady: [
          {
            name: 'http'
            instanceCount: 1
          }
        ]
      }
      runtime: {
        name: 'python'
        version: '3.11'
      }
    }
    siteConfig: {
      appSettings: [
        {
          name: 'AzureWebJobsStorage__accountName'
          value: resStorageAccount.name
        }
        {
          name: 'APPLICATIONINSIGHTS_CONNECTION_STRING'
          value: resAppInsights.properties.ConnectionString
        }
        {
          name: 'AZURE_OPENAI_ENDPOINT'
          value: paramOpenAIEndpoint
        }
        {
          name: 'AZURE_OPENAI_DEPLOYMENT_NAME'
          value: paramOpenAIDeploymentName
        }
        {
          name: 'NOTION_API_KEY'
          value: '@Microsoft.KeyVault(VaultName=${paramKeyVaultName};SecretName=NOTION-API-KEY)'
        }
        {
          name: 'NOTION_DATABASE_ID'
          value: '@Microsoft.KeyVault(VaultName=${paramKeyVaultName};SecretName=NOTION-DATABASE-ID)'
        }
        {
          name: 'AZURE_STORAGE_BLOB_ENDPOINT'
          value: paramImageBlobEndpoint
        }
      ]
      ftpsState: 'Disabled'
      minTlsVersion: '1.2'
    }
  }
}

// RBAC: Grant Function App managed identity Storage Blob Data Owner role on storage account
resource resStorageBlobDataOwnerRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resStorageAccount.id, resFunctionApp.id, 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
  scope: resStorageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', 'ba92f5b4-2d11-453d-a403-e96b0029c9fe')
    principalId: resFunctionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// RBAC: Grant User Storage Blob Data Contributor role on storage account
resource resUserBlobDataContributorRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resStorageAccount.id, paramUserPrincipalId, varStorageBlobDataContributorRoleId)
  scope: resStorageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', varStorageBlobDataContributorRoleId)
    principalId: paramUserPrincipalId
    principalType: 'User'
  }
}

// Reference to OpenAI account for RBAC assignment
resource resOpenAIAccount 'Microsoft.CognitiveServices/accounts@2025-04-01-preview' existing = {
  name: last(split(paramOpenAIAccountId, '/'))
}

// RBAC: Grant Function App managed identity Cognitive Services OpenAI User role
resource resOpenAIUserRoleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(paramOpenAIAccountId, resFunctionApp.id, varCognitiveServicesOpenAIUserRoleId)
  scope: resOpenAIAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', varCognitiveServicesOpenAIUserRoleId)
    principalId: resFunctionApp.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Outputs
output outputFunctionAppName string = resFunctionApp.name
output outputFunctionAppId string = resFunctionApp.id
output outputFunctionAppPrincipalId string = resFunctionApp.identity.principalId
output outputStorageAccountName string = resStorageAccount.name
output outputAppInsightsName string = resAppInsights.name
output outputAppInsightsConnectionString string = resAppInsights.properties.ConnectionString
output outputFunctionAppDefaultHostName string = resFunctionApp.properties.defaultHostName
