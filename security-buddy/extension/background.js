const DEFAULT_BACKEND = 'https://api.safetybuddy.app';

async function getBackend() {
  return new Promise(resolve => {
    chrome.storage.local.get(['backendUrl'], ({ backendUrl }) => {
      resolve(backendUrl || DEFAULT_BACKEND);
    });
  });
}

async function getApiKey() {
  return new Promise(resolve => {
    chrome.storage.local.get(['apiKey'], ({ apiKey }) => resolve(apiKey || null));
  });
}

async function authHeaders() {
  const key = await getApiKey();
  return key
    ? { 'Content-Type': 'application/json', 'Authorization': `Bearer ${key}` }
    : { 'Content-Type': 'application/json' };
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
  const params = new URLSearchParams({
    type: 'financial',
    label: msg.label,
    dest: msg.url,
  });
  chrome.tabs.update(senderTabId, {
    url: chrome.runtime.getURL('warning.html') + '?' + params.toString(),
  });

  const [backend, headers] = await Promise.all([getBackend(), authHeaders()]);
  const key = await getApiKey();
  if (!key) return; // not logged in — skip notification (they're on free/anon)

  fetch(`${backend}/notify-urgent`, {
    method: 'POST',
    headers,
    body: JSON.stringify({
      url: msg.url,
      label: msg.label,
      timestamp: new Date().toISOString(),
    }),
  }).catch(() => {});
}

async function sendGuardianNotification(payload) {
  const key = await getApiKey();
  if (!key) return;

  const [backend, headers] = await Promise.all([getBackend(), authHeaders()]);
  fetch(`${backend}/notify`, {
    method: 'POST',
    headers,
    body: JSON.stringify(payload),
  }).catch(() => {});
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'CHECK_URL') {
    handleCheckUrl(message).then(sendResponse);
    return true;
  }

  if (message.type === 'FINANCIAL_DANGER_PAGE') {
    handleFinancialDanger(message, sender.tab.id);
    return false;
  }

  if (message.type === 'USER_PROCEEDED') {
    sendGuardianNotification({
      url: message.url,
      reason: message.reason || '',
      risk_level: message.risk || 'unknown',
      proceeded: true,
    });
    return false;
  }
});
