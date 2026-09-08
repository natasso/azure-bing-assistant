targetScope = 'subscription'

@description('Opaque identifier used to reconcile an ambiguous deployment request.')
#disable-next-line no-unused-params
param provisioningOperationId string

@minLength(3)
@maxLength(24)
@description('Lowercase environment identifier used to derive resource names.')
param environmentName string

@description('Existing or new resource group name.')
param resourceGroupName string = 'rg-${environmentName}'

@description('Create the resource group when true; otherwise deploy to an existing group.')
param createResourceGroup bool = true

@description('Azure region for all resources.')
param location string

@allowed([
  'off'
  'searchBlob'
])
@description('Optional knowledge integration.')
param knowledgeMode string = 'off'

@description('Full role definition resource ID for the current Foundry runtime user role.')
param cognitiveUserRoleDefinitionId string

@description('Full role definition resource ID for Storage Blob Data Reader.')
param storageBlobDataReaderRoleDefinitionId string = ''

@description('Full role definition resource ID for Search Index Data Reader.')
param searchIndexDataReaderRoleDefinitionId string = ''

@description('Model name selected from live Azure availability.')
param modelName string

@description('Model version selected from live Azure availability.')
param modelVersion string

@description('Model format selected from live Azure availability.')
param modelFormat string

@description('Deployment SKU selected from live Azure availability.')
param modelSku string

@minValue(1)
@description('Model deployment capacity.')
param modelCapacity int = 10

@description('Model deployment name.')
param modelDeploymentName string

@description('Lowercase chatbot display identifier.')
param chatbotName string

@allowed([
  'it'
  'en'
])
@description('Language for all application-controlled interface strings.')
param uiLanguage string = 'it'

@maxLength(80)
@description('Optional literal product-name override. Empty uses the selected language default.')
param uiProductName string = ''

@maxLength(80)
@description('Optional literal organization-name override. Empty uses the selected language default.')
param uiOrganizationName string = ''

@maxLength(80)
@description('Optional literal assistant-name override. Empty uses the selected language default.')
param uiAssistantName string = ''

@maxLength(120)
@description('Optional literal welcome-title override. Empty uses the selected language default.')
param uiWelcomeTitle string = ''

@maxLength(240)
@description('Optional literal welcome-subtitle override. Empty uses the selected language default.')
param uiWelcomeSubtitle string = ''

@maxLength(320)
@description('Optional literal AI-disclaimer override. Empty uses the selected language default.')
param uiDisclaimer string = ''

@description('Optional JSON array containing at most five validated suggested questions. Empty uses language defaults; [] is an explicit empty list.')
param uiSuggestedQuestions string = ''

@description('Acknowledgement of Bing terms and cross-boundary data flow.')
@allowed([
  true
])
param bingTermsAccepted bool

@description('Advisory preferred public sites; standard Bing grounding does not enforce them.')
param webGroundingSites string

var token = uniqueString(subscription().id, environmentName)
var foundryName = 'ai-${environmentName}-${token}'
var webAppName = 'app-${environmentName}-${token}'
var storageName = take(replace('st${environmentName}${token}', '-', ''), 24)
var searchName = 'srch-${environmentName}-${token}'

resource resourceGroupResource 'Microsoft.Resources/resourceGroups@2024-03-01' = if (createResourceGroup) {
  name: resourceGroupName
  location: location
  tags: {
    application: 'azure-bing-assistant'
    environment: environmentName
  }
}

module webapp 'modules/webapp.bicep' = {
  name: 'webapp'
  scope: resourceGroup(resourceGroupName)
  params: {
    location: location
    appName: webAppName
    environmentName: environmentName
    foundryName: foundryName
    knowledgeMode: knowledgeMode
    chatbotName: chatbotName
    uiLanguage: uiLanguage
    uiProductName: uiProductName
    uiOrganizationName: uiOrganizationName
    uiAssistantName: uiAssistantName
    uiWelcomeTitle: uiWelcomeTitle
    uiWelcomeSubtitle: uiWelcomeSubtitle
    uiDisclaimer: uiDisclaimer
    uiSuggestedQuestions: uiSuggestedQuestions
    modelDeploymentName: modelDeploymentName
    webGroundingSites: webGroundingSites
  }
  dependsOn: [
    resourceGroupResource
  ]
}

module foundry 'modules/foundry.bicep' = {
  name: 'foundry'
  scope: resourceGroup(resourceGroupName)
  params: {
    location: location
    accountName: foundryName
    webPrincipalId: webapp.outputs.principalId
    cognitiveUserRoleDefinitionId: cognitiveUserRoleDefinitionId
    modelName: modelName
    modelVersion: modelVersion
    modelFormat: modelFormat
    modelSku: modelSku
    modelCapacity: modelCapacity
    modelDeploymentName: modelDeploymentName
  }
}

module bing 'modules/bing.bicep' = {
  name: 'bing-grounding'
  scope: resourceGroup(resourceGroupName)
  params: {
    accountName: foundry.outputs.accountName
    projectName: foundry.outputs.projectName
    bingName: 'bing-${environmentName}-${token}'
    termsAccepted: bingTermsAccepted
  }
}

module searchConnection 'modules/search-connection.bicep' = if (knowledgeMode == 'searchBlob') {
  name: 'search-connection'
  scope: resourceGroup(resourceGroupName)
  params: {
    accountName: foundry.outputs.accountName
    projectName: foundry.outputs.projectName
    searchName: searchBlob!.outputs.searchName
    searchResourceId: searchBlob!.outputs.searchResourceId
  }
}

module searchBlob 'modules/search-blob.bicep' = if (knowledgeMode == 'searchBlob') {
  name: 'search-blob'
  scope: resourceGroup(resourceGroupName)
  params: {
    location: location
    storageName: storageName
    searchName: searchName
    foundryPrincipalId: foundry.outputs.principalId
    storageBlobDataReaderRoleDefinitionId: storageBlobDataReaderRoleDefinitionId
    searchIndexDataReaderRoleDefinitionId: searchIndexDataReaderRoleDefinitionId
  }
}

output resourceGroupName string = resourceGroupName
output webAppName string = webapp.outputs.appName
output foundryAccountName string = foundry.outputs.accountName
output searchServiceName string = knowledgeMode == 'searchBlob' ? searchBlob!.outputs.searchName : ''
output storageAccountName string = knowledgeMode == 'searchBlob' ? searchBlob!.outputs.storageName : ''
output storageContainerName string = knowledgeMode == 'searchBlob' ? searchBlob!.outputs.containerName : ''
output AZURE_RESOURCE_GROUP string = resourceGroupName
output SERVICE_WEB_NAME string = webapp.outputs.appName
output FOUNDRY_PROJECT_ENDPOINT string = 'https://${foundry.outputs.accountName}.services.ai.azure.com/api/projects/${foundry.outputs.projectName}'
output BING_CONNECTION_NAME string = bing.outputs.connectionName
output SEARCH_ENDPOINT string = knowledgeMode == 'searchBlob' ? 'https://${searchBlob!.outputs.searchName}.search.windows.net' : ''
output SEARCH_INDEX_NAME string = knowledgeMode == 'searchBlob' ? 'documents' : ''
output SEARCH_INDEXER_NAME string = knowledgeMode == 'searchBlob' ? 'documents-indexer' : ''
output SEARCH_DATA_SOURCE_NAME string = knowledgeMode == 'searchBlob' ? 'documents-source' : ''
output SEARCH_CONNECTION_NAME string = knowledgeMode == 'searchBlob' ? searchConnection!.outputs.connectionName : ''
output STORAGE_RESOURCE_ID string = knowledgeMode == 'searchBlob' ? searchBlob!.outputs.storageResourceId : ''
output STORAGE_ACCOUNT_NAME string = knowledgeMode == 'searchBlob' ? searchBlob!.outputs.storageName : ''
output STORAGE_CONTAINER_NAME string = knowledgeMode == 'searchBlob' ? searchBlob!.outputs.containerName : ''
