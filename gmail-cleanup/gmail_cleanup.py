#!/usr/bin/env python3
"""
Gmail Cleanup Script

Operations:
  suggest     — Scan inbox and suggest label names based on sender patterns
  delete_old  — Delete emails older than N days (default: 365)
  delete_promo— Delete promotional/newsletter emails
  label       — Apply labels and archive categorized inbox emails
  all         — Run delete_old + delete_promo + label (default)

Setup:
  1. Go to https://console.cloud.google.com/
  2. Create a project → Enable "Gmail API"
  3. Go to APIs & Services → Credentials → Create OAuth 2.0 Client ID (Desktop app)
  4. Download credentials.json to this directory
  5. pip install -r requirements.txt
  6. python gmail_cleanup.py --operation suggest   # analyse inbox, suggest labels
  7. python gmail_cleanup.py                        # dry-run all cleanup ops
  8. python gmail_cleanup.py --execute              # apply changes
"""

import os
import re
import sys
import time
import argparse
import logging
from collections import Counter
from datetime import datetime, timedelta

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

SCOPES = ["https://www.googleapis.com/auth/gmail.modify"]
TOKEN_FILE = os.path.join(os.path.dirname(__file__), "token.json")
CREDENTIALS_FILE = os.path.join(os.path.dirname(__file__), "credentials.json")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def execute_with_retry(request, max_attempts: int = 5):
    """Execute a Gmail API request with exponential backoff on 429/5xx errors."""
    for attempt in range(max_attempts):
        try:
            return request.execute()
        except HttpError as exc:
            if exc.resp.status in (429, 500, 503) and attempt < max_attempts - 1:
                wait = 2 ** attempt  # 1s, 2s, 4s, 8s
                log.warning("HTTP %d — retrying in %ds ...", exc.resp.status, wait)
                time.sleep(wait)
            else:
                raise


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------

def authenticate():
    """OAuth2 flow — saves/reuses token.json."""
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                sys.exit(
                    f"\nMissing {CREDENTIALS_FILE}.\n"
                    "Download it from Google Cloud Console → APIs & Services → Credentials.\n"
                    "See the script header for full setup instructions."
                )
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w") as fh:
            fh.write(creds.to_json())
        os.chmod(TOKEN_FILE, 0o600)
    return build("gmail", "v1", credentials=creds)


# ---------------------------------------------------------------------------
# Domain → suggested label mapping
# Extend this dict to teach the script about your own senders.
# ---------------------------------------------------------------------------

DOMAIN_LABEL_MAP = {
    # Social networks
    "twitter.com": "Social/Twitter",
    "x.com": "Social/Twitter",
    "linkedin.com": "Social/LinkedIn",
    "facebook.com": "Social/Facebook",
    "instagram.com": "Social/Instagram",
    "reddit.com": "Social/Reddit",
    "tiktok.com": "Social/TikTok",
    "pinterest.com": "Social/Pinterest",
    "discord.com": "Social/Discord",
    # Finance / banking
    "paypal.com": "Finance/PayPal",
    "stripe.com": "Finance",
    "chase.com": "Finance/Chase",
    "bankofamerica.com": "Finance/BofA",
    "wellsfargo.com": "Finance/WellsFargo",
    "citibank.com": "Finance/Citi",
    "americanexpress.com": "Finance/Amex",
    "capitalone.com": "Finance/CapitalOne",
    "revolut.com": "Finance/Revolut",
    "wise.com": "Finance/Wise",
    # Shopping / receipts
    "amazon.com": "Receipts/Amazon",
    "amazon.co.uk": "Receipts/Amazon",
    "amazon.de": "Receipts/Amazon",
    "ebay.com": "Receipts/eBay",
    "etsy.com": "Receipts/Etsy",
    "walmart.com": "Receipts/Walmart",
    "target.com": "Receipts/Target",
    "shopify.com": "Receipts",
    "apple.com": "Receipts/Apple",
    # Dev / work tools
    "github.com": "Notifications/GitHub",
    "atlassian.com": "Notifications/Jira",
    "atlassian.net": "Notifications/Jira",
    "slack.com": "Notifications/Slack",
    "notion.so": "Notifications/Notion",
    "figma.com": "Notifications/Figma",
    "gitlab.com": "Notifications/GitLab",
    "circleci.com": "Notifications/CI",
    "travis-ci.com": "Notifications/CI",
    "pagerduty.com": "Notifications/PagerDuty",
    "datadoghq.com": "Notifications/Datadog",
    # Email marketing platforms (generic newsletters)
    "mailchimp.com": "Newsletters",
    "sendgrid.net": "Newsletters",
    "constantcontact.com": "Newsletters",
    "klaviyo.com": "Newsletters",
    "substack.com": "Newsletters",
    "beehiiv.com": "Newsletters",
    "campaign-archive.com": "Newsletters",
    "mandrillapp.com": "Newsletters",
    # Travel
    "airbnb.com": "Travel/Airbnb",
    "booking.com": "Travel",
    "expedia.com": "Travel",
    "hotels.com": "Travel",
    "uber.com": "Travel/Uber",
    "lyft.com": "Travel/Lyft",
    "ryanair.com": "Travel",
    "easyjet.com": "Travel",
    "klm.com": "Travel",
    # Cloud / infra
    "aws.amazon.com": "Notifications/AWS",
    "google.com": "Notifications/Google",
    "azure.com": "Notifications/Azure",
    "digitalocean.com": "Notifications/DigitalOcean",
}


# ---------------------------------------------------------------------------
# Gmail helpers
# ---------------------------------------------------------------------------

def list_messages(service, query: str, limit: int = 0) -> list:
    """Return message IDs matching the Gmail search query (up to `limit`, 0 = all)."""
    ids = []
    kwargs = {"userId": "me", "q": query, "maxResults": 500}
    while True:
        resp = execute_with_retry(service.users().messages().list(**kwargs))
        for msg in resp.get("messages", []):
            ids.append(msg["id"])
        if limit and len(ids) >= limit:
            return ids[:limit]
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
        kwargs["pageToken"] = page_token
    return ids


def batch_get_senders(service, message_ids: list) -> list:
    """
    Fetch the From header for each message ID using Gmail batch HTTP requests.
    Returns a list of raw From strings. Processes 100 messages per HTTP batch.
    """
    senders = []

    for chunk_start in range(0, len(message_ids), 100):
        chunk = message_ids[chunk_start: chunk_start + 100]
        chunk_results = {}

        def make_callback(msg_id):
            def callback(request_id, response, exception):
                if exception is not None:
                    log.warning("Batch fetch failed for message %s: %s", msg_id, exception)
                    return
                if response:
                    headers = response.get("payload", {}).get("headers", [])
                    for h in headers:
                        if h["name"].lower() == "from":
                            chunk_results[msg_id] = h["value"]
                            return
                    log.debug("No From header for message %s", msg_id)
            return callback

        batch = service.new_batch_http_request()
        for msg_id in chunk:
            batch.add(
                service.users().messages().get(
                    userId="me",
                    id=msg_id,
                    format="metadata",
                    metadataHeaders=["From"],
                ),
                callback=make_callback(msg_id),
            )
        execute_with_retry(batch)
        senders.extend(chunk_results.get(mid, "") for mid in chunk)
        log.info(
            "  Fetched metadata: %d / %d",
            min(chunk_start + 100, len(message_ids)),
            len(message_ids),
        )

    return senders


def batch_delete(service, message_ids: list, dry_run: bool) -> int:
    """Delete messages in chunks of 1000 (Gmail API limit). Returns count."""
    if not message_ids:
        return 0
    if dry_run:
        log.info("  [DRY-RUN] Would delete %d messages", len(message_ids))
        return len(message_ids)
    total = 0
    for i in range(0, len(message_ids), 1000):
        chunk = message_ids[i: i + 1000]
        execute_with_retry(service.users().messages().batchDelete(
            userId="me", body={"ids": chunk}
        ))
        total += len(chunk)
        log.info("  Deleted %d / %d messages ...", total, len(message_ids))
    return total


_label_cache: dict = {}  # name.lower() → label_id, populated once per run


def ensure_label(service, name: str) -> str:
    """Return the label ID for `name`, creating it if needed. Caches the label list."""
    global _label_cache
    if not _label_cache:
        resp = execute_with_retry(service.users().labels().list(userId="me"))
        for lbl in resp.get("labels", []):
            _label_cache[lbl["name"].lower()] = lbl["id"]
    if name.lower() in _label_cache:
        return _label_cache[name.lower()]
    created = execute_with_retry(service.users().labels().create(
        userId="me",
        body={
            "name": name,
            "labelListVisibility": "labelShow",
            "messageListVisibility": "show",
        },
    ))
    log.info("  Created label: %s", name)
    _label_cache[name.lower()] = created["id"]
    return created["id"]


def apply_label_and_archive(service, message_ids: list, label_id: str, dry_run: bool) -> int:
    """Add `label_id` and remove INBOX in chunks of 1000. Returns count."""
    if not message_ids:
        return 0
    if dry_run:
        log.info("  [DRY-RUN] Would label+archive %d messages", len(message_ids))
        return len(message_ids)
    total = 0
    for i in range(0, len(message_ids), 1000):
        chunk = message_ids[i: i + 1000]
        execute_with_retry(service.users().messages().batchModify(
            userId="me",
            body={
                "ids": chunk,
                "addLabelIds": [label_id],
                "removeLabelIds": ["INBOX"],
            },
        ))
        total += len(chunk)
    return total


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------

def log_dry_run_sample(service, message_ids: list, n: int = 5) -> None:
    """Log From/Subject for the first N messages so users can verify before --execute."""
    log.info("  Sample (first %d):", min(n, len(message_ids)))
    for msg_id in message_ids[:n]:
        try:
            resp = execute_with_retry(service.users().messages().get(
                userId="me", id=msg_id, format="metadata",
                metadataHeaders=["From", "Subject"],
            ))
            hdrs = {h["name"].lower(): h["value"]
                    for h in resp.get("payload", {}).get("headers", [])}
            log.info("    from=%-40s  subject=%s",
                     hdrs.get("from", "(none)")[:40],
                     hdrs.get("subject", "(none)")[:80])
        except HttpError:
            pass


# Appended to every delete query to protect emails the user has deliberately kept.
SAFE_EXCLUDE = "-is:starred -is:important -label:drafts"


def delete_old_emails(service, days: int, dry_run: bool) -> int:
    """Delete all emails older than `days` days (skips starred/important/drafts)."""
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y/%m/%d")
    query = f"before:{cutoff} {SAFE_EXCLUDE}"
    log.info("Querying emails older than %d days (before %s)...", days, cutoff)
    ids = list_messages(service, query)
    log.info("Found %d old emails", len(ids))
    if dry_run and ids:
        log_dry_run_sample(service, ids)
    return batch_delete(service, ids, dry_run)


# Gmail native categories are precise; free-text "unsubscribe" was too broad
# (it matched bank/service emails saying "manage your account preferences").
PROMO_QUERIES = [
    "category:promotions",
    "category:updates",
    "label:^smartlabel_newsletter",
    "label:^smartlabel_notification",
]


def delete_promotional_emails(service, dry_run: bool) -> int:
    """Delete promotional, newsletter, and bulk marketing emails (skips starred/important/drafts)."""
    seen: set = set()
    for q in PROMO_QUERIES:
        log.info("Querying: %s", q)
        ids = list_messages(service, f"{q} {SAFE_EXCLUDE}")
        log.info("  → %d messages", len(ids))
        seen.update(ids)
    log.info("Total unique promotional emails: %d", len(seen))
    if dry_run and seen:
        log_dry_run_sample(service, list(seen))
    return batch_delete(service, list(seen), dry_run)


# Rules: label name → Gmail search query (only looks in INBOX)
LABEL_RULES = [
    {
        "label": "Receipts",
        "query": (
            "in:inbox "
            '(subject:"receipt" OR subject:"invoice" OR subject:"order confirmation" '
            'OR subject:"your order" OR subject:"payment confirmation" '
            'OR subject:"purchase confirmation" OR subject:"order shipped")'
        ),
    },
    {
        "label": "Finance",
        "query": (
            "in:inbox "
            "(from:paypal.com OR from:amazon.com OR from:stripe.com "
            'OR subject:"bank statement" OR subject:"account statement" '
            'OR subject:"wire transfer" OR subject:"direct deposit")'
        ),
    },
    {
        "label": "Notifications/GitHub",
        "query": "in:inbox from:github.com",
    },
    {
        "label": "Notifications/Jira",
        "query": "in:inbox (from:atlassian.com OR from:atlassian.net)",
    },
    {
        "label": "Social",
        "query": (
            "in:inbox "
            "(from:twitter.com OR from:linkedin.com OR from:facebook.com "
            "OR from:instagram.com OR from:reddit.com OR from:tiktok.com)"
        ),
    },
]


def suggest_labels(service, max_emails: int = 2000, min_count: int = 3) -> None:
    """
    Scan inbox senders and suggest label names based on DOMAIN_LABEL_MAP.
    Prints two tables:
      1. Known domains  — mapped to a suggested label
      2. Unknown domains — seen >= min_count times; you can add them to DOMAIN_LABEL_MAP
    """
    log.info("Fetching up to %d inbox message IDs...", max_emails)
    ids = list_messages(service, "in:inbox", limit=max_emails)
    log.info("Fetched %d message IDs. Retrieving sender metadata...", len(ids))

    raw_senders = batch_get_senders(service, ids)

    domain_counts: Counter = Counter()
    sender_counts: Counter = Counter()  # full address for unknown domains

    for raw in raw_senders:
        if not raw:
            continue
        match = re.search(r"<([^>]+)>", raw)
        sender_email = (match.group(1) if match else raw.strip()).lower()
        domain = sender_email.split("@", 1)[1] if "@" in sender_email else ""
        if domain:
            domain_counts[domain] += 1
        sender_counts[sender_email] += 1

    # --- Table 1: known domains with suggested labels ---
    known_rows = []
    seen_domains = set()
    for domain, count in domain_counts.most_common():
        label = DOMAIN_LABEL_MAP.get(domain)
        if label:
            known_rows.append((count, label, domain))
            seen_domains.add(domain)

    # --- Table 2: unknown domains appearing >= min_count times ---
    unknown_rows = [
        (count, domain)
        for domain, count in domain_counts.most_common()
        if domain not in seen_domains and count >= min_count
    ]

    print("\n" + "=" * 70)
    print(" LABEL SUGGESTIONS  (based on inbox analysis)")
    print("=" * 70)

    if known_rows:
        print(f"\n{'Count':>6}  {'Suggested Label':<30}  Sender Domain")
        print(f"{'------':>6}  {'-' * 30}  {'-' * 30}")
        for count, label, domain in sorted(known_rows, reverse=True):
            print(f"{count:>6}  {label:<30}  {domain}")
    else:
        print("\n  (No known senders found in inbox)")

    if unknown_rows:
        print(f"\n--- Unknown domains appearing {min_count}+ times (not in DOMAIN_LABEL_MAP) ---")
        print(f"{'Count':>6}  Domain")
        print(f"{'------':>6}  {'-' * 40}")
        for count, domain in unknown_rows[:30]:  # cap at 30
            print(f"{count:>6}  {domain}")
        print(
            "\n  Tip: add these to DOMAIN_LABEL_MAP in the script to auto-label them."
        )

    print("\n--- Next steps ---")
    print("  1. Review the suggestions above and customise LABEL_RULES / DOMAIN_LABEL_MAP")
    print("  2. Run:  python gmail_cleanup.py                  (dry-run all ops)")
    print("  3. Run:  python gmail_cleanup.py --execute        (apply changes)")
    print("=" * 70 + "\n")


def apply_labels(service, dry_run: bool) -> int:
    """Apply labels and archive matching inbox emails. Returns total count."""
    total = 0
    for rule in LABEL_RULES:
        log.info("Rule [%s]", rule["label"])
        log.info("  Query: %s", rule["query"])
        ids = list_messages(service, rule["query"])
        if not ids:
            log.info("  → 0 messages, skipping")
            continue
        log.info("  → %d messages found", len(ids))
        if dry_run:
            label_id = "DRY_RUN_ID"
        else:
            label_id = ensure_label(service, rule["label"])
        count = apply_label_and_archive(service, ids, label_id, dry_run)
        total += count
    return total


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Clean up Gmail: suggest labels, delete old/promo emails, apply labels.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python gmail_cleanup.py --operation suggest      # analyse inbox, suggest labels\n"
            "  python gmail_cleanup.py                          # dry-run all cleanup ops\n"
            "  python gmail_cleanup.py --execute                # apply all changes\n"
            "  python gmail_cleanup.py --days 180               # use 6-month cutoff\n"
            "  python gmail_cleanup.py --operation delete_old   # only delete old emails\n"
        ),
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Apply changes (default is dry-run — no changes made)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=365,
        help="Delete emails older than N days (default: 365)",
    )
    parser.add_argument(
        "--operation",
        choices=["all", "suggest", "delete_old", "delete_promo", "label"],
        default="all",
        help="Which operation to run (default: all)",
    )
    parser.add_argument(
        "--max-emails",
        type=int,
        default=2000,
        metavar="N",
        help="Max inbox emails to scan when using --operation suggest (default: 2000)",
    )
    args = parser.parse_args()

    # 'suggest' is read-only — skip dry-run/execute logic
    if args.operation == "suggest":
        try:
            service = authenticate()
        except Exception as exc:
            sys.exit(f"Authentication failed: {exc}")
        suggest_labels(service, max_emails=args.max_emails)
        return

    dry_run = not args.execute

    log.info("=" * 60)
    if dry_run:
        log.info("DRY-RUN MODE — no changes will be made")
        log.info("Run with --execute to apply changes")
    else:
        log.warning("EXECUTE MODE — changes will be made to your Gmail!")
        confirm = input("Type 'yes' to continue: ").strip().lower()
        if confirm != "yes":
            log.info("Aborted.")
            return
    log.info("=" * 60)

    try:
        service = authenticate()
    except Exception as exc:
        sys.exit(f"Authentication failed: {exc}")

    stats = {}

    if args.operation in ("all", "delete_old"):
        log.info("\n--- [1/3] Delete old emails (older than %d days) ---", args.days)
        stats["deleted_old"] = delete_old_emails(service, args.days, dry_run)

    if args.operation in ("all", "delete_promo"):
        log.info("\n--- [2/3] Delete promotional/newsletter emails ---")
        stats["deleted_promo"] = delete_promotional_emails(service, dry_run)

    if args.operation in ("all", "label"):
        log.info("\n--- [3/3] Apply labels and archive ---")
        stats["labeled"] = apply_labels(service, dry_run)

    log.info("\n=== Summary ===")
    for key, val in stats.items():
        action = "Would affect" if dry_run else "Affected"
        log.info("  %-20s %s %d emails", key, action, val)

    if dry_run:
        log.info("\nRun with --execute to apply these changes.")


if __name__ == "__main__":
    main()
