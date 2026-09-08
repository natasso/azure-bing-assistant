param accountName string
param projectName string
param searchName string
param searchResourceId string

resource foundryAccount 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: accountName
}

resource foundryProject 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' existing = {
  parent: foundryAccount
  name: projectName
}

resource connection 'Microsoft.CognitiveServices/accounts/projects/connections@2026-05-01' = {
  parent: foundryProject
  name: 'document-search'
  properties: {
    category: 'CognitiveSearch'
    target: 'https://${searchName}.search.windows.net'
    authType: 'AAD'
    useWorkspaceManagedIdentity: true
    isSharedToAll: true
    metadata: {
      ApiType: 'Azure'
      ResourceId: searchResourceId
    }
  }
}

output connectionName string = connection.name
