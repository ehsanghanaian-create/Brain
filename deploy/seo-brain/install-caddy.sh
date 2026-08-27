#!/bin/sh
set -eu

CADDY_CONTAINER="gearboxemdad-caddy-1"
CADDYFILE="/opt/gearboxemdad/current/ops/Caddyfile"
SITE_SNIPPET="/opt/seo-brain/app/deploy/seo-brain/Caddyfile.snippet"
PASSWORD_FILE="/opt/seo-brain/.panel-password.txt"
WORK_DIR="/opt/seo-brain/caddy-deploy"
BACKUP_DIR="/opt/gearboxemdad/backups"

install -d -m 700 "$WORK_DIR" "$BACKUP_DIR"

password=$(tr -d '\r\n' < "$PASSWORD_FILE")
hash=$(docker exec "$CADDY_CONTAINER" caddy hash-password --plaintext "$password")
escaped_hash=$(printf '%s' "$hash" | sed 's/[&|]/\\&/g')

sed "s|{\$SEO_BRAIN_BASIC_AUTH_HASH}|$escaped_hash|" "$SITE_SNIPPET" > "$WORK_DIR/site.caddy"

if grep -q '^# BEGIN SEO-BRAIN$' "$CADDYFILE"; then
  awk '/^# BEGIN SEO-BRAIN$/{skip=1; next} /^# END SEO-BRAIN$/{skip=0; next} !skip{print}' "$CADDYFILE" > "$WORK_DIR/Caddyfile.proposed"
else
  cp "$CADDYFILE" "$WORK_DIR/Caddyfile.proposed"
fi

printf '\n' >> "$WORK_DIR/Caddyfile.proposed"
cat "$WORK_DIR/site.caddy" >> "$WORK_DIR/Caddyfile.proposed"

docker cp "$WORK_DIR/Caddyfile.proposed" "$CADDY_CONTAINER:/tmp/Caddyfile.seo-brain"
docker exec "$CADDY_CONTAINER" caddy validate --config /tmp/Caddyfile.seo-brain

stamp=$(date -u +%Y%m%dT%H%M%SZ)
cp "$CADDYFILE" "$BACKUP_DIR/Caddyfile.before-seo-brain.$stamp"
cp "$WORK_DIR/Caddyfile.proposed" "$CADDYFILE"
# The file is bind-mounted into Caddy. Recreate (rather than restart) so Docker
# rebinds the newly replaced inode; the named certificate/config volumes stay.
docker compose \
  --env-file /opt/gearboxemdad/current/.env.production \
  -f /opt/gearboxemdad/current/compose.production.yaml \
  up -d --no-deps --force-recreate caddy >/dev/null

echo "CADDY_SEO_BRAIN_OK"
