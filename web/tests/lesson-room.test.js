import { test, describe } from 'node:test';
import assert from 'node:assert/strict';

import { readFileSync } from 'node:fs';

import {
  connectionLabel, initials, orderTiles, roleOf, roomWaitState,
} from '../assets/js/lesson-room.js';

describe('initials', () => {
  test('ad və soyadın ilk hərfləri, Azərbaycan hərfləri ilə', () => {
    assert.equal(initials('əli həsənov'), 'ƏH');
    assert.equal(initials('İlkin'), 'İ');
    assert.equal(initials('Aynur Rəsul qızı Məmmədova'), 'AM');
  });
  test('boş ad', () => {
    assert.equal(initials('  '), '?');
    assert.equal(initials(null), '?');
  });
});

describe('roleOf', () => {
  test('yalnız açıq müəllim rolu müəllimdir', () => {
    assert.equal(roleOf('{"role": "teacher"}'), 'teacher');
    assert.equal(roleOf('{"role": "student"}'), 'student');
    assert.equal(roleOf(''), 'student');
    assert.equal(roleOf('xarab'), 'student');
  });
});

describe('orderTiles', () => {
  test('ekran → müəllim → özüm → digərləri ad üzrə', () => {
    const order = orderTiles([
      { id: 'v', name: 'Vəli', role: 'student' },
      { id: 'me', name: 'Zaur', role: 'student', local: true },
      { id: 't', name: 'Müəllim', role: 'teacher' },
      { id: 'a', name: 'Əli', role: 'student' },
      { id: 's', name: 'Müəllim', role: 'teacher', screen: true },
    ]).map((t) => t.id);
    assert.deepEqual(order, ['s', 't', 'me', 'a', 'v']);
  });
});

test('bağlantı mətni', () => {
  assert.equal(connectionLabel('reconnecting'), 'Bağlantı bərpa olunur…');
  assert.equal(connectionLabel('başqa'), 'başqa');
});

test('bitmiş dərs boş otaq yox, növbəti addım göstərir', () => {
  /* Auditdə tapılıb: bitmiş dərsin otağında yalnız «Dərs bitib.» var idi. */
  const ended = { id: 7, mode: 'online', status: 'ended' };
  const student = roomWaitState(ended, false);
  assert.equal(student.primary.href, 'dersim.html?id=7');
  assert.equal(student.canStart, false);
  const teacher = roomWaitState(ended, true);
  assert.equal(teacher.primary.href, 'dersim.html?id=7#text');
  assert.equal(teacher.canStart, true);
});

test('başlamamış və sinif dərsi', () => {
  const scheduled = { id: 3, mode: 'online', status: 'scheduled' };
  assert.equal(roomWaitState(scheduled, false).primary, null);
  assert.equal(roomWaitState(scheduled, false).canStart, false);
  assert.equal(roomWaitState(scheduled, true).canStart, true);
  const offline = roomWaitState({ id: 4, mode: 'offline', status: 'live' }, true);
  assert.equal(offline.canStart, false);
  assert.equal(offline.primary.href, 'dersim.html?id=4');
});

test('gözləmə ekranının ikonları sprite-da var', () => {
  const sprite = readFileSync(new URL('../assets/icons.svg', import.meta.url), 'utf8');
  for (const lesson of [{ mode: 'online', status: 'ended' }, { mode: 'online', status: 'scheduled' }, { mode: 'offline' }]) {
    const { icon } = roomWaitState({ id: 1, ...lesson }, true);
    assert.ok(sprite.includes(`id="i-${icon}"`), icon);
  }
});
