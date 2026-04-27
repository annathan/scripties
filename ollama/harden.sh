#!/usr/bin/env bash
# Server hardening: SSH, UFW firewall, fail2ban, automatic security updates.
# Run once after initial OS install, before ./setup.sh
# Requires sudo.
set -euo pipefail

step()  { echo -e "\n\033[0;36m==> $*\033[0m"; }
ok()    { echo -e "    \033[0;32mOK: $*\033[0m"; }
warn()  { echo -e "    \033[0;33mWARN: $*\033[0m"; }
fail()  { echo -e "    \033[0;31mERROR: $*\033[0m"; exit 1; }

[[ $EUID -eq 0 ]] && fail "Run as a normal user with sudo rights, not as root."

# ── SSH key check ─────────────────────────────────────────────────────────────
step "Checking SSH keys"
if [[ ! -f "$HOME/.ssh/authorized_keys" ]] || [[ ! -s "$HOME/.ssh/authorized_keys" ]]; then
    warn "No SSH public key found in ~/.ssh/authorized_keys"
    warn "Add your public key BEFORE disabling password auth or you will lock yourself out."
    warn "From your Windows PC: ssh-keygen (if needed), then:"
    warn "  ssh-copy-id $(whoami)@$(hostname -I | awk '{print $1}')"
    read -r -p "    Have you copied your SSH key to this server? [y/N] " CONFIRM
    [[ "$CONFIRM" =~ ^[Yy]$ ]] || { echo "Aborting — add your key first."; exit 1; }
fi
ok "SSH key present"

# ── Harden SSH daemon ─────────────────────────────────────────────────────────
step "Hardening SSH"
SSHD_CONF="/etc/ssh/sshd_config"
sudo cp "$SSHD_CONF" "${SSHD_CONF}.bak.$(date +%s)"

sudo sed -i 's/^#*PermitRootLogin.*/PermitRootLogin no/' "$SSHD_CONF"
sudo sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication no/' "$SSHD_CONF"
sudo sed -i 's/^#*PubkeyAuthentication.*/PubkeyAuthentication yes/' "$SSHD_CONF"
sudo sed -i 's/^#*MaxAuthTries.*/MaxAuthTries 3/' "$SSHD_CONF"
sudo sed -i 's/^#*LoginGraceTime.*/LoginGraceTime 20/' "$SSHD_CONF"

# Add settings if not already present
grep -q "^AllowUsers" "$SSHD_CONF" || echo "AllowUsers $(whoami)" | sudo tee -a "$SSHD_CONF" > /dev/null

sudo systemctl reload sshd
ok "SSH hardened: password auth disabled, root login disabled"

# ── UFW firewall ──────────────────────────────────────────────────────────────
step "Configuring UFW firewall"
sudo apt-get install -y ufw > /dev/null

sudo ufw --force reset
sudo ufw default deny incoming
sudo ufw default allow outgoing

# SSH — rate limited (blocks brute force at firewall level too)
sudo ufw limit 22/tcp comment "SSH rate-limited"

# Open WebUI — LAN only (change subnet to match your router, e.g. 192.168.1.0/24)
LAN_SUBNET="192.168.0.0/16"
sudo ufw allow from "$LAN_SUBNET" to any port 3000 proto tcp comment "Open WebUI LAN"

# Portainer — LAN only
sudo ufw allow from "$LAN_SUBNET" to any port 9000 proto tcp comment "Portainer LAN"

sudo ufw --force enable
ok "UFW enabled: SSH rate-limited, ports 3000+9000 LAN-only, everything else denied"
warn "If your LAN subnet differs from 192.168.0.0/16, edit the rules:"
warn "  sudo ufw delete allow from 192.168.0.0/16 to any port 3000"
warn "  sudo ufw allow from <your-subnet> to any port 3000 proto tcp"

# ── fail2ban ──────────────────────────────────────────────────────────────────
step "Installing fail2ban"
sudo apt-get install -y fail2ban > /dev/null

sudo tee /etc/fail2ban/jail.local > /dev/null <<'EOF'
[DEFAULT]
bantime  = 1h
findtime = 10m
maxretry = 5
backend  = systemd

[sshd]
enabled  = true
port     = ssh
maxretry = 3
bantime  = 24h
EOF

sudo systemctl enable --now fail2ban
ok "fail2ban installed: SSH bans after 3 attempts for 24h"

# ── Automatic security updates ────────────────────────────────────────────────
step "Enabling automatic security updates"
sudo apt-get install -y unattended-upgrades > /dev/null

sudo tee /etc/apt/apt.conf.d/50unattended-upgrades > /dev/null <<'EOF'
Unattended-Upgrade::Allowed-Origins {
    "${distro_id}:${distro_codename}-security";
};
Unattended-Upgrade::AutoFixInterruptedDpkg "true";
Unattended-Upgrade::MinimalSteps "true";
Unattended-Upgrade::Remove-Unused-Dependencies "true";
Unattended-Upgrade::Automatic-Reboot "false";
EOF

sudo tee /etc/apt/apt.conf.d/20auto-upgrades > /dev/null <<'EOF'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF

ok "Automatic security updates enabled (no auto-reboot)"

# ── Docker socket permissions ─────────────────────────────────────────────────
step "Checking Docker socket access"
if groups | grep -q docker; then
    ok "User is in docker group"
else
    warn "User not in docker group — run: sudo usermod -aG docker \$USER && newgrp docker"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo ""
echo -e "\033[0;32m==========================================\033[0m"
echo -e "\033[0;32m  Hardening complete\033[0m"
echo ""
echo "  What was configured:"
echo "  - SSH: key-only auth, root login disabled, MaxAuthTries 3"
echo "  - UFW: SSH rate-limited, WebUI/Portainer LAN-only, all else denied"
echo "  - fail2ban: SSH bans after 3 failures (24h)"
echo "  - Unattended-upgrades: security patches auto-applied"
echo ""
echo "  Next: run ./setup.sh to start the Docker stack"
echo -e "\033[0;32m==========================================\033[0m"
