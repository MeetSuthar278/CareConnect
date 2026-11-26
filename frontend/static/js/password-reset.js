import {firebase} from './firebase-client.js';

const button = document.getElementById('password-reset');
const email = document.getElementById('email');
const messages = document.getElementById('page-messages');
let busy = false;
let retryAfter = 0;

button.addEventListener('click', async () => {
  if (busy) return;
  email.value = email.value.trim();
  if (!email.reportValidity()) return;
  const alert = document.createElement('div');
  alert.setAttribute('role', 'status');
  alert.className = 'alert alert-info';
  messages.replaceChildren(alert);
  if (Date.now() < retryAfter) {
    alert.textContent = 'Please wait a minute before requesting another reset link.';
    return;
  }
  busy = true;
  button.disabled = true;
  try {
    const provider = await firebase();
    await provider.sdk.sendPasswordResetEmail(provider.auth, email.value);
    retryAfter = Date.now() + 60000;
    alert.textContent = 'If an account uses this email, a password reset link will arrive shortly. Check your spam folder too.';
  } catch (error) {
    // Keep the same result for unknown/disabled accounts; never enumerate users.
    if (['auth/user-not-found', 'auth/user-disabled'].includes(error.code)) {
      retryAfter = Date.now() + 60000;
      alert.textContent = 'If an account uses this email, a password reset link will arrive shortly. Check your spam folder too.';
    } else {
      alert.className = 'alert alert-danger';
      alert.setAttribute('role', 'alert');
      alert.textContent = error.code === 'auth/too-many-requests'
        ? 'Too many reset requests. Please wait and try again later.'
        : error.code === 'auth/invalid-email'
          ? 'Enter a valid email address to request a reset link.'
          : 'Unable to request a reset link right now. Please try again later.';
    }
  } finally {
    busy = false;
    button.disabled = false;
  }
});
