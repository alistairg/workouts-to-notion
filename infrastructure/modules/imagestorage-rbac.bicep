metadata description = 'RBAC assignments for image storage account'

// Parameters
@description('The resource ID of the image storage account')
param paramImageStorageAccountId string

@description('The principal ID of the Function App for RBAC assignment')
param paramFunctionAppPrincipalId string

@description('The principal ID of the user for RBAC assignment')
param paramUserPrincipalId string

// Variables
var varStorageBlobDataContributorRoleId = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe'

// Reference to existing storage account
resource resImageStorageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: last(split(paramImageStorageAccountId, '/'))
}

// RBAC: Grant Function App Storage Blob Data Contributor role
resource resFunctionAppBlobContributorRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resImageStorageAccount.id, paramFunctionAppPrincipalId, varStorageBlobDataContributorRoleId)
  scope: resImageStorageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', varStorageBlobDataContributorRoleId)
    principalId: paramFunctionAppPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// RBAC: Grant User Storage Blob Data Contributor role
resource resUserBlobContributorRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resImageStorageAccount.id, paramUserPrincipalId, varStorageBlobDataContributorRoleId)
  scope: resImageStorageAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', varStorageBlobDataContributorRoleId)
    principalId: paramUserPrincipalId
    principalType: 'User'
  }
}

// Outputs
output outputRoleAssignmentsComplete bool = true
