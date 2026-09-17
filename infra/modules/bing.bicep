param accountName string
param configurationName string
param environmentName string

@minLength(1)
@maxLength(100)
@description('Normalized authorized hostnames. Public HTTPS root URLs are configured with subpages.')
param allowedDomains array

resource account 'Microsoft.Bing/accounts@2020-06-10' = {
  name: accountName
  location: 'global'
  kind: 'Bing.GroundingCustomSearch'
  sku: {
    name: 'G2'
  }
  tags: {
    application: 'azure-bing-assistant'
    environment: environmentName
  }
  properties: {}
}

resource configuration 'Microsoft.Bing/accounts/customSearchConfigurations@2025-05-01-preview' = {
  parent: account
  name: configurationName
  properties: {
    allowedDomains: [for domain in allowedDomains: {
      domain: 'https://${domain}'
      includeSubPages: true
      boostLevel: 'Default'
    }]
    blockedDomains: []
    pinnedDomains: []
  }
}

output accountName string = account.name
output resourceId string = account.id
output configurationName string = configuration.name
