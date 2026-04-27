#!/usr/bin/env bash
# First-time setup for Ollama + Open WebUI on Ubuntu/Debian.
# Run as a normal user (sudo rights required for installs).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

step()  { echo -e "\n\033[0;36m==> $*\033[0m"; }
ok()    { echo -e "    \033[0;32mOK: $*\033[0m"; }
warn()  { echo -e "    \033[0;33mWARN: $*\033[0m"; }
fail()  { echo -e "    \033[0;31mERROR: $*\033[0m"; exit 1; }

# --- 1. Install Docker (skip if already installed) ---
step "Checking Docker"
if command -v docker &>/dev/null && docker info &>/dev/null 2>&1; then
    ok "Docker is already installed and running"
else
    warn "Docker not found — installing via the official script"
    curl -fsSL https://get.docker.com | sudo sh
    sudo usermod -aG docker "$USER"
    ok "Docker installed. NOTE: log out and back in (or run 'newgrp docker') so your user can run docker without sudo."
    ok "Then re-run this script."
    exit 0
fi

# --- 2. Install NVIDIA Container Toolkit (skip if already installed) ---
step "Checking NVIDIA Container Toolkit"
if dpkg -s nvidia-container-toolkit &>/dev/null 2>&1; then
    ok "NVIDIA Container Toolkit already installed"
else
    warn "Installing NVIDIA Container Toolkit"
    curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
        | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
    curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
        | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
        | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
    sudo apt-get update -q
    sudo apt-get install -y nvidia-container-toolkit
    sudo nvidia-ctk runtime configure --runtime=docker
    sudo systemctl restart docker
    ok "NVIDIA Container Toolkit installed"
fi

# --- 3. Create .env if missing ---
step "Checking .env"
if [[ ! -f .env ]]; then
    cp .env.example .env
    warn ".env created — set a real WEBUI_SECRET_KEY before continuing."
    warn "Edit $SCRIPT_DIR/.env then re-run this script."
    exit 0
fi

if grep -q "change-this-to-a-random-string" .env; then
    fail "Secret keys are still placeholders. Edit $SCRIPT_DIR/.env and set real values for WEBUI_SECRET_KEY and SEARXNG_SECRET_KEY."
fi
ok ".env looks good"

# --- 4. Start containers ---
step "Starting containers"
docker compose up -d
ok "Containers started"

# --- 5. Enable stack to start on boot ---
step "Enabling on boot via systemd"
SERVICE_FILE="/etc/systemd/system/ollama-stack.service"
if [[ ! -f "$SERVICE_FILE" ]]; then
    sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=Ollama + Open WebUI
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=${SCRIPT_DIR}
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=120

[Install]
WantedBy=multi-user.target
EOF
    sudo systemctl daemon-reload
    sudo systemctl enable ollama-stack.service
    ok "Stack will now start automatically on boot"
else
    ok "systemd service already exists"
fi

# --- 6. Wait for Ollama ---
step "Waiting for Ollama to be ready"
MAX=60; WAITED=0
until curl -sf http://localhost:11434 &>/dev/null; do
    sleep 2; WAITED=$((WAITED+2))
    [[ $WAITED -ge $MAX ]] && fail "Ollama did not respond after ${MAX}s. Check: docker logs ollama"
    echo "    ... waiting (${WAITED}s)"
done
ok "Ollama is ready"

# --- 7. Pull model ---
step "Pulling llama3.1:8b (first run will download ~5 GB)"
docker exec ollama ollama pull llama3.1:8b
ok "Model ready"

# --- Done ---
echo ""
echo -e "\033[0;32m==========================================\033[0m"
echo -e "\033[0;32m  Setup complete!\033[0m"
echo -e "\033[0;32m  Open WebUI: http://localhost:3000\033[0m"
echo ""
echo -e "  Share with devices on your network:"
echo -e "    http://$(hostname -I | awk '{print $1}'):3000"
echo -e "\033[0;32m==========================================\033[0m"
