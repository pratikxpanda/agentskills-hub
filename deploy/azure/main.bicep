// The Hub on Azure Container Apps: one container, one Azure Files share for /data.
//
// This is the reference cloud path, not a supported product surface. Everything it configures is
// an environment variable the Hub already reads, so nothing here can drift into being required.

@description('Name prefix for every resource created here.')
@minLength(3)
@maxLength(20)
param name string = 'agentskills-hub'

@description('Location for all resources.')
param location string = resourceGroup().location

@description('Fully qualified image reference, digest-pinned in anything but a demo.')
param image string = 'ghcr.io/pratikxpanda/agentskills-hub:latest'

@description('Seed the Hub on first start: on, rotate, or off.')
@allowed(['on', 'rotate', 'off'])
param seed string = 'off'

@description('Minimum replicas. The Hub is stateful on a file share, so this is also the maximum.')
param replicas int = 1

var storageAccountName = toLower(replace('${name}${uniqueString(resourceGroup().id)}', '-', ''))
var shareName = 'hub-data'
var storageLinkName = 'hub-data'

resource logs 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: '${name}-logs'
  location: location
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: take(storageAccountName, 24)
  location: location
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    minimumTlsVersion: 'TLS1_2'
    allowBlobPublicAccess: false
    supportsHttpsTrafficOnly: true
  }
}

resource fileService 'Microsoft.Storage/storageAccounts/fileServices@2023-05-01' = {
  parent: storage
  name: 'default'
}

// SQLite over SMB is the known weak point of this deployment: it works for a single replica and
// nothing else. Postgres, in v0.3, is what removes the constraint rather than papering over it.
resource share 'Microsoft.Storage/storageAccounts/fileServices/shares@2023-05-01' = {
  parent: fileService
  name: shareName
  properties: {
    accessTier: 'TransactionOptimized'
    shareQuota: 100
  }
}

resource environment 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: '${name}-env'
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logs.properties.customerId
        sharedKey: logs.listKeys().primarySharedKey
      }
    }
  }
}

resource storageLink 'Microsoft.App/managedEnvironments/storages@2024-03-01' = {
  parent: environment
  name: storageLinkName
  properties: {
    azureFile: {
      accountName: storage.name
      accountKey: storage.listKeys().keys[0].value
      shareName: shareName
      accessMode: 'ReadWrite'
    }
  }
}

resource app 'Microsoft.App/containerApps@2024-03-01' = {
  name: name
  location: location
  properties: {
    managedEnvironmentId: environment.id
    configuration: {
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
        allowInsecure: false
      }
    }
    template: {
      containers: [
        {
          name: 'hub'
          image: image
          resources: {
            cpu: json('0.5')
            memory: '1Gi'
          }
          env: [
            { name: 'HUB_DATABASE_URL', value: 'sqlite+aiosqlite:////data/hub.db' }
            { name: 'HUB_STORE_ROOT', value: '/data/store' }
            { name: 'HUB_WEB_ROOT', value: '/app/web' }
            { name: 'HUB_SEED', value: seed }
            // The gateway refuses any Host it was not told about; without this every MCP request
            // is a 421 while the API looks perfectly healthy.
            { name: 'HUB_ALLOWED_HOSTS', value: '${name}.${environment.properties.defaultDomain}' }
            { name: 'HUB_PUBLIC_URL', value: 'https://${name}.${environment.properties.defaultDomain}' }
          ]
          volumeMounts: [
            { volumeName: 'hub-data', mountPath: '/data' }
          ]
          probes: [
            {
              type: 'Liveness'
              httpGet: { path: '/api/health', port: 8000 }
              initialDelaySeconds: 20
              periodSeconds: 10
            }
            {
              type: 'Readiness'
              httpGet: { path: '/api/health', port: 8000 }
              initialDelaySeconds: 5
              periodSeconds: 10
            }
          ]
        }
      ]
      volumes: [
        {
          name: 'hub-data'
          storageType: 'AzureFile'
          storageName: storageLink.name
        }
      ]
      scale: {
        minReplicas: replicas
        maxReplicas: replicas
      }
    }
  }
}

output url string = 'https://${app.properties.configuration.ingress.fqdn}'
output shareUrl string = 'https://${storage.name}.file.core.windows.net/${shareName}'
