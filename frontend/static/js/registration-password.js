// Keep these rules in sync with tools/create_firebase_test_user.py.
// Firebase's supported non-alphanumeric characters; whitespace is not special.
const specialCharacters = `^$*.[]{}()?"!@#%&/\\,><':;|_~` + '`-';
const passwordPolicyMessage = 'Use at least 8 characters, including an uppercase letter (A–Z) and a special character (for example, @, #, $, ! or %).';

export function passwordRequirements(password) {
  return {
    length: Array.from(password).length >= 8,
    uppercase: /[A-Z]/.test(password),
    special: Array.from(password).some(character => specialCharacters.includes(character)),
  };
}

export function passwordValidationMessage(password, confirmation) {
  if (!password) return 'Enter a password.';
  if (!Object.values(passwordRequirements(password)).every(Boolean)) return passwordPolicyMessage;
  if (!confirmation) return 'Confirm your password.';
  if (password !== confirmation) return 'Passwords do not match. Enter the same password in both fields.';
  return '';
}

export function firebasePasswordErrorMessage(code) {
  if (code === 'auth/weak-password' || code === 'auth/password-does-not-meet-requirements') {
    return `The password was not accepted. ${passwordPolicyMessage} If it already meets these requirements, contact CareConnect support to check the account password policy.`;
  }
  return '';
}

export function attachPasswordValidation(form) {
  const password = form.elements.password;
  const confirmation = form.elements.confirm_password;
  const requirements = form.querySelectorAll('[data-password-requirement]');

  function update() {
    const satisfied = passwordRequirements(password.value);
    requirements.forEach(item => {
      const met = satisfied[item.dataset.passwordRequirement];
      item.classList.toggle('is-satisfied', met);
      const icon = item.querySelector('[data-requirement-icon]');
      const status = item.querySelector('[data-requirement-status]');
      const symbol = met ? '✓' : '○';
      const description = met ? 'Satisfied.' : 'Not yet satisfied.';
      if (icon.textContent !== symbol) icon.textContent = symbol;
      if (status.textContent !== description) status.textContent = description;
    });
    password.setCustomValidity(!password.value ? 'Enter a password.' :
      Object.values(satisfied).every(Boolean) ? '' : passwordPolicyMessage);
    confirmation.setCustomValidity(!confirmation.value ? 'Confirm your password.' :
      password.value === confirmation.value ? '' : 'Passwords do not match. Enter the same password in both fields.');
    // Clear stale field errors as soon as the user fixes a password.
    [password, confirmation].forEach(field => {
      const error = document.getElementById(`${field.id}_error`);
      if (error) error.textContent = field.validationMessage;
      if (field.validity.valid) field.removeAttribute('aria-invalid');
    });
  }

  form.addEventListener('input', update);
  form.addEventListener('change', update);
  form.addEventListener('reset', () => setTimeout(update, 0));
  update();

  return {
    update,
    validate() {
      update();
      const message = passwordValidationMessage(password.value, confirmation.value);
      if (message) {
        const field = password.validity.valid ? confirmation : password;
        field.focus();
        field.reportValidity();
      }
      return message;
    },
  };
}
