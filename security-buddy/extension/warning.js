const params = new URLSearchParams(location.search);
const type = params.get('type') || 'url';
const dest = params.get('dest') || '';
const reason = params.get('reason') || 'This website looks suspicious.';
const risk = params.get('risk') || 'medium';
const label = params.get('label') || 'suspicious page';

const card = document.getElementById('card');

chrome.storage.sync.get(['guardianName', 'userName'], (config) => {
  const guardianName = config.guardianName || 'your family member';

  if (type === 'financial') {
    document.body.classList.add('financial-warning');
    card.innerHTML = `
      <div class="emoji">🛡️</div>
      <h1>Hold on — your Safety Buddy wants to check something.</h1>
      <div class="financial-message">
        <p>You're about to visit a <strong>${escHtml(label)}</strong> page.</p>
        <br>
        <p>Sending gift cards or money to people you've met online is one of the most common ways people lose money to scammers. This happens to thousands of kind, clever people every year — it's not your fault if someone is trying to trick you.</p>
        <br>
        <p>Before you continue, would you like to call <strong>${escHtml(guardianName)}</strong> and let them know? They'd love to hear from you.</p>
      </div>
      <button class="btn-primary" id="callBtn">Call ${escHtml(guardianName)} first</button>
      <button class="btn-secondary" id="continueBtn">I understand — I still want to continue</button>
      <p class="notice">Safety Buddy has already sent ${escHtml(guardianName)} a quick heads-up message.</p>
    `;
    document.getElementById('callBtn').addEventListener('click', () => {
      window.history.back();
    });
    document.getElementById('continueBtn').addEventListener('click', () => {
      chrome.runtime.sendMessage({
        type: 'USER_PROCEEDED',
        url: dest,
        reason: `User proceeded to ${label} page`,
        risk: 'high',
      });
      window.location.href = dest;
    });

  } else {
    document.body.classList.add('url-warning');
    card.innerHTML = `
      <div class="emoji">🛡️</div>
      <h1>Your Safety Buddy thinks this might be dangerous!</h1>
      <p class="reason">${escHtml(reason)}</p>
      <p class="dest">${escHtml(dest)}</p>
      <button class="btn-primary" id="backBtn">Take me back to safety</button>
      <button class="btn-secondary" id="continueBtn">I understand the risk — continue anyway</button>
    `;
    document.getElementById('backBtn').addEventListener('click', () => {
      window.history.back();
    });
    document.getElementById('continueBtn').addEventListener('click', () => {
      chrome.runtime.sendMessage({
        type: 'USER_PROCEEDED',
        url: dest,
        reason,
        risk,
      });
      window.location.href = dest;
    });
  }
});

function escHtml(str) {
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
