const FINANCIAL_DANGER_PATTERNS = [
  { pattern: /amazon\.com\/(gift[-_]?cards?|gp\/gift)/i, label: 'Amazon gift card' },
  { pattern: /bestbuy\.com\/(site\/gift[-_]?cards?|GIFT)/i, label: 'Best Buy gift card' },
  { pattern: /target\.com\/(gift[-_]?cards?|p\/gift)/i, label: 'Target gift card' },
  { pattern: /walmart\.com\/browse\/gift[-_]?cards?/i, label: 'Walmart gift card' },
  { pattern: /store\.steampowered\.com\/digitalgiftcards/i, label: 'Steam gift card' },
  { pattern: /play\.google\.com.*(redeem|gift)/i, label: 'Google Play gift card' },
  { pattern: /apple\.com\/(shop\/buy-giftcard|gift[-_]?cards?)/i, label: 'Apple gift card' },
  { pattern: /cvs\.com\/shop\/gift[-_]?cards?/i, label: 'CVS gift card' },
  { pattern: /westernunion\.com\/(us\/en\/)?send/i, label: 'Western Union money transfer' },
  { pattern: /moneygram\.com\/send/i, label: 'MoneyGram money transfer' },
  { pattern: /coinbase\.com\/(buy|send)/i, label: 'cryptocurrency purchase' },
];

// --- Financial danger detection (runs on every navigation) ---
// Wrap in a function so it can be called after DOMContentLoaded if needed.
function checkFinancialDanger() {
  const url = window.location.href;
  const match = FINANCIAL_DANGER_PATTERNS.find(p => p.pattern.test(url));
  if (match) {
    chrome.runtime.sendMessage({
      type: 'FINANCIAL_DANGER_PAGE',
      url,
      label: match.label,
      pageTitle: document.title,
    });
  }
}

// document_start: DOM may not be ready yet, but location.href is always available.
checkFinancialDanger();

// --- Link click interception ---
let spinnerEl = null;

function showCheckingSpinner() {
  spinnerEl = document.createElement('div');
  spinnerEl.id = '__safety_buddy_spinner__';
  spinnerEl.style.cssText = [
    'position:fixed', 'inset:0', 'z-index:2147483647',
    'background:rgba(255,255,255,0.9)',
    'display:flex', 'flex-direction:column',
    'align-items:center', 'justify-content:center',
    'font-family:sans-serif',
  ].join(';');
  spinnerEl.innerHTML = `
    <div style="font-size:64px;margin-bottom:16px">🛡️</div>
    <div style="font-size:22px;font-weight:bold;color:#1565c0">Safety Buddy is checking that link…</div>
    <div style="font-size:16px;color:#555;margin-top:8px">Just a moment!</div>
  `;
  (document.body || document.documentElement).appendChild(spinnerEl);
}

function hideCheckingSpinner() {
  if (spinnerEl) {
    spinnerEl.remove();
    spinnerEl = null;
  }
}

document.addEventListener('click', async (e) => {
  // Only intercept plain left-clicks — let the browser handle everything else natively.
  // Ctrl/Cmd = open in new tab, Shift = new window, Alt = save/download, button≠0 = middle/right.
  if (e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;

  const a = e.target.closest('a[href]');
  if (!a) return;

  // Let file downloads through — we're not checking content, just destinations.
  if (a.hasAttribute('download')) return;

  let dest;
  try {
    dest = new URL(a.href);
  } catch {
    return;
  }

  if (!['http:', 'https:'].includes(dest.protocol)) return;
  if (dest.hostname === location.hostname) return;
  if (a.href.startsWith('chrome-extension://') || a.href.startsWith('moz-extension://')) return;

  e.preventDefault();
  e.stopImmediatePropagation();

  showCheckingSpinner();

  let verdict;
  try {
    verdict = await chrome.runtime.sendMessage({
      type: 'CHECK_URL',
      url: a.href,
      pageTitle: document.title,
    });
  } catch {
    verdict = { safe: true }; // fail open if extension context is invalidated
  } finally {
    hideCheckingSpinner();
  }

  if (!verdict || verdict.safe) {
    window.location.href = a.href;
  } else {
    const params = new URLSearchParams({
      type: 'url',
      dest: a.href,
      reason: verdict.reason || 'This website looks suspicious.',
      risk: verdict.risk_level || 'medium',
    });
    window.location.href = chrome.runtime.getURL('warning.html') + '?' + params.toString();
  }
}, true); // capture phase — fires before any page handler
