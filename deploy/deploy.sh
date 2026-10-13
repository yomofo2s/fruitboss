#!/usr/bin/env bash
# Runs on the server as the fruitboss user (GitHub Actions calls this; you can too).
set -euo pipefail
cd /srv/fruitboss/app
git fetch origin master
git reset --hard origin/master
/srv/fruitboss/venv/bin/pip install -q -r requirements.txt
set -a; . /etc/fruitboss.env; set +a
/srv/fruitboss/venv/bin/python manage.py migrate --noinput
/srv/fruitboss/venv/bin/python manage.py collectstatic --noinput
sudo /bin/systemctl restart fruitboss
echo "Deployed $(git rev-parse --short HEAD)"
