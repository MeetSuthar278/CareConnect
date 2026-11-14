// Update existing fields only. Never create a second request while polling.
(() => {
  const page = document.getElementById('request-confirmation');
  const id = Number(page.dataset.requestId);
  const end = Date.now() + 120000;
  let timer;
  function showUpdateMessage(text) {
    let alert = document.getElementById('status-update-message');
    if (!alert) {
      alert = document.createElement('div');
      alert.id = 'status-update-message';
      alert.className = 'alert alert-info';
      alert.setAttribute('role', 'status');
      document.getElementById('page-messages').appendChild(alert);
    }
    alert.textContent = text;
  }
  async function refresh() {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch(page.dataset.statusUrl || `/api/guest/requests/${id}`, {cache:'no-store', signal:controller.signal});
      if (!response.ok) throw new Error('Status unavailable');
      const data = await response.json();
      if (data.request_id !== id || typeof data.display_status !== 'string' ||
          typeof data.status !== 'string') throw new Error('Unexpected status response');
      document.getElementById('status-update-message')?.remove();
      const badge = document.querySelector('#request-status .status');
      badge.textContent = data.display_status;
      badge.className = 'status status-' + data.display_status.toLowerCase().replaceAll(' ', '-');
      const due = document.querySelector('.deadline');
      if (data.response_deadline) {
        due.textContent = 'Response due: ' + new Intl.DateTimeFormat('en-GB', {
          dateStyle:'medium', timeStyle:'short', timeZone:'UTC'
        }).format(new Date(data.response_deadline)) + ' UTC';
      }
      if (data.status !== 'submitted') return;
    } catch (_) {
      showUpdateMessage('Unable to refresh your request right now. Reload this page to check again.');
    } finally { clearTimeout(timeout); }
    if (Date.now() < end) timer = setTimeout(refresh, 2000);
    else showUpdateMessage('Automatic updates paused. Reload this page to check your latest status.');
  }
  timer = setTimeout(refresh, 2000);
  window.addEventListener('pagehide', () => clearTimeout(timer));
})();
