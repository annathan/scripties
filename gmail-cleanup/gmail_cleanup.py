#!/usr/bin/env python3
"""
Gmail Cleanup Script

Operations:
  1. Delete emails older than N days (default: 365)
  2. Delete promotional/newsletter emails
  3. Apply labels and archive categorized inbox emails

Setup:
  1. Go to https://console.cloud.google.com/
  2. Create a project → Enable "Gmail API"
  3. Go to APIs & Services → Credentials → Create OAuth 2.0 Client ID (Desktop app)
  4. Download credentials.json to this directory
  5. pip install -r requirements.txt
  6. python gmail_cleanup.py          # dry-run preview
  7. python gmail_cleanup.py --execute  # apply changes
"""

import os
import sys
import argparse
import logging
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
    return build("gmail", "v1", credentials=creds)


# ---------------------------------------------------------------------------
# Gmail helpers
# ---------------------------------------------------------------------------

def list_messages(service, query: str) -> list:
    """Return all message IDs matching the Gmail search query."""
    ids = []
    kwargs = {"userId": "me", "q": query, "maxResults": 500}
    while True:
        resp = service.users().messages().list(**kwargs).execute()
        for msg in resp.get("messages", []):
            ids.append(msg["id"])
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
        kwargs["pageToken"] = page_token
    return ids


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
        service.users().messages().batchDelete(
            userId="me", body={"ids": chunk}
        ).execute()
        total += len(chunk)
        log.info("  Deleted %d / %d messages ...", total, len(message_ids))
    return total


def ensure_label(service, name: str) -> str:
    """Return the label ID for `name`, creating it if it doesn't exist."""
    resp = service.users().labels().list(userId="me").execute()
    for lbl in resp.get("labels", []):
        if lbl["name"].lower() == name.lower():
            return lbl["id"]
    created = service.users().labels().create(
        userId="me",
        body={
            "name": name,
            "labelListVisibility": "labelShow",
            "messageListVisibility": "show",
        },
    ).execute()
    log.info("  Created label: %s", name)
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
        service.users().messages().batchModify(
            userId="me",
            body={
                "ids": chunk,
                "addLabelIds": [label_id],
                "removeLabelIds": ["INBOX"],
            },
        ).execute()
        total += len(chunk)
    return total


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------

def delete_old_emails(service, days: int, dry_run: bool) -> int:
    """Delete all emails older than `days` days."""
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y/%m/%d")
    query = f"before:{cutoff}"
    log.info("Querying emails older than %d days (before %s)...", days, cutoff)
    ids = list_messages(service, query)
    log.info("Found %d old emails", len(ids))
    return batch_delete(service, ids, dry_run)


# Queries that reliably catch promotional/newsletter emails in Gmail
PROMO_QUERIES = [
    "category:promotions",
    "category:updates",
    "label:^smartlabel_newsletter",
    "label:^smartlabel_notification",
    '"unsubscribe" OR "opt out" OR "manage preferences"',
]


def delete_promotional_emails(service, dry_run: bool) -> int:
    """Delete promotional, newsletter, and bulk marketing emails."""
    seen: set = set()
    for q in PROMO_QUERIES:
        log.info("Querying: %s", q)
        ids = list_messages(service, q)
        log.info("  → %d messages", len(ids))
        seen.update(ids)
    log.info("Total unique promotional emails: %d", len(seen))
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
        "query": "in:inbox from:notifications@github.com",
    },
    {
        "label": "Notifications/Jira",
        "query": "in:inbox (from:jira OR from:atlassian.com OR from:atlassian.net)",
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
        description="Clean up Gmail: delete old/promo emails, apply labels.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python gmail_cleanup.py                        # dry-run all operations\n"
            "  python gmail_cleanup.py --execute              # apply all changes\n"
            "  python gmail_cleanup.py --days 180             # use 6-month cutoff\n"
            "  python gmail_cleanup.py --operation delete_old # only delete old emails\n"
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
        choices=["all", "delete_old", "delete_promo", "label"],
        default="all",
        help="Which operation to run (default: all)",
    )
    args = parser.parse_args()

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
