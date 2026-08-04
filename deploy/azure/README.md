# Azure Container Apps

The reference cloud path. Documentation and a Bicep template, deliberately not a dependency: the
Hub runs identically on a laptop, and this directory exists to show that a hosted deployment is
the same image with different environment variables.

## What it creates

| Resource | Why |
| --- | --- |
| Container Apps environment | Runs the image. |
| Log Analytics workspace | Container logs, including the seeder's printed keys and MCP URLs. |
| Storage account + file share | `/data`: the SQLite database and the content store, together. |
| Container app | Ingress on 8000, health probes on `/api/health`, one replica. |

## Deploy

```bash
az group create --name agentskills-hub --location westeurope

az deployment group create \
  --resource-group agentskills-hub \
  --template-file deploy/azure/main.bicep \
  --parameters image=ghcr.io/pratikxpanda/agentskills-hub@sha256:<digest> seed=on
```

The deployment outputs the app URL. The API keys and MCP endpoints are in the container's first
log lines:

```bash
az containerapp logs show --name agentskills-hub --resource-group agentskills-hub --tail 100
```

Set `seed=off` and redeploy once you have them, so that a restart does not attempt to seed again.

## Things that will bite you

**One replica, and that is not a placeholder.** SQLite over SMB tolerates exactly one writer.
`minReplicas` and `maxReplicas` are both bound to the `replicas` parameter for that reason. The
fix is PostgreSQL, which is v0.3 work, not a scale rule here.

**`HUB_ALLOWED_HOSTS` must match the ingress FQDN.** The template derives it from the environment's
default domain. If you add a custom domain, add it to the list too, or MCP requests to the new
name return `421` while `/api/health` stays green.

**The storage account key is read at deploy time** via `listKeys()` and handed to the managed
environment. It never reaches the image, the compose file, or this repository. A managed identity
would be better and is worth doing when Container Apps' file-share support allows it.

**Cost.** A single always-on 0.5 vCPU replica plus a 100 GiB TransactionOptimized share is not
free. `replicas=0` is not an option while the state is on a file share.

## Verification status

The template has not yet been deployed end to end against a live subscription. Until it has, treat
this page as a design, not as a runbook -- v0.1 item 11's last acceptance criterion is explicitly
about closing that gap, and it stays open.
