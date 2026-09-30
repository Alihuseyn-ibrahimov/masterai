/* Sahib paneli - saf göstəriş funksiyaları (spec 2026-09-29 §3).
 *
 * Status sahəsi bazada `trial`/`active` qalır, «bitib» isə tarixdən
 * hesablanır (`is_open`). Panel bunu AYIRD ETMƏLİDİR: sınaq müddəti
 * keçmiş kurs «Sınaq» kimi göstərilsə, sahib onun bağlı olduğunu görməz.
 */

import { test, describe } from 'node:test';
import assert from 'node:assert/strict';

import {
  activityText,
  auditActionLabel,
  daysLeftText,
  inviteUrl,
  lastActivityText,
  profileLabel,
  seatsText,
  statusView,
} from '../assets/js/owner.js';

describe('statusView', () => {
  test('müddətsiz kurs', () => {
    assert.deepEqual(statusView({ status: 'owner', is_open: true }), { label: 'Müddətsiz', tone: 'neutral' });
  });

  test('açıq sınaq', () => {
    assert.deepEqual(statusView({ status: 'trial', is_open: true }), { label: 'Sınaq', tone: 'info' });
  });

  test('ödənilmiş', () => {
    assert.deepEqual(statusView({ status: 'active', is_open: true }), { label: 'Ödənilib', tone: 'success' });
  });

  test('dayandırılmış', () => {
    assert.deepEqual(statusView({ status: 'suspended', is_open: false }), { label: 'Dayandırılıb', tone: 'danger' });
  });

  test('müddəti keçmiş sınaq «Sınaq» yox, «Müddəti bitib» görünür', () => {
    assert.deepEqual(statusView({ status: 'trial', is_open: false }), { label: 'Müddəti bitib', tone: 'warning' });
    assert.deepEqual(statusView({ status: 'active', is_open: false }), { label: 'Müddəti bitib', tone: 'warning' });
  });
});

describe('daysLeftText', () => {
  test('müddətsiz', () => assert.equal(daysLeftText(null), 'Müddətsiz'));
  test('bitib', () => assert.equal(daysLeftText(0), 'Bitib'));
  test('gün sayı', () => assert.equal(daysLeftText(12), '12 gün qalıb'));
});

describe('seatsText', () => {
  test('limitli', () => assert.equal(seatsText(18, 30), '18 / 30'));
  test('limitsiz', () => assert.equal(seatsText(4, null), '4 / limitsiz'));
});

describe('activityText', () => {
  test('dörd göstərici', () => {
    assert.equal(
      activityText({ sessions: 3, question_sets: 2, answers: 140, messages: 25 }),
      '3 sessiya · 2 bank · 140 cavab · 25 mesaj',
    );
  });
});

describe('lastActivityText', () => {
  const now = new Date('2026-10-10T12:00:00Z');
  test('heç aktivlik yoxdur', () => assert.equal(lastActivityText(null, now), 'Aktivlik yoxdur'));
  test('bu gün', () => assert.equal(lastActivityText('2026-10-10T08:00:00+00:00', now), 'Bu gün'));
  test('dünən', () => assert.equal(lastActivityText('2026-10-09T08:00:00+00:00', now), 'Dünən'));
  test('gün əvvəl', () => assert.equal(lastActivityText('2026-10-01T12:00:00+00:00', now), '9 gün əvvəl'));
});

describe('inviteUrl', () => {
  test('qeydiyyat səhifəsinə, token kodlanmış', () => {
    assert.equal(
      inviteUrl('https://masterai.prdostu.com', 'a+b/c'),
      'https://masterai.prdostu.com/qeydiyyat.html?invite=a%2Bb%2Fc',
    );
  });
});

describe('etiketlər', () => {
  test('profil', () => {
    assert.equal(profileLabel('english'), 'İngilis dili');
    assert.equal(profileLabel('exam_prep'), 'İmtahana hazırlıq');
  });

  test('jurnal əməliyyatları', () => {
    assert.equal(auditActionLabel('payment'), 'Ödəniş');
    assert.equal(auditActionLabel('bilinmeyen'), 'bilinmeyen');
  });
});
