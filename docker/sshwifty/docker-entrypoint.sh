#!/bin/sh
set -eu

SSL_DIR=/etc/nginx/ssl
mkdir -p "$SSL_DIR"

if [ ! -f "$SSL_DIR/cert.pem" ]; then
  CN="${SSHWIFTY_TLS_CN:-quicknavigation}"
  SAN="${SSHWIFTY_TLS_SAN:-DNS:localhost,IP:127.0.0.1}"
  echo "[sshwifty-proxy] generating self-signed TLS cert CN=$CN SAN=$SAN"
  openssl req -x509 -nodes -days 825 -newkey rsa:2048 \
    -keyout "$SSL_DIR/key.pem" \
    -out "$SSL_DIR/cert.pem" \
    -subj "/CN=$CN" \
    -addext "subjectAltName=$SAN"
fi

exec nginx -g 'daemon off;'
