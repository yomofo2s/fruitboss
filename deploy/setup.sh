#!/usr/bin/env bash
# One-time server setup. On a fresh Ubuntu 24.04 VPS, as root:
#   curl -fsSL https://raw.githubusercontent.com/yomofo2s/fruitboss/master/deploy/setup.sh -o setup.sh
#   DEPLOY_PUBKEY="ssh-ed25519 AAAA... github-deploy" bash setup.sh
# Safe to re-run.
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/yomofo2s/fruitboss.git}"
DOMAIN="${DOMAIN:-fruitbossng.com}"
CERT_EMAIL="${CERT_EMAIL:-info@fruitbossng.com}"
SERVER_IP="${SERVER_IP:-46.225.83.109}"
APP=/srv/fruitboss

export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q python3-venv python3-dev build-essential libjpeg-dev zlib1g-dev \
    nginx certbot python3-certbot-nginx git sqlite3 ufw unattended-upgrades dnsutils

id fruitboss &>/dev/null || adduser --system --group --shell /bin/bash --home "$APP" fruitboss
mkdir -p "$APP"/{data,media,backups}
chown -R fruitboss:fruitboss "$APP"
chmod 755 "$APP" "$APP/media"

if [ -n "${DEPLOY_PUBKEY:-}" ]; then
    install -d -m 700 -o fruitboss -g fruitboss "$APP/.ssh"
    grep -qF "$DEPLOY_PUBKEY" "$APP/.ssh/authorized_keys" 2>/dev/null || echo "$DEPLOY_PUBKEY" >> "$APP/.ssh/authorized_keys"
    chown fruitboss:fruitboss "$APP/.ssh/authorized_keys"; chmod 600 "$APP/.ssh/authorized_keys"
fi
echo 'fruitboss ALL=(root) NOPASSWD: /bin/systemctl restart fruitboss' > /etc/sudoers.d/fruitboss
chmod 440 /etc/sudoers.d/fruitboss

[ -d "$APP/app/.git" ] || sudo -u fruitboss git clone "$REPO_URL" "$APP/app"
[ -d "$APP/venv" ] || sudo -u fruitboss python3 -m venv "$APP/venv"

if [ ! -f /etc/fruitboss.env ]; then
    sed -e "s|generated-by-setup|$(python3 -c 'import secrets; print(secrets.token_urlsafe(50))')|" \
        "$APP/app/deploy/env.production.example" > /etc/fruitboss.env
    chown root:fruitboss /etc/fruitboss.env; chmod 640 /etc/fruitboss.env
fi

install -m 644 "$APP/app/deploy/fruitboss.service" /etc/systemd/system/fruitboss.service
install -m 644 "$APP/app/deploy/nginx.conf" /etc/nginx/sites-available/fruitboss
ln -sf /etc/nginx/sites-available/fruitboss /etc/nginx/sites-enabled/fruitboss
rm -f /etc/nginx/sites-enabled/default

cat > /etc/cron.d/fruitboss <<'CRON'
# Cancel unpaid online orders and restore stock
*/5 * * * * fruitboss set -a; . /etc/fruitboss.env; set +a; cd /srv/fruitboss/app && /srv/fruitboss/venv/bin/python manage.py expire_orders >/dev/null 2>&1
# Nightly SQLite backup, keep 14 days
0 3 * * * fruitboss sqlite3 /srv/fruitboss/data/db.sqlite3 ".backup /srv/fruitboss/backups/db-$(date +\%F).sqlite3" && find /srv/fruitboss/backups -name 'db-*.sqlite3' -mtime +14 -delete
CRON

ufw allow OpenSSH; ufw allow 'Nginx Full'; ufw --force enable

systemctl daemon-reload
systemctl enable fruitboss
sudo -u fruitboss bash "$APP/app/deploy/deploy.sh"
nginx -t && systemctl reload nginx

if [ "$(dig +short "$DOMAIN" A | head -1)" = "$SERVER_IP" ]; then
    certbot --nginx --non-interactive --agree-tos -m "$CERT_EMAIL" --redirect -d "$DOMAIN" -d "www.$DOMAIN"
else
    echo "DNS for $DOMAIN does not point to $SERVER_IP yet. Fix the A records, then re-run this script to get HTTPS."
fi
echo "Done. Edit /etc/fruitboss.env (Paystack, email, bank details), create the admin user, then: systemctl restart fruitboss"
