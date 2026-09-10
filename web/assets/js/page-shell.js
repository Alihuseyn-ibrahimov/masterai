/* Daxil olmuş səhifələr üçün ortaq qabıq: mühafizə, başlıq, çıxış.
 * Faza 4-də tam naviqasiya çərçivəsi bunun üzərinə gələcək. */

import { ApiError, clearSession, getUser, isLoggedIn } from './api.js';
import { createIcon } from './icon.js';
import { renderNavigation } from './nav.js';

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

/**
 * Səhifənin naviqasiya qabığını qurur: üst zolaq (geniş ekran) +
 * alt panel (mobil). Hər qorunan səhifə bunu çağırır.
 *
 * Qabıq DOM-un `#appBar` və `#bottomNav` elementlərini gözləyir - * onlar hər səhifədə eyni adla olmalıdır.
 */
export function mountShell() {
  const bar = document.getElementById('appBar');
  const bottom = document.getElementById('bottomNav');
  if (!bar || !bottom) return;
  renderNavigation({
    bar,
    bottom,
    user: getUser(),
    pathname: window.location.pathname,
    onLogout: logout,
  });
}

/** Siyahı yükləmənin ÜÇ halını (yüklənir / xəta / məzmun) bir yerdə
 *  idarə edir - Flutter tərəfində bu, hər ekranda ayrıca və fərqli
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
    const iconWrap = document.createElement('div');
    iconWrap.className = 'state__icon';
    iconWrap.append(createIcon('alert'));
    const title = document.createElement('div');
    title.className = 'state__title';
    title.textContent = 'Yüklənmədi';
    state.append(iconWrap, title);
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
