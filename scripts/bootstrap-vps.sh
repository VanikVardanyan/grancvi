#!/usr/bin/env bash
# Идемпотентный bootstrap для свежей Ubuntu 24.04 VM.
# Запускать под root на VPS один раз.
set -euo pipefail

REPO_URL="https://github.com/VanikVardanyan/grancvi.git"
APP_DIR="/opt/tg-bot"
DEPLOY_USER="deploy"

echo "==> Step 1/6: apt update + essentials"
apt-get update
apt-get upgrade -y
apt-get install -y ca-certificates curl gnupg git ufw

echo "==> Step 2/6: Docker Engine + compose plugin"
if ! command -v docker >/dev/null 2>&1; then
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
    chmod a+r /etc/apt/keyrings/docker.asc
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "${VERSION_CODENAME}") stable" \
        > /etc/apt/sources.list.d/docker.list
    apt-get update
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
else
    echo "  docker already installed — skipping"
fi

echo "==> Step 3/6: deploy user + docker group + SSH keys"
if ! id -u "${DEPLOY_USER}" >/dev/null 2>&1; then
    useradd -m -s /bin/bash "${DEPLOY_USER}"
fi
usermod -aG docker "${DEPLOY_USER}"
mkdir -p "/home/${DEPLOY_USER}/.ssh"
if [ -f /root/.ssh/authorized_keys ]; then
    cp /root/.ssh/authorized_keys "/home/${DEPLOY_USER}/.ssh/authorized_keys"
fi
chown -R "${DEPLOY_USER}:${DEPLOY_USER}" "/home/${DEPLOY_USER}/.ssh"
chmod 700 "/home/${DEPLOY_USER}/.ssh"
chmod 600 "/home/${DEPLOY_USER}/.ssh/authorized_keys" || true

echo "==> Step 4/6: UFW — only SSH"
ufw allow 22/tcp
ufw default deny incoming
ufw default allow outgoing
ufw --force enable

echo "==> Step 5/6: sshd hardening"
sed -i 's/^#\?PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config
sed -i 's/^#\?PermitRootLogin.*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config
systemctl restart ssh

echo "==> Step 6/6: clone repo under ${DEPLOY_USER}"
mkdir -p "${APP_DIR}"
chown "${DEPLOY_USER}:${DEPLOY_USER}" "${APP_DIR}"
if [ ! -d "${APP_DIR}/.git" ]; then
    sudo -u "${DEPLOY_USER}" git clone "${REPO_URL}" "${APP_DIR}"
else
    echo "  repo already cloned — skipping"
fi

echo ""
echo "==============================================="
echo " Bootstrap complete."
echo ""
echo " Next steps:"
echo "   1. Create /opt/tg-bot/.env from template:"
echo "      sudo -u ${DEPLOY_USER} cp ${APP_DIR}/.env.prod.example ${APP_DIR}/.env"
echo ""
echo "   2. Edit /opt/tg-bot/.env, fill BOT_TOKEN, SENTRY_DSN, etc."
echo "      Generate POSTGRES_PASSWORD:"
echo "        openssl rand -base64 24"
echo "      Then update both POSTGRES_PASSWORD and DATABASE_URL in .env."
echo ""
echo "   3. First build & start:"
echo "      cd ${APP_DIR}"
echo "      sudo -u ${DEPLOY_USER} docker compose \\"
echo "        -f docker-compose.yml -f docker-compose.prod.yml up -d --build"
echo ""
echo "   4. Generate deploy-only SSH key locally on your Mac:"
echo "      ssh-keygen -t ed25519 -f ~/.ssh/grancvi-deploy -N '' -C 'grancvi-deploy'"
echo "   5. Append the pub key to /home/${DEPLOY_USER}/.ssh/authorized_keys on this VPS."
echo "   6. Add to GitHub Secrets (repo Settings → Secrets and variables → Actions):"
echo "        SSH_HOST        = this VPS's IPv4"
echo "        SSH_USER        = ${DEPLOY_USER}"
echo "        SSH_PRIVATE_KEY = contents of ~/.ssh/grancvi-deploy (private key)"
echo "==============================================="
