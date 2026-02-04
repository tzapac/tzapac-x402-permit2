#!/bin/sh
set -e

CONFIG_PATH="${X402_CONFIG:-/app/bbt_config.json}"
READABLE_PATH="/app/bbt_config.readable.json"

case "$CONFIG_PATH" in
  /app/*) ;;
  *)
    echo "X402_CONFIG must be under /app" >&2
    exit 1
    ;;
esac

if [ ! -f "$CONFIG_PATH" ]; then
  echo "Config file not found at $CONFIG_PATH" >&2
  exit 1
fi

if ! runuser -u facilitator -- test -r "$CONFIG_PATH"; then
  cp "$CONFIG_PATH" "$READABLE_PATH"
  chown facilitator:facilitator "$READABLE_PATH"
  chmod 400 "$READABLE_PATH"
  CONFIG_PATH="$READABLE_PATH"
fi

if [ "$#" -eq 0 ]; then
  set -- x402-facilitator --config "$CONFIG_PATH"
else
  if [ "$1" = "x402-facilitator" ]; then
    shift
    if ! printf "%s\n" "$@" | grep -q -- "--config"; then
      set -- x402-facilitator --config "$CONFIG_PATH" "$@"
    else
      set -- x402-facilitator "$@"
    fi
  fi
fi

exec runuser -u facilitator -- "$@"
