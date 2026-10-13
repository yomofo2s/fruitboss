# Deploying to the Hetzner VPS (46.225.83.109)

Stack: Ubuntu 24.04, nginx (HTTPS via Let's Encrypt) -> gunicorn (unix socket) -> Django + SQLite.
Layout on the server: `/srv/fruitboss/{app,venv,data,media,backups}`, secrets in `/etc/fruitboss.env`.

## 1. Point the domain at the VPS
In Hetzner DNS (konsoleH / DNS console) set the `A` records for `fruitbossng.com` and `www` to `46.225.83.109`
(they currently point to 88.198.219.246). Leave the MX record alone so email keeps working.

## 2. Push these files to GitHub (the setup script is downloaded from there)
`git push origin master`. If the repo is private, clone manually and run `bash deploy/setup.sh` instead.

## 3. Create a deploy key (on your Mac)
```bash
ssh-keygen -t ed25519 -N "" -f ~/.ssh/fruitboss_deploy -C github-deploy
```

## 4. Run the setup (as root on the VPS)
```bash
ssh root@46.225.83.109
curl -fsSL https://raw.githubusercontent.com/yomofo2s/fruitboss/master/deploy/setup.sh -o setup.sh
DEPLOY_PUBKEY="$(paste the contents of fruitboss_deploy.pub)" bash setup.sh
```
It installs packages, creates the `fruitboss` user, the service, nginx, a firewall (SSH + web only), cron jobs
(`expire_orders` every 5 min, nightly DB backup) and requests the HTTPS certificate once DNS has propagated
(re-run the script if DNS wasn't ready).

## 5. Configure
```bash
nano /etc/fruitboss.env          # PAYSTACK_SECRET_KEY, SHOP_BANK_DETAILS, EMAIL_*
sudo -u fruitboss bash -c 'set -a; . /etc/fruitboss.env; set +a; cd /srv/fruitboss/app && /srv/fruitboss/venv/bin/python manage.py createsuperuser'
systemctl restart fruitboss
```
Optional: `manage.py seed_shop` for starter products. Product photos uploaded in the admin land in `/srv/fruitboss/media`
(copy your local `media/` with `rsync -av media/ root@46.225.83.109:/srv/fruitboss/media/` then `chown -R fruitboss: /srv/fruitboss/media`).

## 6. Auto-deploy from GitHub
In the repo: Settings > Secrets and variables > Actions, add
`DEPLOY_HOST` = `46.225.83.109` and `DEPLOY_SSH_KEY` = contents of `~/.ssh/fruitboss_deploy` (the private key).
After that, every push to `master` that passes CI deploys automatically.

## 7. Paystack
Set the webhook URL to `https://fruitbossng.com/payments/paystack/webhook/`.

## Useful
```bash
journalctl -u fruitboss -f       # app logs
systemctl status nginx fruitboss
ls /srv/fruitboss/backups        # nightly DB backups
```
