@description('Azure region.')
param location string

@description('Globally unique AI Services account name.')
param accountName string

@description('Managed identity of the web application.')
param webPrincipalId string

@description('Full role definition resource ID for the current Foundry runtime user role.')
param cognitiveUserRoleDefinitionId string

param modelName string
param modelVersion string
param modelFormat string
param modelSku string
param modelCapacity int
param modelDeploymentName string

resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: accountName
  location: location
  kind: 'AIServices'
  identity: {
    type: 'SystemAssigned'
  }
  sku: {
    name: 'S0'
  }
  properties: {
    allowProjectManagement: true
    customSubDomainName: accountName
    disableLocalAuth: true
    publicNetworkAccess: 'Enabled'
  }
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = {
  parent: account
  name: 'project'
  location: location
  identity: {
    type: 'SystemAssigned'
  }
  properties: {
    displayName: 'Chatbot project'
    description: 'Managed project for the chatbot application'
  }
}

resource modelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: account
  name: modelDeploymentName
  sku: {
    name: modelSku
    capacity: modelCapacity
  }
  properties: {
    model: {
      format: modelFormat
      name: modelName
      version: modelVersion
    }
  }
}

resource webFoundryUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(account.id, webPrincipalId, cognitiveUserRoleDefinitionId)
  scope: account
  properties: {
    roleDefinitionId: cognitiveUserRoleDefinitionId
    principalId: webPrincipalId
    principalType: 'ServicePrincipal'
  }
}

output accountName string = account.name
output projectName string = project.name
output principalId string = project.identity.principalId
