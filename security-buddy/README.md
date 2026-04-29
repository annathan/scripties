# Safety Buddy

A browser extension that keeps non-technical users — kids and senior citizens — safer online. It intercepts outbound link clicks, checks the destination against Google Safe Browsing and Claude AI, shows a friendly warning if something looks risky, and immediately notifies a guardian by email or SMS.

---

## What it does

| Situation | What happens |
|---|---|
| User clicks a link to an unfamiliar website | Extension pauses the click, checks the URL, lets them through if it's safe |
| URL is flagged by Google Safe Browsing | Friendly warning page appears instead |
| URL looks suspicious (Claude decides) | Friendly warning page appears instead |
| User clicks "continue anyway" on a warning | Guardian receives an email |
| User navigates to a gift card / wire transfer / crypto page | Warning page appears immediately + guardian receives an urgent SMS |

---

## Privacy

Safety Buddy tracks **website visits and destinations only**. It never reads:
- Keystrokes or typed text
- Form fields, passwords, or search terms
- Message or email content (Gmail, WhatsApp, Facebook, etc.)
- Clipboard contents
- Page content beyond the URL and page title

The content script only reads `anchor.href` (where a link goes) and `window.location.href` (what page you're on). No keystroke, input, or form listeners are used anywhere.

---

## Setup

### 1. Backend

```bash
cd security-buddy/backend
cp .env.example .env
# Fill in your API keys in .env
pip install -r requirements.txt
uvicorn main:app --reload
```

The backend runs on `http://localhost:8000`. It needs to be running whenever the extension is in use.

**Required keys:**
- `ANTHROPIC_API_KEY` — from [console.anthropic.com](https://console.anthropic.com)

**Optional but recommended:**
- `GOOGLE_SAFE_BROWSING_API_KEY` — free at Google Cloud Console (Safe Browsing API)
- `SMTP_USER` / `SMTP_PASS` — Gmail with an [App Password](https://myaccount.google.com/apppasswords) (not your account password)
- `TWILIO_*` — free trial at [twilio.com](https://twilio.com) for SMS alerts

### 2. Extension

1. Open Chrome and go to `chrome://extensions`
2. Turn on **Developer mode** (toggle in the top right)
3. Click **Load unpacked**
4. Select the `security-buddy/extension/` folder

For Firefox: go to `about:debugging` → This Firefox → Load Temporary Add-on → select `manifest.json`.

### 3. Configure

Click the Safety Buddy shield icon in your browser toolbar and fill in:
- **Your name** (e.g. "Rose") — used in guardian messages
- **Family member's name** (e.g. "Sarah") — shown on warning pages
- **Family member's email** — where safety alerts go
- **Family member's phone** — for urgent SMS alerts on gift card / money transfer pages

Click **Save Settings**.

---

## Testing

```bash
# Test that the backend is running
curl http://localhost:8000/health

# Test URL check (should return safe=false for a known test URL)
curl -X POST http://localhost:8000/check-url \
  -H "Content-Type: application/json" \
  -d '{"url": "http://malware.testing.google.test/testing/malware/", "page_title": "Test"}'
```

In the browser:
- Navigate to `http://testsafebrowsing.appspot.com/s/malware.html` — should trigger a URL warning
- Navigate to `amazon.com/gift-cards` — should trigger a financial danger warning

---

## Architecture

```
Browser Extension (MV3)          Python Backend (FastAPI)
─────────────────────────        ────────────────────────
content.js                       main.py
  - intercepts <a> clicks   ───► /check-url
  - detects financial pages       check_url.py
                                    1. Google Safe Browsing API
background.js                       2. Claude Haiku (if inconclusive)
  - relays CHECK_URL        ◄───  verdict: {safe, reason, risk_level}
  - relays FINANCIAL_DANGER
  - redirects to warning.html
  - calls /notify-urgent    ───► /notify-urgent
                                   notify.py → Twilio SMS
warning.html + warning.js
  - friendly warning UI
  - "continue" → /notify   ───► /notify
                                   notify.py → SMTP email
popup.html + popup.js
  - guardian settings form
```

---

## File structure

```
security-buddy/
├── extension/
│   ├── manifest.json
│   ├── background.js
│   ├── content.js
│   ├── popup.html
│   ├── popup.js
│   ├── warning.html
│   ├── warning.js
│   └── icons/           (add buddy-16.png, buddy-48.png, buddy-128.png)
└── backend/
    ├── main.py
    ├── check_url.py
    ├── notify.py
    ├── requirements.txt
    └── .env.example
```

### Icons

The `icons/` folder is referenced by `manifest.json` but not included (placeholder). You can create simple shield icons and save them as `buddy-16.png`, `buddy-48.png`, `buddy-128.png`, or use any free icon generator.

---

## Limitations

- The backend must be running locally for the extension to work. If it's stopped, the extension fails open (lets all links through) so users are never blocked.
- SMS alerts require a Twilio account. The free trial gives enough credit to test.
- Gmail App Passwords require 2-factor authentication to be enabled on the Gmail account.
