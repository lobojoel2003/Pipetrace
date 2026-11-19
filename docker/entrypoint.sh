#!/bin/sh
# Pipetrace container entrypoint: prepare the database, then run the given command.
set -e

if [ "${PIPETRACE_AUTO_MIGRATE:-1}" = "1" ]; then
  pipetrace migrate --noinput
  pipetrace ensure_admin
  if [ "${PIPETRACE_LOAD_DEMO:-0}" = "1" ]; then
    pipetrace load_demo --if-empty
  fi
fi

exec "$@"
