const DEFAULT_BACKEND = 'https://api.safetybuddy.app';

async function getBackend() {
  return new Promise(resolve => chrome.storage.local.get(['backendUrl'], ({ backendUrl }) => {
    resolve(backendUrl || DEFAULT_BACKEND);
  }));
}

async function getApiKey() {
  return new Promise(resolve => chrome.storage.local.get(['apiKey'], ({ apiKey }) => resolve(apiKey || null)));
}

async function authHeaders() {
  const key = await getApiKey();
  const h = { 'Content-Type': 'application/json' };
  if (key) h['Authorization'] = `Bearer ${key}`;
  return h;
}

async function handleCheckUrl(msg) {
  const [backend, headers] = await Promise.all([getBackend(), authHeaders()]);
  try {
    const res = await fetch(`${backend}/check-url`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ url: msg.url, page_title: msg.pageTitle || '' }),
    });
    if (!res.ok) return { safe: true };
    return await res.json();
  } catch {
    return { safe: true }; // fail open when backend unreachable
  }
}

async function handleFinancialDanger(msg, senderTabId) {
  const params = new URLSearchParams({ type: 'financial', label: msg.label, dest: msg.url });
  chrome.tabs.update(senderTabId, {
    url: chrome.runtime.getURL('warning.html') + '?' + params.toString(),
  }).catch(() => {}); // tab may have been closed

  const key = await getApiKey();
  if (!key) return; // not logged in — skip server notification

  const [backend, headers] = await Promise.all([getBackend(), authHeaders()]);
  try {
    await fetch(`${backend}/notify-urgent`, {
      method: 'POST',
      headers,
      body: JSON.stringify({ url: msg.url, label: msg.label, timestamp: new Date().toISOString() }),
    });
  } catch {
    // fire-and-forget — ignore network errors
  }
}

async function sendGuardianNotification(payload) {
  const key = await getApiKey();
  if (!key) return;

  const [backend, headers] = await Promise.all([getBackend(), authHeaders()]);
  try {
    await fetch(`${backend}/notify`, { method: 'POST', headers, body: JSON.stringify(payload) });
  } catch {
    // fire-and-forget
  }
}

// Open the onboarding page the first time the extension is installed.
// Updates and browser restarts do not re-trigger this.
chrome.runtime.onInstalled.addListener((details) => {
  if (details.reason === 'install') {
    chrome.tabs.create({ url: chrome.runtime.getURL('onboarding.html') });
  }
});
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'CHECK_URL') {
    handleCheckUrl(message).then(sendResponse).catch(() => sendResponse({ safe: true }));
    return true; // keep the message port open for the async response
  }

  if (message.type === 'FINANCIAL_DANGER_PAGE') {
    handleFinancialDanger(message, sender.tab?.id).catch(() => {});
    return true; // keep port open while async work runs
  }

  if (message.type === 'USER_PROCEEDED') {
    sendGuardianNotification({
      url: message.url,
      reason: message.reason || '',
      risk_level: message.risk || 'unknown',
      proceeded: true,
    }).catch(() => {});
    return true;
  }
});
