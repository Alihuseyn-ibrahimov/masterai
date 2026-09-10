/* Sprite ikonları: `assets/icons.svg` (Tabler Icons, MIT).
 *
 * NİYƏ: əvvəl naviqasiya, nişanlar və xəta ekranları EMOJİ işlədirdi.
 * Emoji hər platformada fərqli görünür (Windows/Android/iOS ayrı-ayrı
 * rəsmlər), rəngi `currentColor` ilə idarə olunmur, ölçüsü şrift
 * ölçüsündən asılıdır və ekran oxuyucusu onu mətn kimi oxuyur
 * («ağac tinginin şəkli» kimi). Tətbiq ondan oyuncaq təsiri bağışlayır.
 *
 * Sprite artıq mövcud idi, sadəcə JS ona bağlanmamışdı; HTML
 * səhifələr işlədirdi, tətbiqin öz çərçivəsi isə yox.
 */

const SPRITE = 'assets/icons.svg';
const SVG_NS = 'http://www.w3.org/2000/svg';
const XLINK_NS = 'http://www.w3.org/1999/xlink';

/**
 * Bəzək ikonu qaytarır (`aria-hidden`); mənası yanındakı mətndədir.
 *
 * @param {string} name - sprite id-si, `i-` prefiksi olmadan
 * @param {string} [className] - əlavə sinif
 * @returns {SVGElement}
 */
export function createIcon(name, className) {
  const svg = document.createElementNS(SVG_NS, 'svg');
  svg.setAttribute('class', className ? `icon ${className}` : 'icon');
  svg.setAttribute('aria-hidden', 'true');
  svg.setAttribute('focusable', 'false');
  const use = document.createElementNS(SVG_NS, 'use');
  const href = `${SPRITE}#i-${name}`;
  use.setAttribute('href', href);
  // Köhnə Safari `href`-i yox, `xlink:href`-i oxuyur.
  use.setAttributeNS(XLINK_NS, 'xlink:href', href);
  svg.append(use);
  return svg;
}
