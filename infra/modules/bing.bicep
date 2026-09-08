@description('Existing Foundry account name.')
param accountName string

@description('Existing Foundry project name.')
param projectName string

@description('Globally unique Grounding with Bing Search resource name.')
param bingName string

@description('Must be true because resource creation accepts the Grounding with Bing terms.')
param termsAccepted bool

resource foundryAccount 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: accountName
}

resource foundryProject 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' existing = {
  parent: foundryAccount
  name: projectName
}

resource bing 'Microsoft.Bing/accounts@2020-06-10' = if (termsAccepted) {
  name: bingName
  location: 'global'
  kind: 'Bing.Grounding'
  sku: {
    name: 'G1'
  }
}

// The key is resolved only inside ARM and stored in the managed Foundry connection.
// It is never an output, parameter, application setting, or CLI value.
resource connection 'Microsoft.CognitiveServices/accounts/projects/connections@2026-05-01' = if (termsAccepted) {
  parent: foundryProject
  name: 'bing-grounding'
  properties: {
    category: 'GroundingWithBingSearch'
    // Official managed-connection metadata; the application uses only this connection ID.
    target: 'https://api.bing.microsoft.com/'
    authType: 'ApiKey'
    credentials: {
      key: listKeys(bing!.id, '2020-06-10').key1
    }
    isSharedToAll: true
    metadata: {
      ApiType: 'Azure'
      Location: 'global'
      ResourceId: bing!.id
    }
  }
}

output connectionName string = termsAccepted ? connection!.name : ''
