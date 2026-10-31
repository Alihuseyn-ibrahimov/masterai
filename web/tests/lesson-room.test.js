import { test, describe } from 'node:test';
import assert from 'node:assert/strict';

import { connectionLabel, initials, orderTiles, roleOf } from '../assets/js/lesson-room.js';

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
