# Safety Buddy

A browser extension that keeps non-technical users — kids and senior citizens — safer online. It quietly checks every link before it opens, warns about dangerous sites in plain language, and sends an immediate message to a trusted family member when something risky happens.

---

## What it does

| Situation | What happens |
|---|---|
| User clicks a link to an unfamiliar website | Extension pauses the click, checks the URL, lets them through if it's safe |
| URL is in Google's threat database | Friendly warning page appears — large text, big "go back" button |
| URL looks suspicious (Claude AI decides) | Same friendly warning page |
| User clicks "continue anyway" on a warning | Guardian receives an email alert |
| User visits a gift card / wire transfer / crypto page | Warning page + guardian gets an urgent SMS immediately |

Fails open: if the backend is unreachable, all links navigate normally. Users are never blocked by a technical failure.

---

## Privacy

Safety Buddy tracks **website visits and destinations only**. It never reads:

- Keystrokes or typed text of any kind
- Form fields, passwords, or search terms
- Message or email content (Gmail, WhatsApp, Facebook, etc.)
- Clipboard contents
- Page content beyond the URL and page title

The content script reads only `anchor.href` (where a link goes) and `window.location.href` (what page you landed on). No keystroke, input, or form listeners are attached anywhere.

---

## Plans and pricing

| | Free | Personal | Family |
|---|---|---|---|
| URL safety checking (AI + Safe Browsing) | ✓ | ✓ | ✓ |
| 1 guardian slot | ✓ | ✓ | ✓ |
| Email alerts when a warning is triggered | — | ✓ | ✓ |
| SMS alerts on gift card / money transfer pages | — | ✓ | ✓ |
| Up to 5 guardians | — | — | ✓ |
| Annual price | — | $9.99/yr | $19.99/yr |
| Lifetime price | — | $24.99 once | $49.99 once |

Lifetime plans include 2 years of Claude AI checking. After 2 years they fall back to Google Safe Browsing only — you can renew AI checking for $9.99 at any time.

---

## How to set it up — from scratch

This takes about 45–60 minutes the first time. Each section below covers one piece.

---

### Step 1 — Get your API keys (15 min)

You'll collect four things before touching any code.

#### Anthropic API key (Claude AI)
1. Go to [console.anthropic.com](https://console.anthropic.com) and create an account
2. Go to **API Keys** → **Create Key**
3. Copy it — you'll paste it as `ANTHROPIC_API_KEY` later

#### Google Safe Browsing key (free)
1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Create a new project (or use an existing one)
3. Search for **Safe Browsing API** → Enable it
4. Go to **Credentials** → **Create Credentials** → **API Key**
5. Copy it — you'll paste it as `GOOGLE_SAFE_BROWSING_API_KEY` later

#### Gmail App Password (for email alerts)
You need this so the backend can send emails without using your real password.

1. Your Gmail account must have **2-Step Verification** turned on — check at [myaccount.google.com/security](https://myaccount.google.com/security)
2. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
3. Under "Select app" choose **Mail**, under "Select device" choose **Other** and type "Safety Buddy"
4. Click **Generate** — copy the 16-character password (no spaces)
5. You'll use this as `SMTP_PASS` with your Gmail address as `SMTP_USER`

#### Twilio SMS (for urgent gift card / scam alerts)
Free trial gives ~$15 credit — enough to test thoroughly.

1. Sign up at [twilio.com](https://www.twilio.com) — no credit card required for trial
2. After verifying your phone, go to the Console dashboard
3. Copy your **Account SID** and **Auth Token** from the top of the page
4. Go to **Phone Numbers** → **Manage** → **Buy a number** → choose any US number (free on trial)
5. Copy the phone number (format: `+15551234567`)
6. **Trial account limitation:** you can only send SMS to phone numbers you've verified. Go to **Verified Caller IDs** and add the guardian's phone number.

---

### Step 2 — Deploy the backend to Railway (15 min)

Railway is the easiest way to host the backend so your family member doesn't need to run anything on their computer.

1. Create a free account at [railway.app](https://railway.app)
2. Click **New Project** → **Deploy from GitHub repo**
3. Connect your GitHub account and select this repository (`scripties`)
4. Railway will detect the `Procfile` in `security-buddy/backend/` and start building

**Set the root directory:**
- In your Railway service settings, set **Root Directory** to `security-buddy/backend`

**Add environment variables:**
In Railway → your service → **Variables**, add each of these:

```
ANTHROPIC_API_KEY          = (your key from Step 1)
GOOGLE_SAFE_BROWSING_API_KEY = (your key from Step 1)

SMTP_HOST                  = smtp.gmail.com
SMTP_PORT                  = 587
SMTP_USER                  = your-gmail@gmail.com
SMTP_PASS                  = (16-char App Password from Step 1)
FROM_EMAIL                 = your-gmail@gmail.com

TWILIO_ACCOUNT_SID         = (from Step 1)
TWILIO_AUTH_TOKEN          = (from Step 1)
TWILIO_FROM_NUMBER         = +15551234567

ALLOWED_ORIGINS            = *
APP_URL                    = https://your-app.up.railway.app
```

Leave `DATABASE_URL` blank — Railway will use SQLite by default. For production with many users, add a Railway PostgreSQL service and paste its URL here.

**Get your Railway URL:**
After the first successful deploy, Railway gives you a URL like `https://your-app.up.railway.app`. Copy it — you'll need it in Step 4.

**Verify it's running:**
Open `https://your-app.up.railway.app/health` in a browser — you should see `{"status":"ok"}`.

---

### Step 3 — Set up Paddle billing (15 min)

Paddle acts as the Merchant of Record, meaning it handles all sales tax (VAT, GST) globally so you don't have to register in each country.

#### Create a Paddle account
1. Sign up at [paddle.com](https://www.paddle.com)
2. You start in **sandbox mode** automatically — safe for testing, no real money

#### Create your five products

In the Paddle dashboard → **Catalog** → **Products**, create five products:

| Product name | Price | Type |
|---|---|---|
| Safety Buddy Personal Annual | $9.99 | Recurring — yearly |
| Safety Buddy Family Annual | $19.99 | Recurring — yearly |
| Safety Buddy Personal Lifetime | $24.99 | One-time |
| Safety Buddy Family Lifetime | $49.99 | One-time |
| Safety Buddy API Renewal | $9.99 | One-time |

For each product, Paddle creates a **Price ID** that starts with `pri_`. Copy all five.

#### Set up the webhook
1. Paddle dashboard → **Developer Tools** → **Notifications** → **New Destination**
2. URL: `https://your-app.up.railway.app/billing/webhook`
3. Events to subscribe to:
   - `transaction.completed`
   - `subscription.created`
   - `subscription.updated`
   - `subscription.canceled`
   - `transaction.payment_failed`
4. Save — Paddle shows you a **webhook secret key**. Copy it.

#### Add Paddle variables to Railway

Back in Railway → Variables, add:

```
PADDLE_API_KEY                    = (from Paddle → Developer Tools → Authentication)
PADDLE_WEBHOOK_SECRET             = (the secret from the webhook you just created)
PADDLE_SANDBOX                    = true
PADDLE_PERSONAL_ANNUAL_PRICE_ID   = pri_...
PADDLE_FAMILY_ANNUAL_PRICE_ID     = pri_...
PADDLE_PERSONAL_LIFETIME_PRICE_ID = pri_...
PADDLE_FAMILY_LIFETIME_PRICE_ID   = pri_...
PADDLE_API_RENEWAL_PRICE_ID       = pri_...
```

When you're ready to take real payments, create the same products in Paddle's **live** environment, update the price IDs, and set `PADDLE_SANDBOX=false`.

---

### Step 4 — Load the extension (5 min)

#### Chrome / Brave
1. Generate the icon files first (one-time, requires Python):
   ```bash
   cd security-buddy/extension/icons
   python generate_icons.py
   ```
2. Open `chrome://extensions`
3. Turn on **Developer mode** (toggle top-right)
4. Click **Load unpacked**
5. Select the `security-buddy/extension/` folder
6. The Safety Buddy shield icon appears in your toolbar

#### Edge
Edge is Chromium-based and runs the extension identically to Chrome — all the same APIs are supported.

1. Generate icons (same as above — skip if already done):
   ```bash
   cd security-buddy/extension/icons
   python generate_icons.py
   ```
2. Open `edge://extensions` (not `chrome://extensions` — Edge has its own page)
3. Turn on **Developer mode** (toggle bottom-left)
4. Click **Load unpacked**
5. Select the `security-buddy/extension/` folder

#### Firefox
1. Open `about:debugging`
2. Click **This Firefox** → **Load Temporary Add-on**
3. Select `security-buddy/extension/manifest.json`

> **Distributing to family members:** Chrome Web Store (one-time $5 developer fee) or Firefox Add-ons are the cleanest options for non-technical users. Until then, you can sideload it on their computer by following the Chrome steps above.

---

### Step 5 — Point the extension at your backend (2 min)

By default the extension talks to `https://api.safetybuddy.app`. To use your Railway URL instead, open the browser's developer console on the extension popup page and run:

```js
chrome.storage.local.set({ backendUrl: 'https://your-app.up.railway.app' })
```

Or: edit `DEFAULT_BACKEND` in `background.js`, `content.js`, and `popup.js` to your Railway URL before loading the extension.

---

### Step 6 — Create an account and add a guardian

1. Click the Safety Buddy shield in your toolbar
2. Click **Don't have an account? Create one**
3. Enter your name, email, and a password (8+ characters)
4. Click **Create Account** — you're now signed in
5. Click **+ Add guardian**
6. Enter the family member's name, email, and phone number
7. Click **Add**

The free plan supports 1 guardian. Upgrade to Personal or Family from the plan picker in the popup.

---

## Testing everything works

```bash
# Health check
curl https://your-app.up.railway.app/health

# URL check — should return safe=false
curl -X POST https://your-app.up.railway.app/check-url \
  -H "Content-Type: application/json" \
  -d '{"url": "http://malware.testing.google.test/testing/malware/", "page_title": "Test"}'
```

In the browser:

| Test | Steps | Expected result |
|---|---|---|
| URL warning | Navigate to `http://testsafebrowsing.appspot.com/s/malware.html` | Warning page appears |
| Continue alert | Click "I understand — continue anyway" on a warning | Guardian receives email |
| Gift card warning | Navigate to `amazon.com/gift-cards` | Warning page appears + SMS sent |
| Fail-open | Stop the backend, click any external link | Link navigates normally |

---

## Giving it to a family member

Once the extension is installed on their computer:

1. Sign them in to their own account (or a shared family account)
2. Add yourself as their guardian with your email and phone
3. Show them what the warning page looks like — run the Safe Browsing test URL above so they're not surprised
4. Explain the green button ("go back to safety") is always the right choice

The extension is completely silent when everything is safe — they won't notice it unless something goes wrong.

---

## Running locally (development)

```bash
cd security-buddy/backend
cp .env.example .env
# Fill in at minimum ANTHROPIC_API_KEY
pip install -r requirements.txt
uvicorn main:app --reload
```

Then set `backendUrl` in the extension to `http://localhost:8000` (see Step 5).

---

## Architecture

```
Browser Extension (MV3)             Python Backend (FastAPI + Railway)
───────────────────────             ──────────────────────────────────
content.js                          main.py
  intercepts <a> clicks        ───► POST /check-url
  detects financial pages             check_url.py
                                        1. Google Safe Browsing API
background.js                           2. Claude Haiku (if inconclusive)
  relays CHECK_URL             ◄───  verdict: {safe, reason, risk_level}
  relays FINANCIAL_DANGER_PAGE
  redirects tab to warning.html
  calls /notify-urgent         ───► POST /notify-urgent
                                      notify.py → Twilio SMS
warning.html + warning.js
  friendly warning UI
  "continue" → /notify         ───► POST /notify
                                      notify.py → SMTP email
popup.html + popup.js
  register / sign in
  guardian management
  plan picker → /billing/checkout ► Paddle hosted checkout
```

---

## File structure

```
security-buddy/
├── README.md
├── extension/
│   ├── manifest.json          MV3, Chrome + Firefox
│   ├── background.js          Service worker: URL checks, financial danger alerts
│   ├── content.js             Intercepts clicks, detects gift card / scam pages
│   ├── popup.html             Auth + guardian management + plan picker
│   ├── popup.js
│   ├── warning.html           Friendly warning page (URL safety)
│   ├── warning.js
│   ├── utils.js               Shared escHtml helper
│   └── icons/
│       ├── generate_icons.py  Generates PNG icons (stdlib only, no Pillow needed)
│       ├── buddy-16.png
│       ├── buddy-48.png
│       └── buddy-128.png
└── backend/
    ├── main.py                FastAPI app, all routes
    ├── auth.py                API key auth (argon2 password hashing)
    ├── billing.py             Paddle Billing REST API
    ├── check_url.py           Safe Browsing + Claude two-stage check
    ├── database.py            SQLAlchemy async engine (SQLite dev / PostgreSQL prod)
    ├── models.py              User, Guardian, WarningEvent ORM models
    ├── notify.py              SMTP email + Twilio SMS
    ├── requirements.txt
    ├── .env.example           All environment variables documented
    ├── Procfile               Railway / Heroku process definition
    ├── railway.toml           Railway build config
    └── .python-version        3.12
```

---

## Common issues

**Extension not loading (Chrome)**
Make sure you selected the `extension/` folder, not the whole `security-buddy/` folder. The `manifest.json` must be at the root of the selected folder.

**"Billing not configured" error**
`PADDLE_API_KEY` is missing or empty in your Railway environment variables.

**Emails not sending**
Check that `SMTP_USER` and `SMTP_PASS` are set. The `SMTP_PASS` must be a Gmail App Password (16 characters, no spaces), not your Gmail account password. 2-Step Verification must be enabled on the Gmail account.

**SMS not sending (Twilio trial)**
Twilio trial accounts can only send to verified phone numbers. Go to your Twilio console → **Verified Caller IDs** and add the guardian's number.

**Backend crashes on startup**
Run `pip install -r requirements.txt` again — a dependency may be missing or the wrong version.

**"The extension cannot read this page" on some sites**
Chrome restricts content scripts on `chrome://` pages, the Web Store, and a few other internal pages. This is normal and expected.
