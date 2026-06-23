// ─── CONFIG ──────────────────────────────────────────────────────────────────
//
// Edit this section to customise behaviour. Everything else should just work.

const CONFIG = {
  // Once you've confirmed Robert's real email address, paste it here.
  // Leave empty to skip forwarding — emails will still be labelled and archived.
  ROBERTS_EMAIL: '',

  // Your real email — receives the weekly digest report.
  MY_EMAIL: 'andrew.nathan05@gmail.com',

  // Gmail label applied to all detected Robert emails (visible in sidebar).
  LABEL_NAME: 'Robert',

  // Internal marker label — keeps the script idempotent across runs.
  // Never shown prominently; nested under Robert/ in Gmail.
  PROCESSED_LABEL_NAME: 'Robert/processed',

  // Max threads to process per run (GAS hard-kills at 6 minutes).
  BATCH_SIZE: 50,

  // Weekly digest schedule. DIGEST_DAY: 0=Sun, 1=Mon … 6=Sat.
  DIGEST_DAY: 1,
  DIGEST_HOUR: 8, // 8am in the timeZone set in appsscript.json (America/New_York)

  // ── Sender domains whose emails are almost certainly meant for Robert. ──────
  // Matched against the From: header domain. Add more as you spot new senders.
  SENDER_DOMAINS: [
    // Job alert sites
    'indeed.com',
    'linkedin.com',
    'glassdoor.com',
    'ziprecruiter.com',
    'monster.com',
    'careerbuilder.com',
    'simplyhired.com',
    'dice.com',
    'theladders.com',
    'snagajob.com',
    'greenhouse.io',
    'lever.co',
    'myworkday.com',
    'wellfound.com',
    'smartrecruiters.com',
    'jobs2careers.com',
    // Neighbourhood / community
    'nextdoor.com',
    'ring.com',
    'signupgenius.com',
    'patch.com',
    'neighborsapp.com',
  ],

  // ── Body/subject keywords used as a secondary confidence signal. ────────────
  // Not a gate — used for logging and scoring only.
  BODY_SIGNALS: [
    'job alert',
    'new jobs for you',
    'jobs near you',
    'neighborhood alert',
    'your nextdoor digest',
    'jobs matching your',
    'application received',
    'interview invitation',
    'your weekly jobs',
    'recommended jobs',
  ],

  // ── Message prepended when forwarding to Robert. ────────────────────────────
  FORWARD_PREAMBLE:
    "Hi Robert,\n\n" +
    "My name is Andy — I own the email address andydunn5@gmail.com. " +
    "It looks like you may have accidentally signed up for some services " +
    "using my address.\n\n" +
    "I'm forwarding this email along so you don't miss it. " +
    "You'll want to update your email address on these services when you get a chance.\n\n" +
    "Hope this helps!\nAndy\n\n" +
    "────────────────────────────────────\n" +
    "Original message below:\n\n",
};

// ─── ENTRY POINTS ────────────────────────────────────────────────────────────

/**
 * Run this ONCE from the Apps Script editor (Run > setup) to:
 *  - Create the Gmail labels
 *  - Install the time-based triggers
 *  - Immediately process any existing Robert emails
 */
function setup() {
  getOrCreateLabel_(CONFIG.LABEL_NAME);
  getOrCreateLabel_(CONFIG.PROCESSED_LABEL_NAME);

  // Remove any stale triggers so we don't double-fire.
  ScriptApp.getProjectTriggers().forEach(t => ScriptApp.deleteTrigger(t));

  // Main processing job — every 6 hours is plenty for email hygiene.
  ScriptApp.newTrigger('processRobertEmails')
    .timeBased()
    .everyHours(6)
    .create();

  // Digest trigger — fires daily, but the function itself only sends on DIGEST_DAY.
  ScriptApp.newTrigger('sendWeeklyDigest')
    .timeBased()
    .everyDays(1)
    .atHour(CONFIG.DIGEST_HOUR)
    .inTimezone('America/New_York')
    .create();

  Logger.log('Setup complete. Running first pass now…');
  processRobertEmails();
  Logger.log('Done. Check the Robert label in Gmail.');
}

/**
 * Main job. Called by the 6-hour trigger (and manually during setup).
 * Finds Robert's emails, archives them, tries to identify his real address,
 * and forwards if ROBERTS_EMAIL is set.
 */
function processRobertEmails() {
  const robertLabel    = getOrCreateLabel_(CONFIG.LABEL_NAME);
  const processedLabel = getOrCreateLabel_(CONFIG.PROCESSED_LABEL_NAME);

  const query   = buildSearchQuery_();
  const threads = GmailApp.search(query, 0, CONFIG.BATCH_SIZE);

  if (threads.length === 0) {
    Logger.log('No new Robert emails found.');
    return;
  }

  Logger.log(`Processing ${threads.length} thread(s)…`);
  let processed = 0;

  threads.forEach(thread => {
    try {
      // Archive and label first — this is the non-negotiable part.
      thread.addLabel(robertLabel);
      thread.addLabel(processedLabel);
      thread.moveToArchive();

      // Try to discover Robert's real email from the email content.
      const { email, phone } = extractRobertEmail_(thread);
      if (email) storeCandidate_('robertCandidates', email);
      if (phone) storeCandidate_('robertPhones', phone);

      // Forward if we know where to send it.
      if (CONFIG.ROBERTS_EMAIL) {
        const firstMessage = thread.getMessages()[0];
        forwardToRobert_(firstMessage, CONFIG.ROBERTS_EMAIL);
      }

      processed++;
    } catch (err) {
      Logger.log(`Error processing thread ${thread.getId()}: ${err}`);
    }
  });

  // Update running total for the digest.
  const props = ScriptApp.getScriptProperties();
  const prev  = parseInt(props.getProperty('totalProcessed') || '0', 10);
  props.setProperty('totalProcessed', String(prev + processed));

  Logger.log(`Done. ${processed} thread(s) processed this run.`);
}

/**
 * Digest job. Fires daily but only sends on CONFIG.DIGEST_DAY.
 * Reports email candidates found so far and how to enable forwarding.
 */
function sendWeeklyDigest() {
  const now     = new Date();
  const dayOfWk = now.getDay(); // 0=Sun … 6=Sat in local time of the trigger

  if (dayOfWk !== CONFIG.DIGEST_DAY) return;

  const props          = ScriptApp.getScriptProperties();
  const totalProcessed = props.getProperty('totalProcessed') || '0';
  const candidates     = JSON.parse(props.getProperty('robertCandidates') || '{}');
  const phones         = JSON.parse(props.getProperty('robertPhones')     || '{}');
  const lastSent       = props.getProperty('lastDigestSent')              || 'never';

  // Sort candidates by frequency descending.
  const sortedEmails = Object.entries(candidates)
    .sort((a, b) => b[1] - a[1]);

  const sortedPhones = Object.entries(phones)
    .sort((a, b) => b[1] - a[1]);

  let body = `Robert Email Doppelganger — Weekly Report\n`;
  body    += `==========================================\n`;
  body    += `Report date : ${now.toDateString()}\n`;
  body    += `Last report : ${lastSent}\n\n`;

  body    += `Emails caught and archived (all time): ${totalProcessed}\n\n`;

  if (sortedEmails.length > 0) {
    body += `Candidate email addresses for Robert's real inbox:\n`;
    sortedEmails.forEach(([email, count], i) => {
      const confidence = count >= 5 ? 'HIGH' : count >= 2 ? 'MEDIUM' : 'LOW';
      body += `  ${i + 1}. ${email} (seen ${count}x) ← ${confidence}\n`;
    });
    body += '\n';

    if (!CONFIG.ROBERTS_EMAIL) {
      const topCandidate = sortedEmails[0][0];
      body += `To enable forwarding, open Code.gs and set:\n`;
      body += `  ROBERTS_EMAIL: '${topCandidate}'\n`;
      body += `Then save and re-run setup() or just let the next trigger fire.\n\n`;
    } else {
      body += `Forwarding is active → ${CONFIG.ROBERTS_EMAIL}\n\n`;
    }
  } else {
    body += `No candidate email addresses found yet.\n`;
    body += `The script will keep scanning incoming emails.\n\n`;
  }

  if (sortedPhones.length > 0) {
    body += `Phone numbers spotted (for reference):\n`;
    sortedPhones.forEach(([phone, count]) => {
      body += `  ${phone} (seen ${count}x)\n`;
    });
    body += '\n';
  }

  body += `────────────────────────────────────\n`;
  body += `Add more sender domains to SENDER_DOMAINS in Code.gs\n`;
  body += `as you spot new services Robert has signed up for.\n`;

  GmailApp.sendEmail(
    CONFIG.MY_EMAIL,
    `[Robert Redirect] Weekly Report — ${now.toDateString()}`,
    body
  );

  props.setProperty('lastDigestSent', now.toDateString());
  Logger.log('Weekly digest sent.');
}

// ─── PRIVATE: SEARCH & LABELLING ─────────────────────────────────────────────

function buildSearchQuery_() {
  const domainClauses = CONFIG.SENDER_DOMAINS
    .map(d => `from:${d}`)
    .join(' OR ');

  // newer_than:30d limits the first run to avoid processing years of history.
  // Remove this clause if you want a full historical cleanup.
  return `(${domainClauses}) -label:${CONFIG.PROCESSED_LABEL_NAME} newer_than:30d`;
}

function getOrCreateLabel_(name) {
  return GmailApp.getUserLabelByName(name) || GmailApp.createLabel(name);
}

// ─── PRIVATE: DETECTIVE WORK ─────────────────────────────────────────────────

/**
 * Tries to find Robert's real email address and any phone numbers from
 * the first message in the thread. Returns { email, phone } — either may be null.
 *
 * Strategy (in priority order):
 *  1. List-Unsubscribe header (most reliable — encodes account email)
 *  2. Footer "this email was sent to [address]" patterns
 *  3. Full body email regex scan with scoring
 *  4. Phone number extraction (informational only)
 */
function extractRobertEmail_(thread) {
  const message   = thread.getMessages()[0];
  const plainBody = message.getPlainBody() || '';
  const sender    = message.getFrom();
  const senderDomain = extractDomain_(sender);

  // ── 1. List-Unsubscribe header ──────────────────────────────────────────
  const headers   = message.getHeader('List-Unsubscribe') || '';
  const unsubEmail = parseUnsubscribeHeader_(headers);
  if (unsubEmail && !isSystemAddress_(unsubEmail) && !isSenderDomain_(unsubEmail, senderDomain)) {
    Logger.log(`[List-Unsubscribe] candidate: ${unsubEmail}`);
    return { email: unsubEmail, phone: null };
  }

  // ── 2. Footer "sent to" patterns ────────────────────────────────────────
  const footerEmail = parseFooterEmail_(plainBody);
  if (footerEmail && !isSystemAddress_(footerEmail) && !isSenderDomain_(footerEmail, senderDomain)) {
    Logger.log(`[Footer] candidate: ${footerEmail}`);
    return { email: footerEmail, phone: extractPhone_(plainBody) };
  }

  // ── 3. Full body scan with scoring ──────────────────────────────────────
  const bodyEmail = scanBodyForEmail_(plainBody, senderDomain);
  if (bodyEmail) {
    Logger.log(`[Body scan] candidate: ${bodyEmail}`);
  }

  // ── 4. Phone (always try, regardless of email result) ───────────────────
  const phone = extractPhone_(plainBody);

  return { email: bodyEmail, phone };
}

function parseUnsubscribeHeader_(header) {
  // Format: <mailto:unsub@example.com?subject=unsub_robert@real.email>
  // or:     <https://example.com/unsubscribe?email=robert@real.email>
  const mailtoMatch = header.match(/mailto:[^?>]+\?[^>]*subject=([^&>]+)/i);
  if (mailtoMatch) {
    const decoded = decodeURIComponent(mailtoMatch[1]);
    const em = decoded.match(/[\w.+\-]+@[\w.\-]+\.\w{2,}/);
    if (em) return em[0].toLowerCase();
  }
  const emailParam = header.match(/[?&](?:email|to|address)=([^&>]+)/i);
  if (emailParam) {
    const decoded = decodeURIComponent(emailParam[1]);
    const em = decoded.match(/[\w.+\-]+@[\w.\-]+\.\w{2,}/);
    if (em) return em[0].toLowerCase();
  }
  return null;
}

function parseFooterEmail_(body) {
  // Matches patterns like:
  //   "This email was sent to robert@example.com"
  //   "You're receiving this because you signed up at robert@example.com"
  //   "Delivered to: robert@example.com"
  const pattern = /(?:sent\s+to|delivered\s+to|you(?:'re|\s+are)\s+receiving\s+(?:this\s+)?(?:email\s+)?(?:because|at)|this\s+message\s+was\s+sent\s+to)\s*[:\-]?\s*([\w.+\-]+@[\w.\-]+\.\w{2,})/gi;
  const match = pattern.exec(body);
  return match ? match[1].toLowerCase() : null;
}

function scanBodyForEmail_(body, senderDomain) {
  const emailRegex = /\b([\w.+\-]+@[\w.\-]+\.[a-zA-Z]{2,})\b/g;
  const scores     = {};
  let match;

  while ((match = emailRegex.exec(body)) !== null) {
    const addr = match[1].toLowerCase();
    if (isSystemAddress_(addr))          continue;
    if (isSenderDomain_(addr, senderDomain)) continue;
    if (addr === 'andydunn5@gmail.com') continue;

    scores[addr] = (scores[addr] || 0) + 1;

    // Bonus for addresses that look like they belong to a Robert.
    const local = addr.split('@')[0];
    if (/robert/i.test(local)) scores[addr] += 10;
    if (/dunn/i.test(local))   scores[addr] += 5;
    // Slight bonus for non-Gmail personal domains (could be work email).
    if (!/@(?:gmail|yahoo|hotmail|outlook|aol|icloud)\./.test(addr)) scores[addr] += 3;
  }

  if (Object.keys(scores).length === 0) return null;

  return Object.entries(scores).sort((a, b) => b[1] - a[1])[0][0];
}

function extractPhone_(body) {
  // US phone numbers in common formats.
  const pattern = /(?:\+?1[\s.\-]?)?\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}/g;
  const match   = body.match(pattern);
  return match ? match[0].replace(/\s+/g, ' ').trim() : null;
}

function extractDomain_(fromHeader) {
  const match = fromHeader.match(/@([\w.\-]+)/);
  return match ? match[1].toLowerCase() : '';
}

function isSenderDomain_(email, senderDomain) {
  if (!senderDomain) return false;
  return email.endsWith('@' + senderDomain) ||
         email.endsWith('.' + senderDomain);
}

function isSystemAddress_(email) {
  return /(?:noreply|no-reply|donotreply|mailer-daemon|bounce|postmaster|notifications?|alerts?|updates?|news|newsletter|info|support|help|marketing|admin|automailer)/i
    .test(email.split('@')[0]);
}

// ─── PRIVATE: STATE & FORWARDING ─────────────────────────────────────────────

function storeCandidate_(propertyKey, value) {
  const props = ScriptApp.getScriptProperties();
  const map   = JSON.parse(props.getProperty(propertyKey) || '{}');
  map[value]  = (map[value] || 0) + 1;
  props.setProperty(propertyKey, JSON.stringify(map));
}

function forwardToRobert_(message, robertEmail) {
  const originalSubject = message.getSubject();
  const subject = `[Fwd from andydunn5@gmail.com] ${originalSubject}`;
  const body    = CONFIG.FORWARD_PREAMBLE + message.getPlainBody();

  GmailApp.sendEmail(robertEmail, subject, body);
  Logger.log(`Forwarded "${originalSubject}" to ${robertEmail}`);
}
