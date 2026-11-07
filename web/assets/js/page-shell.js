/* Daxil olmuş səhifələr üçün ortaq qabıq: mühafizə, başlıq, çıxış.
 * Faza 4-də tam naviqasiya çərçivəsi bunun üzərinə gələcək. */

import { ApiError, clearSession, getUser, isLoggedIn, request } from './api.js';
import { createIcon } from './icon.js';
import { expiryBannerText, shouldShowExpiryBanner } from './license.js';
import { applyCourseBranding, renderNavigation } from './nav.js';
import { rememberNext } from './next-path.js';

/** Tokensiz istifadəçini giriş səhifəsinə göndərir. `replace` işlədilir
 *  ki, geri düyməsi qorunan səhifəyə qaytarmasın. */
export function requireLogin() {
  if (!isLoggedIn()) {
    // Girişdən sonra bu səhifəyə qayıt (məs. sinifdə skan edilən QR linki).
    rememberNext(window.sessionStorage, window.location.pathname.split('/').pop() + window.location.search);
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
  mountSkipLink();
  mountCourseBranding(bar);
}

/** Kursu BÜTÜN daxil olmuş istifadəçilər üçün (tələbə daxil) gətirir -
 *  loqo hər kəsə görünməlidir. Xəbərdarlıq banner isə yalnız müəllimə
 *  göstərilir (`shouldShowExpiryBanner`). Xəta səssiz udulur - bu
 *  köməkçi məlumatdır, səhifəni sındırmamalıdır. */
async function mountCourseBranding(bar) {
  const user = getUser();
  if (!user) return;
  let course;
  try {
    course = await request('/me/course');
  } catch {
    return;
  }
  applyCourseBranding(bar, course);
  if (user.is_teacher) mountExpiryBanner(course);
}

/** «Məzmuna keç»: klaviatura ilə gələn hər səhifədə əvvəlcə naviqasiya
 *  zolağının bütün linklərindən keçməli olmasın (WCAG 2.4.1). Link yalnız
 *  fokus alanda görünür. Qorunan səhifələrin ortaq qabı `.app-shell`-dir. */
function mountSkipLink() {
  const shell = document.querySelector('.app-shell');
  if (!shell || document.querySelector('.skip-link')) return;
  if (!shell.id) shell.id = 'main';
  shell.tabIndex = -1;
  const link = document.createElement('a');
  link.className = 'skip-link';
  link.href = `#${shell.id}`;
  link.textContent = 'Məzmuna keç';
  document.body.prepend(link);
}

/** Abunənin bitməsinə az qalıbsa müəllimə xəbərdarlıq (spec: 5 gün).
 *  Kurs artıq `mountCourseBranding`-də (loqo üçün, HƏR istifadəçiyə)
 *  gətirilib - burada təkrar sorğu YOXDUR. */
function mountExpiryBanner(course) {
  const user = getUser();
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
