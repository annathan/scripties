# Self-Hosted LLM — Ollama + Open WebUI

A Docker Compose stack that runs Ollama (LLM backend) and Open WebUI (ChatGPT-like frontend) with NVIDIA GPU acceleration. Designed for an Ubuntu home server, accessible from any device on the local network.

**Hardware used:** MSI Thin 15, RTX 2050 4GB VRAM — runs 3B–4B models fully on GPU at good speed. 7B models fit with tight quantisation; 8B models spill into RAM and are noticeably slower.

---

## Setup order

```
1.  Install Ubuntu         → ubuntu install + NVIDIA drivers
2.  Laptop setup           → lid close, suspend, GPU persistence
3.  Harden the server      → harden.sh
4.  Start the stack        → setup.sh
5.  System prompt          → paste system-prompt.txt into Admin Panel
6.  Google sign-in         → .env + Google Cloud Console
7.  Install as an app      → PWA in Chrome/Safari
8.  Web search             → SearXNG (already in stack, enable in Admin Panel)
9.  Feature requests       → tools/feature-request.py + ntfy app on your phone
10. Home automation        → tools/home-assistant.py + home-automation/packages/llm_conversation.yaml
11. Azure monitoring       → onboard-arc.sh + deploy-dcr.ps1
12. Remote access          → Entra App Proxy or Cloudflare Tunnel (when ready)
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

## Part 2 — Laptop-Specific Setup

The MSI Thin 15 is running headless as a server. Two things will bite you if you skip this step: closing the lid suspends the machine (killing the stack), and Ubuntu's power management may throttle the GPU under sustained load.

### Prevent suspend when lid is closed

```bash
sudo nano /etc/systemd/logind.conf
```

Set these lines (uncomment if they're commented out):

```ini
HandleLidSwitch=ignore
HandleLidSwitchExternalPower=ignore
HandleLidSwitchDocked=ignore
```

Apply without rebooting:

```bash
sudo systemctl restart systemd-logind
```

The lid can now be closed and the machine keeps running. Verify with `systemctl status` — it should stay active.

### Keep the machine awake (disable auto-suspend)

```bash
sudo systemctl mask sleep.target suspend.target hibernate.target hybrid-sleep.target
```

### Disable GPU power saving (prevents cold-start latency on first inference)

```bash
sudo nvidia-smi -pm 1        # enable persistence mode — GPU stays warm
sudo nvidia-smi --auto-boost-default=0
```

Make persistence mode survive reboots by adding it to `/etc/rc.local`:

```bash
echo '#!/bin/bash
nvidia-smi -pm 1
exit 0' | sudo tee /etc/rc.local
sudo chmod +x /etc/rc.local
```

### Verify thermals under load

Laptop sustained GPU load can cause throttling. Install monitoring tools:

```bash
sudo apt install nvtop lm-sensors -y
sudo sensors-detect --auto
```

Run `nvtop` while a model is generating to watch GPU temp and clock speed. The RTX 2050 will throttle if it hits ~90°C — if that happens, clean the vents or point a small fan at the underside.

---

## Part 3 — Harden the Server

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

## Part 4 — Set Up the Stack

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

## Part 5 — System Prompt (Tone + Context)

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

## Part 6 — Google Sign-In


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

## Part 7 — Use it Like an App + Voice Input

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

## Part 8 — Web Search (SearXNG)

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

## Part 9 — Feature Requests to Drew (ntfy)

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

## Part 10 — Home Automation Integration

Two parts: a chat tool so Jess can ask about and control the house directly in chat, and a package that wires HA's voice assistant up to Ollama.

### Chat tool — query and control HA from Open WebUI

`tools/home-assistant.py` is an Open WebUI tool that hits the HA REST API. Jess can type things like:

- *"Is the front door locked?"*
- *"Turn off the pool pump"*
- *"How much solar are we generating right now?"*
- *"Close the garage door"*

**Install:**

1. In HA, go to **Profile → Security → Long-lived access tokens → Create token** — copy it somewhere safe
2. In Open WebUI: **Admin Panel → Tools → + (Add Tool)**
3. Paste the contents of `tools/home-assistant.py`
4. In **Valves**, set:
   - `ha_url`: `http://192.168.x.x:8123` (your HA LAN IP)
   - `ha_token`: the token you just generated
5. Save and enable the tool

The model will call it automatically when you ask about any home state or ask it to control a device.

---

### Morning briefing — HA calls Ollama for a daily summary

`home-automation/packages/llm_conversation.yaml` adds a `rest_command.ollama_chat` that any HA automation can use, plus a `script.morning_home_briefing` that runs at 7:30am on weekdays.

The script sends current solar production, pool and hot water state, and outdoor temperature to Ollama, which turns them into a 2–3 sentence push notification in plain English.

**Install:**

1. Edit `home-automation/packages/llm_conversation.yaml` — replace `<your-garage-pc-ip>` with the LAN IP of the Ollama server
2. Drop the file into your HA `packages/` directory (or include the `automation:` and `script:` and `rest_command:` blocks in your `configuration.yaml`)
3. HA → Developer Tools → YAML → Reload All YAML
4. Update the entity names in `script.morning_home_briefing` to match your actual HA entities

---

### Voice assistant — use Ollama as HA's conversation brain

This lets you say *"Hey Google, ask Home Assistant to turn on the pool pump"* and have Ollama decide what to do instead of HA's built-in intent matcher.

**Setup (HA UI):**

1. **Settings → Devices & Services → Add Integration → OpenAI Conversation**
2. Set:
   - **API Key:** `ollama` (any non-empty string — Ollama ignores it)
   - **Base URL:** `http://<your-garage-pc-ip>:11434/v1`
   - **Model:** `llama3.1:8b`
3. **Settings → Voice Assistants** → edit your assistant → set **Conversation agent** to the OpenAI Conversation entry you just created

---

## Part 11 — Managing Docker from Windows (Portainer)

Portainer runs as part of the stack and gives you a browser-based Docker management UI — no need to SSH in for day-to-day tasks.

Open from your Windows PC: **`http://<server-IP>:9000`**

From Portainer you can:
- See all containers and their status
- Restart or stop individual containers
- Browse container logs in real time
- Pull new images / update containers

---

## Part 12 — Azure Monitoring (Sentinel)

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

## Part 13 — Remote Access from School (Phase 2)

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

### Models your RTX 2050 (4GB VRAM) can run

The 4GB ceiling means 8B models won't fit entirely on GPU. Stick to 3B–4B for fast, fully GPU-accelerated responses. 7B models work but need aggressive quantisation and are measurably slower.

| Model | VRAM | Speed | Good for |
|---|---|---|---|
| `gemma3:4b` | ~2.5 GB | Fast | Best all-round at this size — strong reasoning and instruction following (installed by default) |
| `llama3.2:3b` | ~2.0 GB | Very fast | Meta's latest small model, good for chat and Q&A |
| `phi3.5:mini` | ~2.2 GB | Very fast | Microsoft's 3.8B model, punches above its weight |
| `qwen2.5:3b` | ~1.9 GB | Very fast | Strong on structured tasks and multilingual |
| `mistral:7b-instruct-q4_0` | ~3.8 GB | Moderate | Fits on 4GB with Q4 quantisation; noticeably slower than the 3B models |
| `llama3.1:8b` | ~5 GB | Slow | Won't fit on GPU — runs partly in RAM, expect 3–4× slower responses |

**Recommendation:** Start with `gemma3:4b`. If responses feel slow, drop to `llama3.2:3b`. If you need smarter answers and can wait, try `mistral:7b-instruct-q4_0`.

---

## Why Ollama and not vLLM or llama.cpp?

Short answer: Ollama is the right tool for this use case, and the alternatives are for different problems.

vLLM and SGLang are for when a local model becomes backend infrastructure — serving agents, pointing multiple apps at the same API endpoint, or building enterprise-grade inference pipelines. The article that covers them most clearly says *"I wouldn't install either of these before getting acquainted with simpler tools"* and *"Ollama is still the tool I'd point someone to if they just want to get started."*

llama.cpp is foundational (Ollama used to run on top of it) and gives you ~10–15% more throughput with fine-grained memory control. The tradeoff is that you lose model management, the Open WebUI integration, and the easy Docker setup — not worth it for a family chat assistant.

ExLlamaV3 squeezes more out of consumer GPUs specifically, but requires building your own serving layer from scratch.

If the use case ever evolves into something that needs multi-app API serving or agent infrastructure, that's the point to revisit. For now, Ollama is the right fit.

### VRAM fragmentation

Ollama instances degrade after several days of continuous uptime — response times creep up as GPU memory fragments. The stack mitigates this two ways:

- **Env vars** (`OLLAMA_KEEP_ALIVE=5m`, `OLLAMA_MAX_LOADED_MODELS=1`) — model unloads when idle and only one model occupies VRAM at a time
- **Daily restart timer** — `setup.sh` registers a systemd timer that restarts just the `ollama` container at 3am. Open WebUI reconnects automatically on the next request, so there's no visible interruption.

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
