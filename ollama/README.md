# Self-Hosted LLM — Ollama + Open WebUI

A Docker Compose stack that runs Ollama (LLM backend) and Open WebUI (ChatGPT-like frontend) on your home PC with NVIDIA GPU acceleration.

---

## Prerequisites

Install these once before running setup:

1. **Docker Desktop for Windows** — [download](https://www.docker.com/products/docker-desktop/)
   - During install, enable the **WSL 2** backend when prompted
2. **NVIDIA Container Toolkit for WSL 2** — lets Docker use your GPU
   - Follow the [NVIDIA WSL 2 guide](https://docs.nvidia.com/cuda/wsl-user-guide/index.html)
   - Short version: install the CUDA driver for WSL from [developer.nvidia.com/cuda-downloads](https://developer.nvidia.com/cuda-downloads), then restart Docker Desktop

---

## First-Time Setup

Open **PowerShell** in this directory and run:

```powershell
.\setup.ps1
```

The script will:
1. Verify Docker is running
2. Create a `.env` file (you'll need to set a secret key — it will tell you if this is needed)
3. Start both containers
4. Wait for Ollama to be ready
5. Pull the `llama3.1:8b` model (~5 GB download)

When done, open **http://localhost:3000** in your browser, create an account, and start chatting.

---

## Google Sign-In (Recommended)

Open WebUI has built-in Google OAuth support. This means you and your wife can sign in with your Google accounts — no separate passwords to manage, and it feels just like any modern app.

### One-time setup (takes ~5 minutes)

1. Go to [console.cloud.google.com](https://console.cloud.google.com) and create a project (name it anything, e.g. "Home AI")
2. Navigate to **APIs & Services → Credentials → Create Credentials → OAuth 2.0 Client ID**
3. Set Application type to **Web application**
4. Under **Authorised redirect URIs**, add:
   - `http://localhost:3000/oauth/google/callback`
   - `http://192.168.x.x:3000/oauth/google/callback` (your local IP — run `ipconfig | findstr "IPv4"` to find it)
5. Copy the **Client ID** and **Client Secret** into your `.env` file:
   ```
   GOOGLE_CLIENT_ID=xxxxxxx.apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=GOCSPX-xxxxxxx
   ENABLE_OAUTH_SIGNUP=true
   ```
6. Restart the stack: `docker compose up -d`

The Open WebUI login page will now show a **"Sign in with Google"** button. First login automatically creates the account.

> **Tip:** In Open WebUI settings (Admin Panel → Users) you can disable the email/password signup form entirely once both accounts are created, so only Google sign-in works.

---

## Use it Like an App (No Browser Bar)

Open WebUI is a **Progressive Web App (PWA)**, meaning you can install it to feel like a native app — its own icon, standalone window, no browser address bar — just like the ChatGPT or Claude apps.

### On Windows / Mac (Chrome or Edge)
1. Open `http://localhost:3000` (or the network URL) in Chrome or Edge
2. Look for the **install icon** (⊕) in the address bar, or open the browser menu and choose **"Install Open WebUI"** / **"Add to Desktop"**
3. Click **Install** — it appears as an app in the Start Menu / taskbar

### On Android
1. Open the URL in Chrome
2. Tap the three-dot menu → **"Add to Home screen"**
3. The app icon appears on the home screen, opens full-screen

### On iPhone / iPad
1. Open the URL in **Safari**
2. Tap the Share button (box with arrow) → **"Add to Home Screen"**
3. The app icon appears on the home screen, opens full-screen

> Your wife can do this on her school laptop or phone — she taps/clicks the icon and goes straight into the chat, just like a real app.

---

## Giving Your Wife Access on the Home Network

1. On your PC, run:
   ```powershell
   ipconfig | findstr "IPv4"
   ```
2. Find the address that starts with `192.168.x.x` (or `10.x.x.x`)
3. Share that URL with her: `http://192.168.x.x:3000`

She opens it in Chrome or Safari, signs in with Google, installs it as a PWA (see above), and from then on taps the icon like any app.

---

## Day-to-Day Commands

| Task | Command |
|---|---|
| Start the stack | `docker compose up -d` |
| Stop the stack | `docker compose down` |
| View logs | `docker logs open-webui` or `docker logs ollama` |
| Pull another model | `docker exec ollama ollama pull <model>` |
| List downloaded models | `docker exec ollama ollama list` |
| Remove a model | `docker exec ollama ollama rm <model>` |

### Suggested Models

| Model | Size | Good for |
|---|---|---|
| `llama3.1:8b` | ~5 GB | General chat, Q&A, writing (already installed) |
| `mistral:7b` | ~4.5 GB | Fast responses, general use |
| `gemma2:9b` | ~5.5 GB | Reasoning, instructions |
| `phi3:mini` | ~2.3 GB | Quick answers, low memory use |

Pull any of them with:
```powershell
docker exec ollama ollama pull mistral:7b
```

---

## Remote Access from School (Phase 2)

When you're ready to let her access the LLM from outside your home network, the easiest approach is a **Cloudflare Tunnel** — no port forwarding or router changes needed, and she gets a stable `https://` URL.

Add this service to `docker-compose.yml`:

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

Then add `CLOUDFLARE_TUNNEL_TOKEN=<your-token>` to `.env`.

To get a tunnel token:
1. Sign up free at [cloudflare.com](https://cloudflare.com)
2. Go to **Zero Trust → Networks → Tunnels → Create a tunnel**
3. Choose **Cloudflared**, copy the token
4. Set the tunnel to route to `http://open-webui:8080`
5. Add the new `https://` URL to your Google OAuth **Authorised redirect URIs** (see Google Sign-In section above)

She'll get a stable public URL she can open from any device, anywhere.

---

## Troubleshooting

**GPU not being used:**
```powershell
docker exec ollama ollama ps
```
Should show your model running on GPU. If it says CPU, check NVIDIA Container Toolkit is installed correctly.

**Can't reach from another device on the network:**
- Make sure Windows Firewall allows inbound on port 3000
- Check with: `netstat -an | findstr "3000"`

**Open WebUI won't start:**
```powershell
docker logs open-webui
```

**Google sign-in not appearing:**
- Make sure `GOOGLE_CLIENT_ID` and `GOOGLE_CLIENT_SECRET` are set in `.env` (no quotes, no spaces)
- Restart after editing `.env`: `docker compose up -d`
