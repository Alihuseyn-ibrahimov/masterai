/* Daxil olmuş səhifələr üçün ortaq qabıq: mühafizə, başlıq, çıxış.
 * Faza 4-də tam naviqasiya çərçivəsi bunun üzərinə gələcək. */

import { ApiError, clearSession, getUser, isLoggedIn, request } from './api.js';
import { createIcon } from './icon.js';
import { expiryBannerText, shouldShowExpiryBanner } from './license.js';
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
  mountExpiryBanner();
}

/** Abunənin bitməsinə az qalıbsa müəllimə xəbərdarlıq (spec: 5 gün).
 *  Tələbə üçün sorğu HEÇ GÖNDƏRİLMİR. Xəta səssiz udulur - banner
 *  köməkçi məlumatdır, səhifəni sındırmamalıdır (402 isə `request`
 *  içində onsuz da bağlı səhifəyə aparır). */
async function mountExpiryBanner() {
  const user = getUser();
  if (!user || !user.is_teacher) return;
  let course;
  try {
    course = await request('/me/course');
  } catch {
    return;
  }
  if (!shouldShowExpiryBanner(user, course)) return;
  // Qorunan səhifələrdə `<main>` YOXDUR - ortaq konteyner `.app-shell`-dir
  // (test_web_pages.py bunu hər səhifədə yoxlayır).
  const shell = document.querySelector('.app-shell');
  if (!shell) return;
  const banner = document.createElement('div');
  banner.className = 'notice notice--warning';
  banner.setAttribute('role', 'status');
  const text = document.createElement('span');
  text.textContent = expiryBannerText(course.days_left);
  banner.append(createIcon('alert'), text);
  shell.prepend(banner);
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
