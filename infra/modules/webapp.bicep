@description('Azure region.')
param location string

@description('Globally unique App Service name.')
param appName string

param environmentName string

@description('AI Services account name.')
param foundryName string

@allowed([
  'off'
  'searchBlob'
])
param knowledgeMode string

param chatbotName string
param modelDeploymentName string
param webGroundingSites string
@allowed([
  'it'
  'en'
])
param uiLanguage string
param uiProductName string
param uiOrganizationName string
param uiAssistantName string
param uiWelcomeTitle string
param uiWelcomeSubtitle string
param uiDisclaimer string
param uiSuggestedQuestions string

var uiSettings = concat(
  [
    {
      name: 'UI_LANGUAGE'
      value: uiLanguage
    }
  ],
  empty(uiProductName) ? [] : [
    {
      name: 'UI_PRODUCT_NAME'
      value: uiProductName
    }
  ],
  empty(uiOrganizationName) ? [] : [
    {
      name: 'UI_ORGANIZATION_NAME'
      value: uiOrganizationName
    }
  ],
  empty(uiAssistantName) ? [] : [
    {
      name: 'UI_ASSISTANT_NAME'
      value: uiAssistantName
    }
  ],
  empty(uiWelcomeTitle) ? [] : [
    {
      name: 'UI_WELCOME_TITLE'
      value: uiWelcomeTitle
    }
  ],
  empty(uiWelcomeSubtitle) ? [] : [
    {
      name: 'UI_WELCOME_SUBTITLE'
      value: uiWelcomeSubtitle
    }
  ],
  empty(uiDisclaimer) ? [] : [
    {
      name: 'UI_DISCLAIMER'
      value: uiDisclaimer
    }
  ],
  empty(uiSuggestedQuestions) ? [] : [
    {
      name: 'UI_SUGGESTED_QUESTIONS'
      value: uiSuggestedQuestions
    }
  ]
)

resource plan 'Microsoft.Web/serverfarms@2024-04-01' = {
  name: 'plan-${appName}'
  location: location
  sku: {
    name: 'B1'
    tier: 'Basic'
  }
  kind: 'linux'
  properties: {
    reserved: true
  }
}

resource site 'Microsoft.Web/sites@2024-04-01' = {
  name: appName
  location: location
  kind: 'app,linux'
  identity: {
    type: 'SystemAssigned'
  }
  tags: {
    'azd-env-name': environmentName
    'azd-service-name': 'web'
  }
  properties: {
    serverFarmId: plan.id
    httpsOnly: true
    siteConfig: {
      alwaysOn: true
      ftpsState: 'Disabled'
      http20Enabled: true
      linuxFxVersion: 'PYTHON|3.11'
      appCommandLine: 'python -m uvicorn app.backend.main:app --host 0.0.0.0 --port 8000'
      minTlsVersion: '1.2'
      appSettings: concat([
        {
          name: 'APP_ENV'
          value: 'production'
        }
        {
          name: 'KNOWLEDGE_MODE'
          value: knowledgeMode
        }
        {
          name: 'FOUNDRY_ACCOUNT_NAME'
          value: foundryName
        }
        {
          name: 'FOUNDRY_PROJECT_ENDPOINT'
          value: 'https://${foundryName}.services.ai.azure.com/api/projects/project'
        }
        {
          name: 'CHATBOT_NAME'
          value: chatbotName
        }
        {
          name: 'MODEL_DEPLOYMENT_NAME'
          value: modelDeploymentName
        }
        {
          name: 'WEB_GROUNDING_SITES'
          value: webGroundingSites
        }
      ], uiSettings, [
        {
          name: 'AGENT_TIMEOUT_SECONDS'
          value: '90'
        }
        {
          name: 'SCM_DO_BUILD_DURING_DEPLOYMENT'
          value: 'true'
        }
      ])
    }
  }
}

output appName string = site.name
output principalId string = site.identity.principalId
