import { test, describe } from 'node:test';
import assert from 'node:assert/strict';

import { formatLessonTime, groupLessons, localInputToIso } from '../assets/js/lessons.js';

const lesson = (id, starts_at, status = 'scheduled', duration_min = 60) => ({ id, starts_at, status, duration_min });

describe('groupLessons', () => {
  const now = Date.parse('2026-11-03T12:00:00Z');

  test('canlı, gələcək və keçmiş ayrılır', () => {
    const groups = groupLessons([
      lesson(1, '2026-11-03T11:30:00Z', 'live'),
      lesson(2, '2026-11-05T10:00:00Z'),
      lesson(3, '2026-11-04T10:00:00Z'),
      lesson(4, '2026-11-01T10:00:00Z', 'ended'),
      lesson(5, '2026-11-02T10:00:00Z', 'ended'),
    ], now);
    assert.deepEqual(groups.live.map((l) => l.id), [1]);
    assert.deepEqual(groups.upcoming.map((l) => l.id), [3, 2]);
    assert.deepEqual(groups.past.map((l) => l.id), [5, 4]);
  });

  test('vaxtı keçmiş, amma başladılmamış dərs keçmişə düşür', () => {
    const groups = groupLessons([lesson(1, '2026-11-03T09:00:00Z', 'scheduled', 60)], now);
    assert.deepEqual(groups.past.map((l) => l.id), [1]);
  });

  test('davam edən vaxtdakı planlaşdırılmış dərs hələ gələcəkdədir', () => {
    const groups = groupLessons([lesson(1, '2026-11-03T11:30:00Z', 'scheduled', 90)], now);
    assert.deepEqual(groups.upcoming.map((l) => l.id), [1]);
  });

  test('boş siyahı', () => {
    assert.deepEqual(groupLessons(null), { live: [], upcoming: [], past: [] });
  });
});

describe('vaxt', () => {
  test('yerli vaxt formatı', () => {
    const iso = new Date(2026, 10, 3, 9, 5).toISOString();
    assert.equal(formatLessonTime(iso), '3 noy, 09:05');
  });

  test('yararsız vaxt boş sətir verir', () => {
    assert.equal(formatLessonTime('x'), '');
  });

  test('datetime-local dəyəri ISO-ya çevrilir, boş dəyər null', () => {
    assert.equal(localInputToIso('2026-11-03T10:00'), new Date(2026, 10, 3, 10, 0).toISOString());
    assert.equal(localInputToIso(''), null);
  });
});
