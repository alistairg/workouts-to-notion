

param secretValue string = 'myGreatSecret!'

resource resKeyVault 'Microsoft.KeyVault/vaults@2025-05-01' = {
  name: 'kvtest01'
  location: 'westeurope'
  properties: {
    sku: {
      name: 'standard'
      family: 'A'
    }
    tenantId: tenant().tenantId
    enableSoftDelete: false
    enablePurgeProtection: false
  }
}

resource resSecret 'Microsoft.KeyVault/vaults/secrets@2025-05-01' = {
  name: 'my-secret'
  parent: resKeyVault
  properties: {
    value: secretValue
  }
}

resource resStorageAccount 'Microsoft.Storage/storageAccounts@2025-01-01' = {
  name: 'myteststorage'
  location: 'westeurope'
  sku: {
    name: 'Standard_LRS'
  }
  kind: 'StorageV2'
  properties: {
    publicNetworkAccess: 'Enabled'
    supportsHttpsTrafficOnly: false
  }
}
