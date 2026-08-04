#!/bin/sh
# Migrations first, seeding second, server last. Each step is safe to repeat, because a container
# that only works on a fresh volume is a container that fails the first time it is restarted.
set -eu

python -m agentskills_hub_core.schema

case "${HUB_SEED:-off}" in
  off|false|0) ;;
  rotate)
    # Keys are stored hashed, so a restart cannot reprint them. Rotating is the only way to see a
    # usable key again, and it invalidates the previous one.
    python /app/scripts/seed.py --no-migrate --rotate
    ;;
  *)
    python /app/scripts/seed.py --no-migrate
    ;;
esac

exec "$@"
