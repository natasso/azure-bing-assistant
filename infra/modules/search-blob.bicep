@description('Azure region.')
param location string

@description('Globally unique Storage account name.')
param storageName string

@description('Globally unique Azure AI Search service name.')
param searchName string

@description('Managed identity of the Foundry project.')
param foundryPrincipalId string

@description('Full role definition resource ID for Storage Blob Data Reader.')
param storageBlobDataReaderRoleDefinitionId string

@description('Full role definition resource ID for Search Index Data Reader.')
param searchIndexDataReaderRoleDefinitionId string

var containerName = 'documents'

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageName
  location: location
  kind: 'StorageV2'
  sku: {
    name: 'Standard_LRS'
  }
  properties: {
    allowBlobPublicAccess: false
    allowSharedKeyAccess: false
    defaultToOAuthAuthentication: true
    minimumTlsVersion: 'TLS1_2'
    publicNetworkAccess: 'Enabled'
    supportsHttpsTrafficOnly: true
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
  properties: {
    deleteRetentionPolicy: {
      enabled: true
      days: 7
    }
  }
}

resource container 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: containerName
  properties: {
    publicAccess: 'None'
  }
}

// Semantic configuration uses a pinned preview until the stable API supports it.
resource search 'Microsoft.Search/searchServices@2024-03-01-preview' = {
  name: searchName
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  sku: {
    name: 'basic'
  }
  properties: {
    disableLocalAuth: true
    hostingMode: 'default'
    publicNetworkAccess: 'enabled'
    semanticSearch: 'free'
  }
}

resource searchBlobReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, search.id, storageBlobDataReaderRoleDefinitionId)
  scope: storage
  properties: {
    roleDefinitionId: storageBlobDataReaderRoleDefinitionId
    principalId: search.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

resource foundrySearchReader 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(search.id, foundryPrincipalId, searchIndexDataReaderRoleDefinitionId)
  scope: search
  properties: {
    roleDefinitionId: searchIndexDataReaderRoleDefinitionId
    principalId: foundryPrincipalId
    principalType: 'ServicePrincipal'
  }
}

output storageName string = storage.name
output storageResourceId string = storage.id
output containerName string = container.name
output searchName string = search.name
output searchResourceId string = search.id
