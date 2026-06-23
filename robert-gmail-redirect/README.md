# Robert Gmail Redirect

A Google Apps Script that runs inside `andydunn5@gmail.com` to:

| Step | What it does |
|---|---|
| **Identify** | Finds emails from job boards, neighbourhood apps, and community sites that are clearly meant for someone else |
| **Archive** | Applies a `Robert` label and moves them out of the inbox automatically |
| **Detect** | Scans email content for Robert's real email address (footer patterns, unsubscribe headers, body scan) |
| **Forward** | Once you set `ROBERTS_EMAIL` in the config, forwards each email to Robert with a friendly note |
| **Digest** | Emails you a weekly report of what was caught and the top candidate addresses found |

## Background

Classic "email doppelganger" problem — someone called Robert in the US signed up for services using an old Gmail address that isn't his. This script handles the inbox noise while trying to find him so you can reconnect the emails.

## Prerequisites

- A Google account (sign into script.google.com **as `andydunn5@gmail.com`**, not your main account)
- About 5 minutes

## Setup — Option A: Script editor (no tools required)

1. Go to [script.google.com](https://script.google.com) and sign in as `andydunn5@gmail.com`
2. Click **New project**, name it `Robert Email Redirect`
3. In the editor, click the gear icon → **Project Settings** → tick **Show "appsscript.json" manifest file in editor**
4. Replace the contents of `Code.gs` with the contents of `Code.gs` from this repo
5. Click on `appsscript.json` in the file list and replace its contents with the contents of `appsscript.json` from this repo
6. Click **Save** (⌘S / Ctrl+S)
7. From the function dropdown at the top, select **`setup`** and click **Run**
8. Accept the OAuth permission prompt — it will ask for Gmail access
9. Done. Check Gmail for a new `Robert` label in the sidebar.

## Setup — Option B: clasp CLI

```bash
npm install -g @google/clasp
clasp login   # opens browser — sign in as andydunn5@gmail.com

cd robert-gmail-redirect
clasp create --type standalone --title "Robert Email Redirect"
# This creates .clasp.json — do NOT commit it (contains your personal scriptId)

clasp push
```

Then open the script URL that clasp prints, select **`setup`** from the function dropdown, and click **Run**.

Add `.clasp.json` to `.gitignore` if you haven't already.

## Config reference

All user-editable settings are at the top of `Code.gs` in the `CONFIG` object.

| Key | Default | Description |
|---|---|---|
| `ROBERTS_EMAIL` | `''` | Robert's real email once confirmed. Leave empty to skip forwarding. |
| `MY_EMAIL` | `andrew.nathan05@gmail.com` | Where the weekly digest is sent. |
| `LABEL_NAME` | `Robert` | Gmail label applied to all Robert emails. |
| `PROCESSED_LABEL_NAME` | `Robert/processed` | Internal idempotency marker. Don't rename this after first run. |
| `BATCH_SIZE` | `50` | Max threads per run. Keeps execution under GAS's 6-minute limit. |
| `DIGEST_DAY` | `1` (Monday) | Day of week for the digest (0=Sun … 6=Sat). |
| `DIGEST_HOUR` | `8` | Hour for the digest (24h, Eastern Time). |
| `SENDER_DOMAINS` | see Code.gs | List of sender domains whose emails belong to Robert. Add more as you see them. |
| `BODY_SIGNALS` | see Code.gs | Keywords used as a secondary confidence signal (not a gate). |
| `FORWARD_PREAMBLE` | see Code.gs | Intro text prepended when forwarding to Robert. |

## Finding Robert — how it works

On every run the script scans each email for Robert's real address in priority order:

1. **`List-Unsubscribe` header** — many services embed the subscribed account email here
2. **Footer patterns** — looks for `"this email was sent to [address]"`, `"delivered to: [address]"`, etc.
3. **Full body scan** — extracts all email addresses, filters out system/noreply addresses and the sender's own domain, then scores what's left (+10 if the local part contains "robert", +5 for "dunn", +3 for non-consumer domains like a work email)

Candidates are accumulated in Apps Script's `PropertiesService` across runs, so confidence builds up over time. The weekly digest ranks them by frequency.

## Enabling forwarding

Once the weekly digest shows a high-confidence candidate:

1. Open `Code.gs` in the script editor
2. Set `ROBERTS_EMAIL: 'robert.whatever@example.com'`
3. Click **Save**
4. Either wait for the next 6-hour trigger, or select **`processRobertEmails`** and click **Run** to forward immediately

The forwarded email includes a friendly note from you explaining the situation, so Robert knows what's going on.

## First-run historical cleanup

By default the search query includes `newer_than:30d` to avoid processing years of backlog on the first run. To do a full historical cleanup, open `Code.gs`, find `buildSearchQuery_()`, and remove the `newer_than:30d` clause. Then run `processRobertEmails()` manually a few times until the batch count drops to zero.

## Troubleshooting

**"You do not have permission"** — Make sure you're signed into script.google.com as `andydunn5@gmail.com`, not your main account. The OAuth consent is scoped to the signed-in account.

**Emails still appearing in inbox** — Run `processRobertEmails()` manually to catch up on the backlog. The 6-hour trigger only fires on schedule.

**Wrong emails being caught** — If you also use any of the listed services personally (e.g. LinkedIn), remove that domain from `SENDER_DOMAINS` in `Code.gs`.

**`Robert/processed` label missing** — Run `setup()` again. It creates labels idempotently.

**Digest not arriving** — Check your spam folder. Also verify `MY_EMAIL` in CONFIG is correct and run `sendWeeklyDigest()` manually to test.

**Quota errors** — The GAS free tier allows 6 hours of script runtime per day. The 6-hour trigger and ~50-thread batches are well within limits. If you hit quota, reduce `BATCH_SIZE` to 20.
