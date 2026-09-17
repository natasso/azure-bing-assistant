param accountName string
param projectName string
param connectionName string
param bingAccountName string

resource foundryAccount 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: accountName
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' existing = {
  parent: foundryAccount
  name: projectName
}

resource bingAccount 'Microsoft.Bing/accounts@2020-06-10' existing = {
  name: bingAccountName
}

resource connection 'Microsoft.CognitiveServices/accounts/projects/connections@2026-05-01' = {
  parent: project
  name: connectionName
  properties: {
    category: 'GroundingWithCustomSearch'
    target: 'https://api.bing.microsoft.com/'
    authType: 'ApiKey'
    isSharedToAll: true
    credentials: {
      key: bingAccount.listKeys().key1
    }
    metadata: {
      ApiType: 'Azure'
      ResourceId: bingAccount.id
    }
  }
}

output connectionId string = connection.id
