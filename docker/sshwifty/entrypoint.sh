#!/bin/sh
set -eu

if [ -n "${SSHWIFTY_DOCKER_TLSCERT:-}" ] && [ -n "${SSHWIFTY_DOCKER_TLSCERTKEY:-}" ]; then
  printf '%s' "$SSHWIFTY_DOCKER_TLSCERT" > /tmp/cert
  printf '%s' "$SSHWIFTY_DOCKER_TLSCERTKEY" > /tmp/certkey
  export SSHWIFTY_TLSCERTIFICATEFILE=/tmp/cert
  export SSHWIFTY_TLSCERTIFICATEKEYFILE=/tmp/certkey
fi

exec /sshwifty
