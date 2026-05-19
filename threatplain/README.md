# ThreatPlain

Paste a URL, IP address, file hash, or raw email headers and get a plain-English explanation of what it is, what it does, and what you should do about it — no security background required.

---

## Getting your API keys

### 1. VirusTotal (free)
1. Go to <https://www.virustotal.com/gui/join-us> and create an account.
2. After signing in, click your avatar in the top-right corner → **API Key**.
3. Copy the key. Free tier: 4 requests/minute, 500/day.

### 2. AbuseIPDB (free)
1. Go to <https://www.abuseipdb.com/register> and create an account.
2. In the dashboard, go to **Account** → **API**.
3. Click **Create Key**, name it anything, copy the key.
4. Free tier: 1,000 checks/day.

### 3. URLScan.io (free)
1. Go to <https://urlscan.io/user/signup> and create an account.
2. In your profile, click **API Keys** → **Create new API key**.
3. Choose **Public** or **Unlisted** visibility (unlisted keeps your submissions private), copy the key.
4. Free tier: 100 scans/day.

### 4. Anthropic (Claude)
1. Go to <https://console.anthropic.com> and sign up.
2. Go to **API Keys** → **Create Key**, copy the key.
3. Free trial credits are available; after that, usage is pay-as-you-go (a typical analysis costs < $0.01).

---

## Running locally

```bash
# 1. Clone and enter the directory
cd threatplain

# 2. Create a virtual environment
python -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up your API keys
cp .env.example .env
# Open .env in any text editor and fill in your four API keys

# 5. Start the server
uvicorn main:app --reload --port 8000
```

Open <http://localhost:8000> in your browser.

---

## What gets sent where

| Input type    | APIs queried                          |
|---------------|---------------------------------------|
| IP address    | VirusTotal, AbuseIPDB                 |
| URL / domain  | VirusTotal, URLScan.io                |
| File hash     | VirusTotal                            |
| Email headers | VirusTotal + AbuseIPDB (per IP found) |

All results are passed to Claude (`claude-sonnet-4-20250514`) which synthesises them into the four-field threat card. Raw API responses are stored locally in `threatplain.db` (SQLite).

---

## Sharing results

Every result gets a unique short ID. After an analysis, the URL in your browser changes to `/result/<id>`. That URL is shareable — anyone with it can view the same result card.

Use the **Copy link** button on the result card to copy it to your clipboard.

---

## Notes

- URLScan.io scans can take 20–40 seconds; the app polls until they finish.
- If any API key is missing, that source is skipped and Claude works with whatever data is available.
- Results are stored indefinitely in `threatplain.db`. Delete the file to clear all history.
