const fields = ['userName', 'guardianName', 'guardianEmail', 'guardianPhone'];

chrome.storage.sync.get(fields, (data) => {
  for (const key of fields) {
    if (data[key]) document.getElementById(key).value = data[key];
  }
});

document.getElementById('saveBtn').addEventListener('click', () => {
  const values = {};
  for (const key of fields) {
    values[key] = document.getElementById(key).value.trim();
  }
  chrome.storage.sync.set(values, () => {
    const status = document.getElementById('status');
    status.textContent = '✓ Saved!';
    setTimeout(() => { status.textContent = ''; }, 2000);
  });
});
