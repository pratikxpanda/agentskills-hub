# Running the Hub

One image, one process, one volume. The API, the MCP gateway, and the built UI are one deployment
in v0.1 because splitting them would be a scaling decision no v0.1 deployment has earned.

## Locally

```bash
docker compose -f deploy/docker-compose.yml up --build
```

That is the whole setup. On first start the container applies migrations, seeds the teams and
skills in [examples/seed.yaml](../examples/seed.yaml), and prints something like:

```
Teams

  Checkout Squad (checkout-squad)
    MCP endpoint  http://127.0.0.1:8000/mcp/checkout-squad
    API key       ashub_...
```

Open <http://127.0.0.1:8000> for the UI, and point an agent at the printed MCP endpoint with the
printed key as a bearer token. [examples/agent/](../examples/agent) has two that work.

### The keys are printed once

Only a hash of each key is stored, so a restart cannot reprint one. Copy them from the first run.
If you lose them, `HUB_SEED=rotate` mints new ones and invalidates the old.

### Persistence

`/data` holds both the SQLite database and the content store, on one named volume, because they
have to be restored together: a store without its rows is unreachable and rows without their
store are 404s. `docker compose down` keeps the volume; `docker compose down -v` destroys it.

## Configuration

Everything is an environment variable and nothing is a secret in the image.

| Variable | Default in the image | Meaning |
| --- | --- | --- |
| `HUB_DATABASE_URL` | `sqlite+aiosqlite:////data/hub.db` | Where the metadata lives. |
| `HUB_STORE_ROOT` | `/data/store` | Where skill content lives. |
| `HUB_WEB_ROOT` | `/app/web` | The built UI. If it is absent, the API and gateway still serve. |
| `HUB_ALLOWED_HOSTS` | unset | Hosts the MCP gateway will answer for. **Required**, see below. |
| `HUB_ALLOWED_ORIGINS` | unset | Origins the MCP gateway will answer for. |
| `HUB_SEED` | `off` | `on` seeds on start, `rotate` also mints fresh keys, `off` does neither. |
| `HUB_PUBLIC_URL` | `http://127.0.0.1:8000` | Only affects the URLs the seeder prints. |
| `HUB_AUTH_FAILURE_LIMIT` | `10` | Failed authentications before a client is throttled. |
| `HUB_MAX_ARCHIVE_BYTES` | 20 MB | Upload limit; see also `HUB_MAX_TOTAL_BYTES`, `HUB_MAX_FILE_BYTES`. |

### `HUB_ALLOWED_HOSTS` is not optional

The MCP transport refuses any `Host` header it was not told about. That is DNS-rebinding
protection and it is the correct default, but it means the first symptom of a missing
`HUB_ALLOWED_HOSTS` is every MCP request returning `421` while the API is perfectly healthy. Put
every name and port clients will use in the list.

## Hardening

The image runs as uid 10001 with a read-only root filesystem, no capabilities, and
`no-new-privileges`. `/data` is the only writable path apart from a tmpfs at `/tmp`. Base images
are pinned by digest and an SBOM is published with every image CI builds; see the `Container image`
job in [.github/workflows/ci.yml](../.github/workflows/ci.yml).

If you bind-mount a host directory instead of using the named volume, `chown 10001:10001` it
first, or the container will not be able to write.

## Somewhere other than a laptop

[azure/](azure) documents Azure Container Apps as the reference cloud path. It is a template and
a runbook, not a dependency: the Hub runs identically on a laptop, and anything that made that
untrue would be a bug.
