# Self-Hosted LLM — Ollama + Open WebUI

A Docker Compose stack that runs Ollama (LLM backend) and Open WebUI (ChatGPT-like frontend) with NVIDIA GPU acceleration. Designed for an Ubuntu home server, accessible from any device on the local network.

**Hardware used:** RTX 3060 12GB, 32GB RAM — can run 8B models fully on GPU with headroom for 13B quantised.

---

## Part 1 — Install Ubuntu

Install **Ubuntu 24.04 LTS** (Server edition is fine — no GUI needed).

During install:
- Create a user account you'll remember
- Enable OpenSSH server so you can manage it remotely from your main PC

After first boot, update everything:

```bash
sudo apt update && sudo apt upgrade -y && sudo reboot
```

### Install NVIDIA drivers

```bash
sudo ubuntu-drivers autoinstall
sudo reboot
```

Verify after reboot:
```bash
nvidia-smi
```
You should see your RTX 3060 listed with driver version and VRAM.

---

## Part 2 — Set Up the Stack

Clone this repo (or copy the `ollama/` folder) onto the server, then run the setup script:

```bash
cd ollama/
chmod +x setup.sh
./setup.sh
```

The script handles everything in order:
1. Installs Docker (official installer, adds you to the `docker` group)
2. Installs NVIDIA Container Toolkit (GPU passthrough for Docker)
3. Creates a `.env` file — **you'll need to edit it before re-running** (see below)
4. Starts the containers
5. Registers the stack as a systemd service so it starts automatically on boot
6. Waits for Ollama, then pulls `llama3.1:8b` (~5 GB)

### The `.env` file

After the first run creates it, edit `.env`:

```bash
nano ollama/.env
```

Set a real secret key — generate one with:
```bash
openssl rand -hex 32
```

Then re-run `./setup.sh` to continue.

---

## Part 3 — Google Sign-In

Open WebUI supports Google OAuth out of the box. This means you and your wife sign in with your Google accounts — no separate passwords.

### One-time setup (~5 minutes)

1. Go to [console.cloud.google.com](https://console.cloud.google.com) → create a project (name it anything, e.g. "Home AI")
2. **APIs & Services → Credentials → Create Credentials → OAuth 2.0 Client ID**
3. Application type: **Web application**
4. Under **Authorised redirect URIs**, add:
   ```
   http://localhost:3000/oauth/google/callback
   http://<server-LAN-IP>:3000/oauth/google/callback
   ```
   Find your server's LAN IP with: `hostname -I`
5. Copy **Client ID** and **Client Secret** into `.env`:
   ```
   GOOGLE_CLIENT_ID=xxxxxxxx.apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=GOCSPX-xxxxxxxx
   ENABLE_OAUTH_SIGNUP=true
   ```
6. Restart: `docker compose restart open-webui`

The login page will now show **Sign in with Google**. First sign-in auto-creates the account.

> Once both accounts are created, you can disable email/password signup in **Admin Panel → Settings → General** so only Google sign-in works.

---

## Part 4 — Use it Like an App

Open WebUI is a **Progressive Web App (PWA)** — you can install it to feel like a native app with its own icon and no browser bar.

### On any laptop (Chrome or Edge)
1. Open `http://<server-IP>:3000` in Chrome or Edge
2. Click the install icon (⊕) in the address bar, or **browser menu → "Install Open WebUI"**
3. It appears in the taskbar/Start Menu as a standalone app

### On Android (Chrome)
1. Open the URL in Chrome
2. Three-dot menu → **"Add to Home screen"**

### On iPhone/iPad (Safari)
1. Open the URL in Safari
2. Share button → **"Add to Home Screen"**

Your wife taps the icon and goes straight to the chat — same experience as the ChatGPT or Claude app.

---

## Part 5 — Sharing on the Home Network

The setup script prints your server's LAN IP at the end. To find it again:

```bash
hostname -I
```

Give her the URL: `http://192.168.x.x:3000`

Any device on your home Wi-Fi can reach it. She signs in with Google and installs it as a PWA (above).

---

## Day-to-Day Commands

| Task | Command |
|---|---|
| Start the stack | `docker compose up -d` |
| Stop the stack | `docker compose down` |
| Restart after config change | `docker compose restart open-webui` |
| View logs | `docker logs open-webui` or `docker logs ollama` |
| Pull another model | `docker exec ollama ollama pull <model>` |
| List models | `docker exec ollama ollama list` |
| Remove a model | `docker exec ollama ollama rm <model>` |

### Models your 3060 (12GB VRAM) can run

| Model | VRAM | Speed | Good for |
|---|---|---|---|
| `llama3.1:8b` | ~5 GB | Fast | General chat, Q&A, writing (already installed) |
| `mistral:7b` | ~4.5 GB | Fast | General use, instructions |
| `gemma2:9b` | ~5.5 GB | Fast | Reasoning, following instructions |
| `llama3.1:13b` | ~8 GB | Moderate | Noticeably smarter, still fits on GPU |
| `phi3:mini` | ~2.3 GB | Very fast | Quick answers, low footprint |

Pull any with:
```bash
docker exec ollama ollama pull llama3.1:13b
```

---

## Part 6 — Remote Access from School (Phase 2)

When you're ready for her to access it outside the home network, use a **Cloudflare Tunnel** — no port forwarding, no router changes, and she gets a stable `https://` URL.

Add to `docker-compose.yml`:

```yaml
  cloudflared:
    image: cloudflare/cloudflared:latest
    container_name: cloudflared
    command: tunnel --no-autoupdate run
    environment:
      - TUNNEL_TOKEN=${CLOUDFLARE_TUNNEL_TOKEN}
    depends_on:
      - open-webui
    restart: unless-stopped
```

Add to `.env`:
```
CLOUDFLARE_TUNNEL_TOKEN=<your-token>
```

To get a token:
1. Free account at [cloudflare.com](https://cloudflare.com)
2. **Zero Trust → Networks → Tunnels → Create a tunnel → Cloudflared**
3. Copy the token, set tunnel to route to `http://open-webui:8080`
4. Add the new `https://` URL to your Google OAuth **Authorised redirect URIs**

Then restart: `docker compose up -d`

---

## Troubleshooting

**Check GPU is being used:**
```bash
docker exec ollama ollama ps
# Should show model on GPU. If it says CPU, check nvidia-smi runs and Container Toolkit is installed.
```

**Can't reach from another device:**
```bash
sudo ufw allow 3000/tcp   # if ufw firewall is active
```

**Logs:**
```bash
docker logs open-webui
docker logs ollama
```

**Google sign-in not showing:**
- Check `.env` has `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` set (no quotes, no spaces)
- `docker compose restart open-webui`
