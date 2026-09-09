/* Daxil olmuş səhifələr üçün ortaq qabıq: mühafizə, başlıq, çıxış.
 * Faza 4-də tam naviqasiya çərçivəsi bunun üzərinə gələcək. */

import { ApiError, clearSession, getUser, isLoggedIn } from './api.js';
import { homePathForCurrentUser } from './auth-page.js';

/** Tokensiz istifadəçini giriş səhifəsinə göndərir. `replace` işlədilir
 *  ki, geri düyməsi qorunan səhifəyə qaytarmasın. */
export function requireLogin() {
  if (!isLoggedIn()) {
    window.location.replace('giris.html');
    return false;
  }
  return true;
}

export function logout() {
  clearSession();
  window.location.replace('giris.html');
}

/** Baş başlığı doldurur: brend + istifadəçi adı + çıxış düyməsi. */
export function renderHeader(container) {
  const user = getUser();
  const name = user && user.display_name ? user.display_name : 'İstifadəçi';
  const initial = name.trim().charAt(0).toUpperCase() || '?';

  container.innerHTML = '';
  container.className = 'row row--between';

  const brand = document.createElement('a');
  brand.className = 'brand';
  // `index.html` (açılış səhifəsi) Faza 6-da gələcək — hələlik brend
  // istifadəçinin öz başlanğıc səhifəsinə qayıdır.
  brand.href = homePathForCurrentUser();
  brand.innerHTML = 'Master<span class="brand__accent">AI</span>';

  const right = document.createElement('div');
  right.className = 'row';

  const avatar = document.createElement('span');
  avatar.className = 'avatar';
  avatar.textContent = initial;

  const label = document.createElement('span');
  label.className = 'text-sm';
  label.textContent = name;

  const button = document.createElement('button');
  button.className = 'btn btn--secondary btn--sm';
  button.type = 'button';
  button.textContent = 'Çıxış';
  button.addEventListener('click', logout);

  right.append(avatar, label, button);
  container.append(brand, right);
}

/** Siyahı yükləmənin ÜÇ halını (yüklənir / xəta / məzmun) bir yerdə
 *  idarə edir — Flutter tərəfində bu, hər ekranda ayrıca və fərqli
 *  yazılırdı, çox yerdə isə ümumiyyətlə yox idi. */
export async function loadInto(container, loader, render) {
  container.innerHTML = '<div class="state"><div class="spinner"></div>'
    + '<div class="state__text">Yüklənir…</div></div>';
  try {
    render(container, await loader());
  } catch (error) {
    // 401 = token köhnəlib/etibarsızdır: sessiyanı təmizləyib girişə at.
    if (error instanceof ApiError && error.status === 401) {
      logout();
      return;
    }
    container.innerHTML = '';
    const state = document.createElement('div');
    state.className = 'state';
    state.innerHTML = '<div class="state__icon">⚠️</div>'
      + '<div class="state__title">Yüklənmədi</div>';
    const text = document.createElement('div');
    text.className = 'state__text';
    text.textContent = error.message;
    const retry = document.createElement('button');
    retry.className = 'btn btn--secondary';
    retry.type = 'button';
    retry.textContent = 'Təkrar cəhd et';
    retry.addEventListener('click', () => loadInto(container, loader, render));
    state.append(text, retry);
    container.append(state);
  }
}
