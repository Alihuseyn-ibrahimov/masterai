import { test, describe } from 'node:test';
import assert from 'node:assert/strict';

import {
  formatLessonTime, groupLessons, lessonIcs, localInputToIso, startsInText,
} from '../assets/js/lessons.js';

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

test('startsInText: dəqiqə, saat, sabah, gün', () => {
  const now = new Date(2026, 10, 1, 9, 0).getTime();
  const at = (d, h, m) => new Date(2026, 10, d, h, m).toISOString();
  assert.equal(startsInText(at(1, 9, 35), now), '35 dəqiqə sonra');
  assert.equal(startsInText(at(1, 9, 0, 30), now + 1000), '');
  assert.equal(startsInText(at(1, 11, 0), now), '2 saat sonra');
  assert.equal(startsInText(at(1, 11, 10), now), '2 saat 10 dəq sonra');
  assert.equal(startsInText(at(2, 10, 0), now), 'sabah, 10:00');
  assert.equal(startsInText(at(4, 10, 0), now), '3 gün sonra');
  assert.equal(startsInText(at(1, 8, 0), now), '', 'keçmiş vaxt sayılmır');
  assert.equal(startsInText('pozuq', now), '');
});

test('startsInText: gecə yarısını keçən saatlar «sabah» sayılır', () => {
  const now = new Date(2026, 10, 1, 23, 0).getTime();
  assert.equal(startsInText(new Date(2026, 10, 2, 1, 30).toISOString(), now), 'sabah, 01:30');
});

test('lessonIcs: CRLF, UTC vaxt, 15 dəqiqəlik xatırlatma, xüsusi simvollar', () => {
  const ics = lessonIcs({
    id: 7, title: 'Konstitusiya; maddə 1, 2', starts_at: '2026-11-03T06:00:00Z',
    duration_min: 90, mode: 'online', chat_name: 'Qrup A',
  }, 'https://masterai.prdostu.com', Date.UTC(2026, 10, 1));
  const lines = ics.split('\r\n');
  assert.ok(!ics.replace(/\r\n/g, '').includes('\n'), 'yalnız CRLF');
  assert.ok(lines.includes('DTSTART:20261103T060000Z'));
  assert.ok(lines.includes('DTEND:20261103T073000Z'));
  assert.ok(lines.includes('DTSTAMP:20261101T000000Z'));
  assert.ok(lines.includes('SUMMARY:Konstitusiya\\; maddə 1\\, 2'));
  assert.ok(lines.includes('TRIGGER:-PT15M'));
  assert.ok(lines.includes('UID:lesson-7@masterai.prdostu.com'));
  assert.ok(lines.includes('URL:https://masterai.prdostu.com/dersim.html?id=7'));
  assert.ok(lines.includes('DESCRIPTION:Qrup A\\nOnlayn\\nhttps://masterai.prdostu.com/dersim.html?id=7'));
  assert.equal(lines[0], 'BEGIN:VCALENDAR');
});

test('lessonIcs: yararsız vaxt boş fayl verir', () => {
  assert.equal(lessonIcs({ id: 1, title: 'x', starts_at: 'yox' }, 'https://a'), '');
});
