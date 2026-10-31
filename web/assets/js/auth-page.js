/* Giriş və qeydiyyat formalarının paylaşılan məntiqi.
 *
 * Hər iki səhifə eyni davranışı gözləyir: göndərmə zamanı düymə
 * bloklanır (ikiqat göndərmənin qarşısı), xəta ekran oxuyucusuna da
 * çatır (`role="alert"`), uğurdan sonra rola görə yönləndirmə. */

import { isLoggedIn } from './api.js';
import { takeNext } from './next-path.js';

/** Daxil olmuş istifadəçini öz səhifəsinə göndərir - müəllim və tələbə
 *  fərqli başlanğıc ekranı görür. */
export function homePathForCurrentUser() {
  const next = takeNext(window.sessionStorage);
  if (next) return next;
  /* Hər iki rol «Bu gün»dən başlayır (2026-10-31): rol fərqi səhifənin
     İÇİNDƏDİR, giriş yolu bir olur. */
  return 'bugun.html';
}

/** Auth səhifəsinə ARTIQ daxil olmuş istifadəçi düşərsə, formanı
 *  göstərmək mənasızdır. */
export function redirectIfAlreadyLoggedIn() {
  if (isLoggedIn()) {
    window.location.replace(homePathForCurrentUser());
    return true;
  }
  return false;
}

/**
 * @param {object} options
 * @param {HTMLFormElement} options.form
 * @param {HTMLElement} options.errorBox
 * @param {HTMLButtonElement} options.submitButton
 * @param {(data: Record<string, string>) => Promise<unknown>} options.submit
 */
export function wireAuthForm({ form, errorBox, submitButton, submit }) {
  const idleLabel = submitButton.textContent;

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    errorBox.hidden = true;
    errorBox.textContent = '';
    submitButton.disabled = true;
    submitButton.textContent = 'Gözləyin…';

    const data = Object.fromEntries(new FormData(form).entries());
    try {
      await submit(data);
      window.location.replace(homePathForCurrentUser());
    } catch (error) {
      errorBox.textContent = error.message;
      errorBox.hidden = false;
      submitButton.disabled = false;
      submitButton.textContent = idleLabel;
      // Fokusu ilk sahəyə qaytarmaq düzəlişi asanlaşdırır.
      const firstField = form.querySelector('input');
      if (firstField) firstField.focus();
    }
  });
}
