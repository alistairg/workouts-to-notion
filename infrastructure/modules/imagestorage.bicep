metadata description = 'Deploys storage account for uploaded workout images with lifecycle management'

// Parameters
@description('The location for the storage resources')
param paramLocation string

@description('Tags to apply to resources')
param paramTags object

@description('The name of the storage account for images')
param paramImageStorageAccountName string

// Variables
var varContainerName = 'uploaded-images'

// Storage Account for uploaded images
resource resImageStorageAccount 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: paramImageStorageAccountName
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
    accessTier: 'Hot'
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
}

// Blob Service
resource resBlobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: resImageStorageAccount
  name: 'default'
  properties: {
    deleteRetentionPolicy: {
      enabled: true
      days: 7
    }
  }
}

// Blob Container for uploaded images
resource resBlobContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: resBlobService
  name: varContainerName
  properties: {
    publicAccess: 'None'
  }
}

// Lifecycle Management Policy - Delete blobs after 90 days
resource resLifecyclePolicy 'Microsoft.Storage/storageAccounts/managementPolicies@2023-05-01' = {
  parent: resImageStorageAccount
  name: 'default'
  properties: {
    policy: {
      rules: [
        {
          enabled: true
          name: 'delete-old-images'
          type: 'Lifecycle'
          definition: {
            filters: {
              blobTypes: [
                'blockBlob'
              ]
              prefixMatch: [
                '${varContainerName}/'
              ]
            }
            actions: {
              baseBlob: {
                delete: {
                  daysAfterModificationGreaterThan: 90
                }
              }
            }
          }
        }
      ]
    }
  }
}

// Outputs
output outputStorageAccountName string = resImageStorageAccount.name
output outputStorageAccountId string = resImageStorageAccount.id
output outputBlobEndpoint string = resImageStorageAccount.properties.primaryEndpoints.blob
output outputContainerName string = varContainerName
