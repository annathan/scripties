#!/usr/bin/env bash
# Onboard this Linux server to Azure Arc and install Azure Monitor Agent.
# Run after harden.sh and setup.sh.
#
# What this does:
#   1. Installs the Azure Connected Machine agent (Arc)
#   2. Connects the machine to your Azure subscription
#   3. Installs Azure Monitor Agent via Arc extension
#
# Once done, deploy monitoring/dcr-template.json via Azure Portal or
# the companion deploy-dcr.ps1 to start shipping logs to Sentinel.
set -euo pipefail

step()  { echo -e "\n\033[0;36m==> $*\033[0m"; }
ok()    { echo -e "    \033[0;32mOK: $*\033[0m"; }
warn()  { echo -e "    \033[0;33mWARN: $*\033[0m"; }
fail()  { echo -e "    \033[0;31mERROR: $*\033[0m"; exit 1; }

# ── Config — fill these in ────────────────────────────────────────────────────
SUBSCRIPTION_ID="${SUBSCRIPTION_ID:-}"
RESOURCE_GROUP="${RESOURCE_GROUP:-}"
LOCATION="${LOCATION:-uksouth}"
TENANT_ID="${TENANT_ID:-}"
# Optional: tag the machine in Azure
MACHINE_NAME="${MACHINE_NAME:-home-llm-server}"

if [[ -z "$SUBSCRIPTION_ID" || -z "$RESOURCE_GROUP" || -z "$TENANT_ID" ]]; then
    echo ""
    echo "Set these environment variables before running, or edit this script:"
    echo "  export SUBSCRIPTION_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
    echo "  export RESOURCE_GROUP=rg-home-llm"
    echo "  export TENANT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
    echo "  export LOCATION=uksouth    # change to your region"
    echo "  export MACHINE_NAME=home-llm-server"
    exit 1
fi

# ── Install Arc Connected Machine agent ───────────────────────────────────────
step "Installing Azure Connected Machine agent"

if command -v azcmagent &>/dev/null; then
    ok "azcmagent already installed"
else
    # Add Microsoft package repo
    curl -sSL https://packages.microsoft.com/keys/microsoft.asc \
        | sudo gpg --dearmor -o /usr/share/keyrings/microsoft.gpg

    CODENAME=$(lsb_release -cs)
    echo "deb [arch=amd64 signed-by=/usr/share/keyrings/microsoft.gpg] \
https://packages.microsoft.com/ubuntu/$(lsb_release -rs)/prod ${CODENAME} main" \
        | sudo tee /etc/apt/sources.list.d/microsoft.list > /dev/null

    sudo apt-get update -q
    sudo apt-get install -y azcmagent
    ok "azcmagent installed"
fi

# ── Connect to Azure Arc ───────────────────────────────────────────────────────
step "Connecting to Azure Arc (browser login required)"
warn "A device login prompt will appear — open the URL on any device and enter the code."

sudo azcmagent connect \
    --subscription-id  "$SUBSCRIPTION_ID" \
    --resource-group   "$RESOURCE_GROUP" \
    --location         "$LOCATION" \
    --tenant-id        "$TENANT_ID" \
    --resource-name    "$MACHINE_NAME" \
    --cloud            "AzureCloud"

ok "Machine connected to Azure Arc as: $MACHINE_NAME"
echo "    View in portal: https://portal.azure.com -> Azure Arc -> Machines"

# ── Install Azure Monitor Agent extension ─────────────────────────────────────
step "Installing Azure Monitor Agent via Arc extension"
warn "This step is best done from Azure Portal or via the deploy-dcr.ps1 script."
warn "In the portal: Azure Arc -> Machines -> $MACHINE_NAME -> Extensions -> Add -> Azure Monitor Agent"
echo ""
echo "  Or run deploy-dcr.ps1 from your Windows machine — it installs AMA and"
echo "  deploys the Data Collection Rule in one step."

echo ""
echo -e "\033[0;32m==========================================\033[0m"
echo -e "\033[0;32m  Arc onboarding complete\033[0m"
echo ""
echo "  Next steps:"
echo "  1. On your Windows PC, run: monitoring/deploy-dcr.ps1"
echo "  2. This creates the DCR and links it to this machine"
echo "  3. Logs will appear in Sentinel within ~5 minutes"
echo -e "\033[0;32m==========================================\033[0m"
