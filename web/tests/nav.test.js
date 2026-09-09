import { test, describe } from 'node:test';
import assert from 'node:assert/strict';

import { activeHref, allDestinations, destinationsFor } from '../assets/js/nav.js';

describe('destinationsFor', () => {
  test('tələbə öz bölmələrini görür', () => {
    const hrefs = destinationsFor({ is_teacher: false }).map((d) => d.href);
    assert.deepEqual(hrefs, ['chatlar.html', 'tapsiriqlar.html', 'tarixce.html', 'profil.html']);
  });

  test('müəllim öz bölmələrini görür', () => {
    const hrefs = destinationsFor({ is_teacher: true }).map((d) => d.href);
    assert.deepEqual(hrefs, ['muellim.html', 'sessiyalar.html', 'hesabatlar.html', 'profil.html']);
  });

  test('istifadəçi məlum deyilsə tələbə bölmələri (təhlükəsiz defolt)', () => {
    assert.equal(destinationsFor(null)[0].href, 'chatlar.html');
    assert.equal(destinationsFor(undefined)[0].href, 'chatlar.html');
  });

  test('hər rolda ən çox 4 bölmə — mobil alt panelə sığmalıdır', () => {
    assert.ok(destinationsFor({ is_teacher: false }).length <= 4);
    assert.ok(destinationsFor({ is_teacher: true }).length <= 4);
  });

  test('hər bölmənin etiketi, ikonu və uyğunluq siyahısı var', () => {
    for (const destination of allDestinations()) {
      assert.ok(destination.label, `${destination.href}: etiket yoxdur`);
      assert.ok(destination.icon, `${destination.href}: ikon yoxdur`);
      assert.ok(destination.matches.includes(destination.href),
        `${destination.href}: öz səhifəsində aktiv olmalıdır`);
    }
  });
});

describe('activeHref', () => {
  const student = destinationsFor({ is_teacher: false });

  test('cari səhifəni tanıyır', () => {
    assert.equal(activeHref(student, 'chatlar.html'), 'chatlar.html');
  });

  test('tam yolda da işləyir', () => {
    // Səhifələr həm `file://`, həm serverdən açıla bilər.
    assert.equal(activeHref(student, '/masterai/web/tarixce.html'), 'tarixce.html');
    assert.equal(activeHref(student, 'C:/Quantum/masterai/web/profil.html'), 'profil.html');
  });

  test('DETAL səhifəsi öz bölməsini işıqlandırır', () => {
    // `chat.html` ayrıca bölmə deyil — Çatlar bölməsinin içidir.
    // Əks halda istifadəçi çata girəndə naviqasiyada "harda olduğunu"
    // itirir.
    assert.equal(activeHref(student, 'chat.html'), 'chatlar.html');
  });

  test('sorğu parametri aktivliyi pozmur', () => {
    assert.equal(activeHref(student, 'chat.html?id=7'), 'chatlar.html');
  });

  test('naməlum səhifədə heç nə aktiv deyil', () => {
    assert.equal(activeHref(student, 'giris.html'), null);
    assert.equal(activeHref(student, ''), null);
    assert.equal(activeHref(student, null), null);
  });

  test('müəllim səhifəsi tələbə bölmələrində aktiv sayılmır', () => {
    assert.equal(activeHref(student, 'muellim.html'), null);
  });
});
