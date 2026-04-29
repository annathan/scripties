const BACKEND = 'http://localhost:8000';

async function getConfig() {
  return new Promise(resolve => chrome.storage.sync.get(
    ['guardianEmail', 'guardianPhone', 'guardianName', 'userName'],
    resolve,
  ));
}

async function handleCheckUrl(msg) {
  const config = await getConfig();
  try {
    const res = await fetch(`${BACKEND}/check-url`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        url: msg.url,
        page_title: msg.pageTitle || '',
      }),
    });
    if (!res.ok) return { safe: true }; // fail open on server error
    return await res.json();
  } catch {
    return { safe: true }; // fail open when backend unreachable
  }
}

async function sendGuardianNotification(payload) {
  const config = await getConfig();
  if (!config.guardianEmail) return;

  fetch(`${BACKEND}/notify`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      guardian_email: config.guardianEmail,
      guardian_name: config.guardianName || 'there',
      user_name: config.userName || 'Your family member',
      ...payload,
    }),
  }).catch(() => {});
}

async function handleFinancialDanger(msg, senderTabId) {
  const config = await getConfig();

  // Redirect the tab to the financial warning page
  const params = new URLSearchParams({
    type: 'financial',
    label: msg.label,
    dest: msg.url,
  });
  chrome.tabs.update(senderTabId, {
    url: chrome.runtime.getURL('warning.html') + '?' + params.toString(),
  });

  // Fire-and-forget urgent SMS
  if (config.guardianPhone) {
    fetch(`${BACKEND}/notify-urgent`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        guardian_phone: config.guardianPhone,
        guardian_name: config.guardianName || 'there',
        user_name: config.userName || 'Your family member',
        url: msg.url,
        label: msg.label,
        timestamp: new Date().toISOString(),
      }),
    }).catch(() => {});
  }
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'CHECK_URL') {
    handleCheckUrl(message).then(sendResponse);
    return true; // keep port open for async response
  }

  if (message.type === 'FINANCIAL_DANGER_PAGE') {
    handleFinancialDanger(message, sender.tab.id);
    return false;
  }

  if (message.type === 'USER_PROCEEDED') {
    sendGuardianNotification({
      url: message.url,
      reason: message.reason || 'No reason given',
      risk_level: message.risk || 'unknown',
      proceeded: true,
    });
    return false;
  }
});
