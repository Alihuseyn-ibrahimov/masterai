import { test, describe } from 'node:test';
import assert from 'node:assert/strict';

import { activeHref, allDestinations, destinationsFor, shortLabel } from '../assets/js/nav.js';

describe('destinationsFor', () => {
  test('tələbə öz bölmələrini görür', () => {
    const hrefs = destinationsFor({ is_teacher: false }).map((d) => d.href);
    assert.deepEqual(hrefs, ['chatlar.html', 'tapsiriqlar.html', 'tarixce.html', 'profil.html']);
  });

  test('müəllim öz bölmələrini görür', () => {
    const hrefs = destinationsFor({ is_teacher: true }).map((d) => d.href);
    assert.deepEqual(hrefs,
      ['muellim.html', 'chatlar.html', 'sessiyalar.html', 'hesabatlar.html', 'profil.html']);
  });

  test('MÜƏLLİMDƏ DƏ çat bölməsi var', () => {
    /* REAL BOŞLUQ İDİ (istifadəçi tapdı): müəllim naviqasiyasında çat
       yox idi, halbuki `hesabatlar.html` tapşırıq təyin etmək üçün çat
       TƏLƏB EDİR («əvvəlcə qrup çatına üzv olun»). Yəni təzə müəllim
       hesabı ev tapşırığı təyin edə bilmirdi - çat siyahısına çatmaq
       yolu yox idi. */
    const hrefs = destinationsFor({ is_teacher: true }).map((d) => d.href);
    assert.ok(hrefs.includes('chatlar.html'));
  });

  test('istifadəçi məlum deyilsə tələbə bölmələri (təhlükəsiz defolt)', () => {
    assert.equal(destinationsFor(null)[0].href, 'chatlar.html');
    assert.equal(destinationsFor(undefined)[0].href, 'chatlar.html');
  });

  test('hər rolda ən çox 5 bölmə - mobil alt panelə sığmalıdır', () => {
    /* Hədd 4-dən 5-ə qaldırıldı, çünki müəllimə çat bölməsi LAZIMDIR.
       Sığdığı GÜMAN EDİLMƏDİ, ÖLÇÜLDÜ: 390px-də 5 bölmənin hər biri
       78px xana alır və bütün etiketlər bir sətirdə sığır. 360px-də
       yalnız «Sual bankları» iki sətrə düşürdü - ona görə qısa mobil
       etiket mexanizmi əlavə olundu (aşağıdakı testlərə bax). */
    assert.ok(destinationsFor({ is_teacher: false }).length <= 5);
    assert.ok(destinationsFor({ is_teacher: true }).length <= 5);
  });

  test('uzun etiketin qısa mobil variantı var', () => {
    /* Alt paneldə xana 320px-lik telefonda ~64px olur. 10 simvoldan
       uzun etiket iki sətrə düşüb sıranı əyir. */
    const tooLong = allDestinations().filter((d) => shortLabel(d).length > 10);
    assert.deepEqual(tooLong, [], 'qısa etiketi olmayan uzun bölmə');
  });

  test('qısa etiket verilməyibsə adi etiket işlədilir', () => {
    assert.equal(shortLabel({ label: 'Profil' }), 'Profil');
    assert.equal(shortLabel({ label: 'Sual bankları', short: 'Banklar' }), 'Banklar');
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
