#!/bin/sh
set -eu

: "${SYNAPSE_SERVER_NAME:?SYNAPSE_SERVER_NAME is required}"

signing_key="${SYNAPSE_CONFIG_DIR:-/data}/${SYNAPSE_SERVER_NAME}.signing.key"
if [ ! -f "$signing_key" ]; then
  /start.py generate
fi

python /nexus/render_config.py
exec /start.py

