/* Naviqasiya çərçivəsi - bölmələr, aktivlik, göstərmə.
 *
 * Bölmə siyahısı və aktivlik məntiqi SAF funksiyalardır (DOM tələb
 * etmir) ki, Node-da test edilə bilsinlər.
 *
 * Bölmə sayı hər rol üçün ən çox 5-dir. Rəqəm GÜMAN EDİLMƏDİ, ÖLÇÜLDÜ:
 * 390px-lik telefonda 5 bölmənin hər biri 78px xana alır və etiketlər
 * bir sətirdə sığır. 320px-də xana 64px olur, ona görə uzun etiketin
 * `short` variantı verilir - alt panel onu işlədir, üst zolaq isə tam
 * etiketi saxlayır (masaüstündə yer var).
 *
 * İkon adları `assets/icons.svg` sprite-ının id-ləridir (emoji YOX,
 * bax `icon.js` modul qeydi).
 */

import { createIcon } from './icon.js';

const STUDENT_DESTINATIONS = [
  // `matches` - hansı səhifələrdə bu bölmə aktiv sayılır. Detal
  // səhifəsi (məs. `chat.html`) öz bölməsini işıqlandırmalıdır, əks
  // halda istifadəçi "harda olduğunu" itirir.
  /* «Bu gün» (2026-10-31) ilk bölmədir: auditdə ana ekran yox idi,
     tələbə girişdən sonra çat siyahısına düşürdü. Tarixçə və nişanlar
     «Profil»in altına keçdi - «Bu gün» onsuz da seriya və nişanı
     göstərir. */
  { href: 'bugun.html', label: 'Bu gün', icon: 'home', matches: ['bugun.html'] },
  /* Dərslər xülasələri və tutoru da əhatə edir: tələbə kabinetinin
     əsas bölməsidir, xülasə isə dərsin bir hissəsidir. */
  { href: 'dersler.html', label: 'Dərslər', icon: 'school', matches: ['dersler.html', 'dersim.html', 'dars.html', 'tutor.html', 'xulaseler.html', 'xulase.html'] },
  { href: 'tapsiriqlar.html', label: 'Tapşırıqlar', short: 'Tapşırıq', icon: 'notes', matches: ['tapsiriqlar.html', 'tapsiriq.html'] },
  { href: 'chatlar.html', label: 'Çatlar', icon: 'message', matches: ['chatlar.html', 'chat.html', 'sessiya.html'] },
  { href: 'profil.html', label: 'Profil', icon: 'user', matches: ['profil.html', 'tarixce.html', 'nailiyyetler.html', 'sahib.html'] },
];

/* Müəllimdə DƏ çat bölməsi var. Əvvəl yox idi və bu, funksional
 * boşluq yaradırdı: `hesabatlar.html` tapşırıq təyin etmək üçün çat
 * TƏLƏB EDİR («əvvəlcə qrup çatına üzv olun»), amma müəllimin çat
 * siyahısına çatmaq yolu yox idi - yəni təzə müəllim hesabı ev
 * tapşırığı təyin edə bilmirdi. Çat həm də müəllimin sinifə mesaj
 * yazdığı yerdir.
 *
 * 2026-10-31: «Bu gün» birinci oldu, «Profil» bölmədən çıxdı - üst
 * zolaqdakı avatar profilə aparır (5 bölmə həddi qalır). */
const TEACHER_DESTINATIONS = [
  { href: 'bugun.html', label: 'Bu gün', icon: 'home', matches: ['bugun.html'] },
  /* Canlı quiz sessiyası dərsin bir hissəsidir: sessiyalar dərs
     bölməsindən linklə açılır. */
  { href: 'dersler.html', label: 'Dərslər', icon: 'school', matches: ['dersler.html', 'dersim.html', 'dars.html', 'sessiyalar.html', 'tutor.html'] },
  { href: 'muellim.html', label: 'Quiz yarat', short: 'Quiz', icon: 'books', matches: ['muellim.html', 'suallar.html', 'xulase.html'] },
  { href: 'chatlar.html', label: 'Çatlar', icon: 'message', matches: ['chatlar.html', 'chat.html'] },
  { href: 'hesabatlar.html', label: 'Hesabatlar', short: 'Hesabat', icon: 'report', matches: ['hesabatlar.html', 'tarixce.html'] },
];

/** Alt paneldə göstəriləcək etiket: dar telefonda uzun ad iki sətrə
 *  düşüb sıranı əyir. `short` verilməyibsə adi etiket işlədilir. */
export function shortLabel(destination) {
  return (destination && destination.short) || (destination && destination.label) || '';
}

export function destinationsFor(user) {
  return user && user.is_teacher ? TEACHER_DESTINATIONS : STUDENT_DESTINATIONS;
}

/** Bütün mövcud bölmələr - testlərin "hər hədəf səhifəsi var?"
 *  yoxlaması üçün. */
export function allDestinations() {
  return [...STUDENT_DESTINATIONS, ...TEACHER_DESTINATIONS];
}

/** Cari ünvana uyğun bölmənin `href`-i; uyğun yoxdursa `null`.
 *  Tam yol da (`/masterai/web/chat.html`), təkcə fayl adı da qəbul
 *  edilir - səhifələr həm `file://`, həm serverdən açıla bilər. */
export function activeHref(destinations, pathname) {
  const file = String(pathname || '').split('/').pop().split('?')[0];
  const match = destinations.find((destination) => destination.matches.includes(file));
  return match ? match.href : null;
}

/* ---- DOM ---- */

function link(destination, active, className, withIcon) {
  const node = document.createElement('a');
  node.className = className;
  node.href = destination.href;
  if (active) node.setAttribute('aria-current', 'page');
  if (withIcon) {
    node.append(createIcon(destination.icon, 'bottom-nav__icon'));
  }
  const label = document.createElement('span');
  // Alt panel (ikonlu) qısa etiketi, üst zolaq tam etiketi göstərir.
  label.textContent = withIcon ? shortLabel(destination) : destination.label;
  node.append(label);
  return node;
}

/**
 * Üst zolağı və mobil alt paneli qurur.
 *
 * @param {object} options
 * @param {HTMLElement} options.bar - üst zolaq konteyneri
 * @param {HTMLElement} options.bottom - alt panel konteyneri
 * @param {object|null} options.user
 * @param {string} options.pathname
 * @param {() => void} options.onLogout
 */
export function renderNavigation({ bar, bottom, user, pathname, onLogout }) {
  const destinations = destinationsFor(user);
  const active = activeHref(destinations, pathname);

  bar.className = 'app-bar';
  bar.innerHTML = '';

  const brand = document.createElement('a');
  brand.className = 'brand';
  /* Loqo AÇILIŞ SƏHİFƏSİNƏ aparır, ilk bölməyə yox.
     Əvvəl `destinations[0].href` idi - yəni müəllim üçün «Sual
     bankları», tələbə üçün «Çatlar». İstifadəçi loqodan əsas sayta
     qayıtmaq gözləyir; bölmələr onsuz da zolağın özündədir. */
  brand.href = 'index.html';
  brand.append(document.createTextNode('Master'));
  const accent = document.createElement('span');
  accent.className = 'brand__accent';
  accent.textContent = 'AI';
  brand.append(accent);

  const nav = document.createElement('nav');
  nav.className = 'app-nav';
  nav.setAttribute('aria-label', 'Əsas bölmələr');
  for (const destination of destinations) {
    nav.append(link(destination, destination.href === active, 'app-nav__link', false));
  }

  const right = document.createElement('div');
  right.className = 'app-bar__user';
  const name = (user && user.display_name) || 'İstifadəçi';
  /* Avatar profilə aparır - müəllim naviqasiyasında «Profil» bölməsi
     yoxdur (5 bölmə həddi), yol isə qalmalıdır. */
  const avatar = document.createElement('a');
  avatar.href = 'profil.html';
  avatar.setAttribute('aria-label', 'Profil');
  avatar.className = 'avatar';
  avatar.textContent = name.trim().charAt(0).toUpperCase() || '?';
  avatar.title = name;
  const logoutButton = document.createElement('button');
  logoutButton.className = 'btn btn--secondary btn--sm';
  logoutButton.type = 'button';
  logoutButton.textContent = 'Çıxış';
  logoutButton.addEventListener('click', onLogout);
  right.append(avatar, logoutButton);

  bar.append(brand, nav, right);

  bottom.className = 'bottom-nav';
  bottom.setAttribute('aria-label', 'Əsas bölmələr');
  bottom.innerHTML = '';
  for (const destination of destinations) {
    bottom.append(link(destination, destination.href === active, 'bottom-nav__link', true));
  }
}
