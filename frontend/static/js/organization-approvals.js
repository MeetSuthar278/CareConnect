document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('form[data-application-decision]').forEach(form => {
    form.addEventListener('submit', event => {
      // Shared main.js confirmation runs first; cancellation sends no decision.
      if (event.defaultPrevented) return;
      if (form.dataset.submitting === 'true') {
        event.preventDefault();
        return;
      }
      if (event.submitter?.value === 'reject') {
        const reason = window.prompt('Reason for rejecting this organization (1 to 255 characters):');
        if (reason === null) {
          event.preventDefault();
          return;
        }
        if (!reason.trim() || reason.trim().length > 255) {
          event.preventDefault();
          const alert = document.createElement('div');
          alert.className = 'alert alert-danger';
          alert.setAttribute('role', 'alert');
          alert.textContent = 'Enter a rejection reason containing 1 to 255 characters.';
          document.getElementById('page-messages').replaceChildren(alert);
          return;
        }
        let input = form.querySelector('input[name="reason"]');
        if (!input) {
          input = document.createElement('input');
          input.type = 'hidden';
          input.name = 'reason';
          form.appendChild(input);
        }
        input.value = reason.trim();
      }
      form.dataset.submitting = 'true';
    });
  });
});
window.addEventListener('pageshow', () => {
  document.querySelectorAll('form[data-application-decision]').forEach(form => delete form.dataset.submitting);
});
