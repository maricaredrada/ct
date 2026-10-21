const button = document.getElementById('scan-btn');
const result = document.getElementById('result');

const resetToPrompt = () => {
  window.setTimeout(() => {
    result.textContent = 'Ready for next scan.';
    result.className = '';
  }, 2200);
};

button?.addEventListener('click', async () => {
  button.disabled = true;
  result.textContent = 'Scanning...';
  try {
    const response = await fetch('/kiosk/scan', { method: 'POST' });
    const data = await response.json();
    if (data.ok) {
      result.textContent = `${data.action}: ${data.member.name} (${data.member.classification})`;
      result.className = 'ok';
    } else {
      result.textContent = data.message;
      result.className = 'error';
    }
  } catch {
    result.textContent = 'Scan request failed.';
    result.className = 'error';
  } finally {
    button.disabled = false;
    resetToPrompt();
  }
});
