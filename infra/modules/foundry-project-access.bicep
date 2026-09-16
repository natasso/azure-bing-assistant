param accountName string
param projectPrincipalId string
param roleDefinitionId string

resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' existing = {
  name: accountName
}

resource projectFoundryUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(account.id, projectPrincipalId, roleDefinitionId)
  scope: account
  properties: {
    roleDefinitionId: roleDefinitionId
    principalId: projectPrincipalId
    principalType: 'ServicePrincipal'
  }
}
