#!/bin/bash
# Run once on a fresh Ubuntu 22.04 EC2 instance.
# Usage: bash setup.sh
set -e

REPO="https://github.com/neraium/neraium.git"   # replace with your actual repo URL
BRANCH="claude/neraium-cnc-manufacturing-v3-ms3jm"
APP_DIR="/home/ubuntu/neraium"

echo "=== System packages ==="
sudo apt-get update -q
sudo apt-get install -y -q python3-pip python3-venv nginx git curl

echo "=== Node.js 20 ==="
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs

echo "=== Clone repo ==="
if [ -d "$APP_DIR" ]; then
  cd "$APP_DIR" && git pull origin "$BRANCH"
else
  git clone --branch "$BRANCH" "$REPO" "$APP_DIR"
fi
cd "$APP_DIR"

echo "=== Python deps ==="
pip3 install --user uvicorn fastapi numpy pandas httpx

echo "=== Build frontend ==="
cd "$APP_DIR/frontend"
npm install --silent
npm run build

echo "=== Install nginx config ==="
sudo cp "$APP_DIR/deploy/nginx.conf" /etc/nginx/sites-available/neraium
sudo ln -sf /etc/nginx/sites-available/neraium /etc/nginx/sites-enabled/neraium
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl restart nginx

echo "=== Install systemd service ==="
sudo cp "$APP_DIR/deploy/neraium.service" /etc/systemd/system/neraium.service
sudo systemctl daemon-reload
sudo systemctl enable neraium
sudo systemctl restart neraium

echo ""
echo "Done. Get your public IP from the AWS console and open it in a browser."
echo "To check logs: sudo journalctl -u neraium -f"
