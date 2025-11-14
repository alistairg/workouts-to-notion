metadata description = 'Deploys Azure Key Vault with secrets for workouts-to-notion'

// Parameters
@description('The location for the Key Vault')
param paramLocation string

@description('Tags to apply to resources')
param paramTags object

@description('The name of the Key Vault')
param paramKeyVaultName string

@description('The principal ID of the Function App for Key Vault Secrets User role')
param paramFunctionAppPrincipalId string

@description('The principal ID of the user for Key Vault Administrator role')
param paramUserPrincipalId string

// Variables
var varKeyVaultSecretsUserRoleId = '4633458b-17de-408a-b874-0445c86b69e6'
var varKeyVaultAdministratorRoleId = '00482a5a-887f-4fb3-b363-3b7fe8e74483'

// Key Vault
resource resKeyVault 'Microsoft.KeyVault/vaults@2023-07-01' = {
  name: paramKeyVaultName
  location: paramLocation
  tags: paramTags
  properties: {
    sku: {
      family: 'A'
      name: 'standard'
    }
    tenantId: subscription().tenantId
    enableRbacAuthorization: true // Use RBAC instead of access policies
    enableSoftDelete: true
    softDeleteRetentionInDays: 90
    enablePurgeProtection: true
    publicNetworkAccess: 'Enabled'
    networkAcls: {
      defaultAction: 'Allow'
      bypass: 'AzureServices'
    }
  }
}

// Deploy secrets with conditional creation using @batchSize(1)
@batchSize(1)
@onlyIfNotExists()
resource resSecrets 'Microsoft.KeyVault/vaults/secrets@2023-07-01' = [for secret in [
  {
    name: 'NOTION-API-KEY'
    value: 'placeholder-update-this-value'
  }
  {
    name: 'NOTION-DATABASE-ID'
    value: 'placeholder-update-this-value'
  }
  {
    name: 'HEVY-API-KEY'
    value: 'placeholder-update-this-value'
  }
  {
    name: 'NOTION-WORKOUTS-DATABASE-ID'
    value: 'placeholder-update-this-value'
  }
  {
    name: 'NOTION-EXERCISES-DATABASE-ID'
    value: 'placeholder-update-this-value'
  }
  {
    name: 'NOTION-EXERCISE-PERFORMANCES-DATABASE-ID'
    value: 'placeholder-update-this-value'
  }
]: {
  name: secret.name
  parent: resKeyVault
  properties: {
    value: secret.value
  }
}]

// RBAC: Grant Function App managed identity Key Vault Secrets User role
resource resKeyVaultSecretsUserRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resKeyVault.id, paramFunctionAppPrincipalId, varKeyVaultSecretsUserRoleId)
  scope: resKeyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', varKeyVaultSecretsUserRoleId)
    principalId: paramFunctionAppPrincipalId
    principalType: 'ServicePrincipal'
  }
}

// RBAC: Grant user Key Vault Administrator role
resource resKeyVaultAdministratorRole 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(resKeyVault.id, paramUserPrincipalId, varKeyVaultAdministratorRoleId)
  scope: resKeyVault
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', varKeyVaultAdministratorRoleId)
    principalId: paramUserPrincipalId
    principalType: 'User'
  }
}

// Outputs
output outputKeyVaultName string = resKeyVault.name
output outputKeyVaultId string = resKeyVault.id
output outputKeyVaultUri string = resKeyVault.properties.vaultUri
output outputNotionApiKeySecretUri string = resSecrets[0].properties.secretUri
output outputNotionDatabaseIdSecretUri string = resSecrets[1].properties.secretUri
output outputHevyApiKeySecretUri string = resSecrets[2].properties.secretUri
output outputNotionWorkoutsDatabaseIdSecretUri string = resSecrets[3].properties.secretUri
output outputNotionExercisesDatabaseIdSecretUri string = resSecrets[4].properties.secretUri
output outputNotionExercisePerformancesDatabaseIdSecretUri string = resSecrets[5].properties.secretUri
