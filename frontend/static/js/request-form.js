// Preserve the native team form and Post/Redirect/Get; block rapid duplicate clicks.
document.getElementById('team-request-form').addEventListener('submit', function (event) {
  if (event.defaultPrevented || !this.checkValidity()) return;
  if (this.dataset.submitting === 'true') { event.preventDefault(); return; }
  this.dataset.submitting = 'true';
  this.querySelector('button[type="submit"]').disabled = true;
});
window.addEventListener('pageshow', () => {
  const form = document.getElementById('team-request-form');
  delete form.dataset.submitting;
  // Preserve the server's empty-catalog disabled state.
  form.querySelector('button[type="submit"]').disabled = form.querySelector('#service_id').options.length < 2;
});
