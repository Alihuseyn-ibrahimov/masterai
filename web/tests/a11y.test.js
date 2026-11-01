import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const read = (path) => readFileSync(new URL(`../${path}`, import.meta.url), 'utf8');

/* axe-core yoxlamasında (2026-11-01) tapılanlar geri qayıtmasın. */

test('hər qorunan səhifəyə «Məzmuna keç» linki qoşulur', () => {
  const shell = read('assets/js/page-shell.js');
  assert.match(shell, /mountSkipLink\(\);/);
  assert.match(shell, /'Məzmuna keç'/);
  assert.match(read('index.html'), /<a class="skip-link" href="#main">/);
  assert.match(read('assets/css/base.css'), /\.skip-link:focus \{ transform: none; \}/);
});

test('mətn içindəki link altdan xətlidir (yalnız rənglə seçilmir)', () => {
  assert.match(read('assets/css/base.css'), /:where\(p, li\) > a:not\(\.btn\) \{ text-decoration: underline;/);
});

test('basılı əsas düymə öz fonunu itirmir', () => {
  const css = read('assets/css/components.css');
  assert.doesNotMatch(css, /^\.btn\[aria-pressed="true"\]/m);
  assert.match(css, /\.btn:not\(\.btn--primary\)\[aria-pressed="true"\]/);
});

test('qazanılmamış nişanda bütün kart sönmür, yalnız ikon', () => {
  const page = read('nailiyyetler.html');
  assert.doesNotMatch(page, /card\.style\.opacity/);
  assert.match(page, /card--locked/);
});
