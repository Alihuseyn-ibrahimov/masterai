/* Naviqasiya çərçivəsi — bölmələr, aktivlik, göstərmə.
 *
 * Bölmə siyahısı və aktivlik məntiqi SAF funksiyalardır (DOM tələb
 * etmir) ki, Node-da test edilə bilsinlər.
 *
 * Bölmə sayı hər rol üçün ən çox 4-dür: mobil alt panelə 5-dən çoxu
 * sığmır və hədəf 4-də saxlanılır ki, etiketlər kəsilməsin.
 */

const STUDENT_DESTINATIONS = [
  // `matches` — hansı səhifələrdə bu bölmə aktiv sayılır. Detal
  // səhifəsi (məs. `chat.html`) öz bölməsini işıqlandırmalıdır, əks
  // halda istifadəçi "harda olduğunu" itirir.
  { href: 'chatlar.html', label: 'Çatlar', icon: '💬', matches: ['chatlar.html', 'chat.html'] },
  { href: 'tapsiriqlar.html', label: 'Tapşırıqlar', icon: '📝', matches: ['tapsiriqlar.html'] },
  { href: 'tarixce.html', label: 'Tarixçə', icon: '📊', matches: ['tarixce.html', 'nailiyyetler.html'] },
  { href: 'profil.html', label: 'Profil', icon: '👤', matches: ['profil.html'] },
];

const TEACHER_DESTINATIONS = [
  { href: 'muellim.html', label: 'Sual bankları', icon: '📚', matches: ['muellim.html'] },
  { href: 'sessiyalar.html', label: 'Sessiyalar', icon: '🎯', matches: ['sessiyalar.html'] },
  { href: 'hesabatlar.html', label: 'Hesabatlar', icon: '📈', matches: ['hesabatlar.html'] },
  { href: 'profil.html', label: 'Profil', icon: '👤', matches: ['profil.html'] },
];

export function destinationsFor(user) {
  return user && user.is_teacher ? TEACHER_DESTINATIONS : STUDENT_DESTINATIONS;
}

/** Bütün mövcud bölmələr — testlərin "hər hədəf səhifəsi var?"
 *  yoxlaması üçün. */
export function allDestinations() {
  return [...STUDENT_DESTINATIONS, ...TEACHER_DESTINATIONS];
}

/** Cari ünvana uyğun bölmənin `href`-i; uyğun yoxdursa `null`.
 *  Tam yol da (`/masterai/web/chat.html`), təkcə fayl adı da qəbul
 *  edilir — səhifələr həm `file://`, həm serverdən açıla bilər. */
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
    const icon = document.createElement('span');
    icon.className = 'bottom-nav__icon';
    icon.textContent = destination.icon;
    icon.setAttribute('aria-hidden', 'true');
    node.append(icon);
  }
  const label = document.createElement('span');
  label.textContent = destination.label;
  node.append(label);
  return node;
}

/**
 * Üst zolağı və mobil alt paneli qurur.
 *
 * @param {object} options
 * @param {HTMLElement} options.bar — üst zolaq konteyneri
 * @param {HTMLElement} options.bottom — alt panel konteyneri
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
  brand.href = destinations[0].href;
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
  const avatar = document.createElement('span');
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
