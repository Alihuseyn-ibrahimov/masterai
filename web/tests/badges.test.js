import { test, describe } from 'node:test';
import assert from 'node:assert/strict';

import { BADGES, describeBadge, sortBadges } from '../assets/js/badges.js';

describe('nişan kataloqu', () => {
  test('backend-dəki beş nişan var', () => {
    assert.deepEqual(
      BADGES.map((b) => b.key),
      ['ilk_addim', 'yuz_faiz', 'fenn_ustasi', 'suretli_eqli', 'silsile_5'],
    );
  });

  test('hər nişanın adı, ikonu və meyarı var', () => {
    for (const badge of BADGES) {
      assert.ok(badge.label && badge.icon && badge.criteria, badge.key);
    }
  });
});

describe('describeBadge', () => {
  test('qazanılmış nişanı təsvir edir', () => {
    const badge = describeBadge({ badge_type: 'yuz_faiz', earned: true, earned_at: '2026-09-01' });
    assert.equal(badge.label, 'Yüz faiz');
    assert.equal(badge.earned, true);
    assert.equal(badge.earnedAt, '2026-09-01');
  });

  test('naməlum nişanda ekran boş qalmır', () => {
    // Backend yeni nişan əlavə edərsə köhnə frontend sınmamalıdır.
    const badge = describeBadge({ badge_type: 'yeni_nisan', earned: false });
    assert.equal(badge.label, 'yeni_nisan');
    assert.equal(badge.icon, '🏅');
  });

  test('etibarsız sətir sındırmır', () => {
    assert.doesNotThrow(() => describeBadge(null));
    assert.equal(describeBadge(null).earned, false);
  });
});

describe('sortBadges', () => {
  test('qazanılanlar əvvəldə', () => {
    const sorted = sortBadges([
      { badge_type: 'ilk_addim', earned: false },
      { badge_type: 'yuz_faiz', earned: true },
    ]);
    assert.equal(sorted[0].key, 'yuz_faiz');
  });

  test('boş girişdə boş siyahı', () => {
    assert.deepEqual(sortBadges(null), []);
  });
});
