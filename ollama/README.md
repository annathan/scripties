# Self-Hosted LLM — Ollama + Open WebUI

A Docker Compose stack that runs Ollama (LLM backend) and Open WebUI (ChatGPT-like frontend) with NVIDIA GPU acceleration. Designed for an Ubuntu home server, accessible from any device on the local network.

**Hardware used:** RTX 3060 12GB, 32GB RAM — runs 8B models fully on GPU with headroom for 13B quantised.

---

## Setup order

```
1. Install Ubuntu         → ubuntu install + NVIDIA drivers
2. Harden the server      → harden.sh
3. Start the stack        → setup.sh
4. System prompt          → paste system-prompt.txt into Admin Panel
5. Google sign-in         → .env + Google Cloud Console
6. Install as an app      → PWA in Chrome/Safari
7. Web search             → SearXNG (already in stack, enable in Admin Panel)
8. Feature requests       → tools/feature-request.py + ntfy app on your phone
9. Azure monitoring       → onboard-arc.sh + deploy-dcr.ps1
10. Remote access         → Entra App Proxy or Cloudflare Tunnel (when ready)
```

---

## Part 1 — Install Ubuntu

Install **Ubuntu 24.04 LTS** (Server edition — no GUI needed).

During install:
- Create a user account you'll remember
- Enable OpenSSH server

After first boot:

```bash
sudo apt update && sudo apt upgrade -y && sudo reboot
```

### Install NVIDIA drivers

```bash
sudo ubuntu-drivers autoinstall
sudo reboot
nvidia-smi   # verify — should show RTX 3060 with 12GB VRAM
```

---

## Part 2 — Harden the Server

Run this **before** setting up Docker. It configures SSH, firewall, and automatic security updates.

```bash
chmod +x harden.sh
./harden.sh
```

**Before running:** copy your SSH public key from your Windows PC first, or the script will stop and warn you:

```powershell
# On your Windows PC (run once if you don't have a key yet)
ssh-keygen

# Then copy it to the server
ssh-copy-id youruser@192.168.x.x
```

**What `harden.sh` does:**
- SSH: disables password auth and root login, limits auth attempts
- UFW firewall: SSH rate-limited; ports 3000 (WebUI) and 9000 (Portainer) allowed from LAN only; everything else denied
- fail2ban: bans IPs after 3 failed SSH attempts for 24 hours
- Unattended-upgrades: security patches applied automatically

---

## Part 3 — Set Up the Stack

```bash
chmod +x setup.sh
./setup.sh
```

The script:
1. Installs Docker (official installer)
2. Installs NVIDIA Container Toolkit (GPU passthrough)
3. Creates `.env` — **edit it before re-running** (see below)
4. Starts the containers (Ollama, Open WebUI, Portainer)
5. Registers the stack as a systemd service — starts on boot without login
6. Pulls `llama3.1:8b` (~5 GB)

### Set the secret key in `.env`

```bash
nano .env
```

Generate a key:
```bash
openssl rand -hex 32
```

Re-run `./setup.sh` after saving.

---

## Part 4 — System Prompt (Tone + Context)

This is the single most impactful config change — it tells the model how to behave in every conversation before anyone types a word.

The file `system-prompt.txt` in this folder contains tone and style rules only — the things that should apply globally to every conversation:
- No "Certainly!", "Great question!", "Absolutely!" openers
- No reframe correction structure ("It's not X, it's really Y")
- Natural, conversational tone throughout
- Plain language, no AI padding

It deliberately contains **no context about who the users are or what they do** — that's personal to each user and they should build it themselves (see below).

### Applying the global tone prompt

1. Open `http://<server-IP>:3000` and sign in as admin
2. **Admin Panel → Settings → Interface → Default System Prompt**
3. Paste the contents of `system-prompt.txt` and save

### Jess builds her own context

Open WebUI has two ways for a user to add personal context — and Jess should do this herself so it reflects how she actually works:

**Memory (builds over time):** In **Settings → Personalization → Memory**, she can tell it things once and they stick across all future conversations — her role, the year groups she supports, how she likes explanations pitched. The model also accumulates facts as she chats, so it gets more useful the more she uses it.

**User system prompt (her permanent context):** In **Settings → Personalization → System Prompt**, she can write a short note about herself — e.g. "I'm a School Learning Support Officer working with Years 7–12, including students with learning difficulties." This gets prepended to every conversation she has, on top of the global tone rules.

The split means the tone is consistent for both of you, but her professional context is hers to own and refine over time.

> You can also set per-model overrides in **Admin Panel → Models** if you ever want one model to behave differently from another.

---

## Part 5 — Google Sign-In


Open WebUI supports Google OAuth — sign in with your Google accounts, no separate passwords.

### One-time setup (~5 minutes)

1. Go to [console.cloud.google.com](https://console.cloud.google.com) → create a project (e.g. "Home AI")
2. **APIs & Services → Credentials → Create Credentials → OAuth 2.0 Client ID**
3. Application type: **Web application**
4. Under **Authorised redirect URIs**, add:
   ```
   http://localhost:3000/oauth/google/callback
   http://<server-LAN-IP>:3000/oauth/google/callback
   ```
   (Find the LAN IP: `hostname -I`)
5. Add to `.env`:
   ```
   GOOGLE_CLIENT_ID=xxxxxxxx.apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=GOCSPX-xxxxxxxx
   ENABLE_OAUTH_SIGNUP=true
   ```
6. `docker compose restart open-webui`

> Once both accounts are set up, disable email/password signup in **Admin Panel → Settings → General** so only Google sign-in works.

---

## Part 6 — Use it Like an App + Voice Input

Open WebUI is a **Progressive Web App (PWA)** — install it as a standalone app with its own icon and no browser bar.

### Installing as an app

**On any laptop (Chrome or Edge):**
1. Open `http://<server-IP>:3000`
2. Click the install icon (⊕) in the address bar → **"Install Open WebUI"**
3. Appears in the taskbar/Start Menu, opens in its own window

**On Android (Chrome):**  Three-dot menu → **"Add to Home screen"**

**On iPhone/iPad (Safari):**  Share button → **"Add to Home Screen"**

### Voice input (speech to text)

Open WebUI has a built-in microphone button in the chat input bar. Tap it, speak, and it transcribes via the browser's Web Speech API — same as voice-to-text on any other app.

- Works on Chrome, Edge, Safari (desktop and mobile)
- No extra setup or server-side component needed
- The microphone icon appears in the message input box

> Enable it in **Settings → Voice** within Open WebUI if it doesn't appear by default.

---

## Part 7 — Web Search (SearXNG)

SearXNG is already in the Docker stack — it's a self-hosted meta-search engine that queries Google, Bing, DuckDuckGo, and Wikipedia on your behalf. Nothing leaves the house with your identity attached.

### Enable it in Open WebUI (one-time)

1. Sign in as admin, go to **Admin Panel → Settings → Web Search**
2. Toggle **Enable Web Search** on
3. Set **Web Search Engine** to `searxng`
4. Set the URL to `http://searxng:8080`
5. Save

### Using it

A search toggle button appears in the chat input bar. When active, the model fetches live results and works them into its answer — useful for anything time-sensitive or requiring current information that isn't in its training data.

> Google Scholar is included as an engine, weighted higher — handy for Jess when researching evidence-based learning support strategies.

---

## Part 8 — Feature Requests to Drew (ntfy)

Jess can say "tell Drew I want X" in any conversation and the model will send you a push notification. No buttons, no forms — just natural language.

### Step 1 — Get a channel name

Pick a long random string for your private channel name. Generate one:

```bash
openssl rand -hex 8
# example output: a3f7c2d09e1b4852
```

Your channel URL will be: `https://ntfy.sh/drew-llm-a3f7c2d09e1b4852`

No account needed on ntfy.sh. The channel name is the only thing keeping it private, so make it random.

### Step 2 — Install the ntfy app

Install **ntfy** on your phone ([Android](https://play.google.com/store/apps/details?id=io.heckel.ntfy) / [iOS](https://apps.apple.com/app/ntfy/id1625396347)) and subscribe to your channel URL.

### Step 3 — Install the tool in Open WebUI

1. Open `tools/feature-request.py` from this repo
2. In Open WebUI: **Admin Panel → Tools → + (Add Tool)**
3. Paste the contents of the file
4. In the **Valves** section, replace `your-channel-name-here` with your actual channel name
5. Save and enable the tool

### Step 4 — Tell the model about it (add to system prompt)

Add one line to the end of `system-prompt.txt` before you paste it into the Admin Panel:

```
If the user asks you to tell Drew something or request a feature, use the send_feature_request tool.
```

### How it works

Jess types anything like *"this is great but can you tell Drew I'd like it to read responses aloud?"* — the model calls the tool, you get a notification on your phone with her exact request.

---

## Part 10 — Managing Docker from Windows (Portainer)

Portainer runs as part of the stack and gives you a browser-based Docker management UI — no need to SSH in for day-to-day tasks.

Open from your Windows PC: **`http://<server-IP>:9000`**

From Portainer you can:
- See all containers and their status
- Restart or stop individual containers
- Browse container logs in real time
- Pull new images / update containers

---

## Part 11 — Azure Monitoring (Sentinel)

Ships SSH auth events, sudo logs, and firewall activity to your existing Sentinel workspace via Azure Arc + Azure Monitor Agent.

### Step 1 — Onboard the server to Azure Arc

On the **Linux server**:

```bash
export SUBSCRIPTION_ID="your-subscription-id"
export RESOURCE_GROUP="rg-home-llm"        # create this RG in Azure first if needed
export TENANT_ID="your-tenant-id"
export LOCATION="australiaeast"
export MACHINE_NAME="home-llm-server"

chmod +x monitoring/onboard-arc.sh
./monitoring/onboard-arc.sh
```

A device-login URL will appear — open it on any device to authenticate.

### Step 2 — Deploy the DCR and install AMA

On your **Windows PC**:

```powershell
cd ollama/

.\monitoring\deploy-dcr.ps1 `
    -SubscriptionId   "your-subscription-id" `
    -ResourceGroupName "rg-home-llm" `
    -WorkspaceName    "your-workspace-name" `
    -ArcMachineName   "home-llm-server" `
    -Location         "australiaeast"
```

This deploys `monitoring/dcr-template.json` which:
- Creates a Data Collection Rule collecting `auth`/`authpriv` (SSH, sudo), `daemon` (Docker), and `kern` (UFW firewall) syslog facilities
- Associates the DCR with the Arc machine
- Installs the Azure Monitor Agent extension

### Verify in Sentinel

Logs appear in the `Syslog` table within ~5 minutes:

```kql
Syslog
| where Computer == "home-llm-server"
| where Facility in ("auth", "authpriv")
| order by TimeGenerated desc
| take 50
```

Useful analytics rules to enable in Sentinel:
- **Failed SSH brute force** — built-in rule, detects multiple failures from a single IP
- **Successful login after brute force** — correlation rule
- **Sudo privilege escalation** — search for `COMMAND` in auth syslog

---

## Part 12 — Remote Access from School (Phase 2)

Two options — pick based on your Azure licensing.

### Option A: Microsoft Entra Application Proxy (recommended if you have Entra P1)

Runs a connector on the server that calls out to Microsoft — no inbound ports, full Entra ID authentication and Conditional Access in front of the WebUI, and all access events flow directly into Sentinel.

Requires: **Microsoft Entra ID P1** (included in Microsoft 365 Business Premium / E3/E5).

Setup:
1. In Entra admin centre: **Applications → Enterprise Applications → New application → On-premises application**
2. Set the internal URL to `http://localhost:3000`
3. Download and install the **Application Proxy Connector** on the Linux server
4. Assign your wife's account to the app
5. Add the generated `https://` URL to Google OAuth **Authorised redirect URIs**

She gets an `https://` URL she can open from anywhere, protected by her Entra/Microsoft login and any Conditional Access policies you apply.

### Option B: Cloudflare Tunnel (free, no license needed)

Uncomment the `cloudflared` service in `docker-compose.yml`, then:

1. Free account at [cloudflare.com](https://cloudflare.com)
2. **Zero Trust → Networks → Tunnels → Create a tunnel → Cloudflared**
3. Copy the token, set tunnel to route to `http://open-webui:8080`
4. Add `CLOUDFLARE_TUNNEL_TOKEN=<token>` to `.env`
5. Add the new `https://` URL to your Google OAuth **Authorised redirect URIs**
6. `docker compose up -d`

---

## Day-to-Day Commands

| Task | Command (on server) |
|---|---|
| Start the stack | `docker compose up -d` |
| Stop the stack | `docker compose down` |
| Restart WebUI only | `docker compose restart open-webui` |
| View logs | `docker logs open-webui` / `docker logs ollama` |
| Pull a model | `docker exec ollama ollama pull <model>` |
| List models | `docker exec ollama ollama list` |
| Check what's running on GPU | `docker exec ollama ollama ps` |

### Models your 3060 (12GB VRAM) can run

| Model | VRAM | Speed | Good for |
|---|---|---|---|
| `llama3.1:8b` | ~5 GB | Fast | General chat, Q&A, writing (installed by default) |
| `mistral:7b` | ~4.5 GB | Fast | General use, instructions |
| `gemma2:9b` | ~5.5 GB | Fast | Reasoning, following instructions |
| `llama3.1:13b` | ~8 GB | Moderate | Noticeably smarter, still fits entirely on GPU |
| `phi3:mini` | ~2.3 GB | Very fast | Quick answers, low footprint |

---

## Troubleshooting

**GPU not being used:**
```bash
docker exec ollama ollama ps
# If shows CPU: verify nvidia-smi works and NVIDIA Container Toolkit is installed
```

**Can't reach WebUI from another device on LAN:**
```bash
sudo ufw status          # check port 3000 is allowed from your LAN subnet
sudo ufw allow from 192.168.0.0/16 to any port 3000 proto tcp
```

**Container logs:**
```bash
docker logs open-webui
docker logs ollama
docker logs portainer
```

**Google sign-in not appearing:**
- Check `.env` has `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` (no quotes, no extra spaces)
- `docker compose restart open-webui`

**fail2ban status (check if your own IP got banned):**
```bash
sudo fail2ban-client status sshd
sudo fail2ban-client set sshd unbanip <your-ip>
```
