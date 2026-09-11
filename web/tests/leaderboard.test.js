import assert from 'node:assert/strict';
import { test, describe } from 'node:test';

import {
  emptyLeaderboardText,
  leaderboardRow,
  leaderboardRows,
} from '../assets/js/leaderboard.js';

const row = (over = {}) => ({
  user_id: 7, display_name: 'Nərmin', homework_score: 3,
  live_score: 2, total_score: 5, rank: 1, ...over,
});

describe('leaderboardRow', () => {
  test('komponentləri mətndə göstərir', () => {
    assert.equal(leaderboardRow(row(), 1).breakdown, 'Ev tapşırığı 3 · Canlı sessiya 2');
  });

  test('sıfır komponent də GÖSTƏRİLİR', () => {
    // Gizlətsək, tələbə hansı sahədə geridə qaldığını bilməzdi.
    const r = leaderboardRow(row({ live_score: 0, total_score: 3 }), 1);
    assert.equal(r.breakdown, 'Ev tapşırığı 3 · Canlı sessiya 0');
  });

  test('öz sətrini işarələyir', () => {
    assert.equal(leaderboardRow(row(), 7).isMe, true);
    assert.equal(leaderboardRow(row(), 8).isMe, false);
  });

  test('çatışmayan sahələr 0 sayılır', () => {
    // Köhnə keşdən gələn cavabda yeni sahələr olmaya bilər - səhifə
    // `NaN` göstərməməlidir.
    const r = leaderboardRow({ user_id: 7, display_name: 'A', rank: 1 }, 7);
    assert.equal(r.total, 0);
    assert.equal(r.breakdown, 'Ev tapşırığı 0 · Canlı sessiya 0');
  });
});

describe('leaderboardRows', () => {
  test('server sıralamasına toxunmur', () => {
    // Təkrar sıralamaq iki mənbə yaradardı; `rank` serverdən gəlir.
    const rows = leaderboardRows(
      [row({ rank: 1, total_score: 5 }), row({ user_id: 8, display_name: 'Rəşad', rank: 2, total_score: 9 })],
      7,
    );
    assert.deepEqual(rows.map((r) => r.name), ['Nərmin', 'Rəşad']);
    assert.deepEqual(rows.map((r) => r.rank), [1, 2]);
  });

  test('boş siyahı sınmır', () => {
    assert.deepEqual(leaderboardRows(null, 1), []);
    assert.deepEqual(leaderboardRows([], 1), []);
  });
});

describe('emptyLeaderboardText', () => {
  test('üzv yoxdursa', () => {
    assert.match(emptyLeaderboardText([]), /tələbə yoxdur/);
  });

  test('üzv var, xal yoxdursa - FƏRQLİ mətn', () => {
    // İki hal fərqli səbəblərdir; eyni mətn yanıldıcı olardı.
    assert.match(emptyLeaderboardText([row({ total_score: 0 })]), /Hələ xal yoxdur/);
  });

  test('xal varsa mətn yoxdur', () => {
    assert.equal(emptyLeaderboardText([row()]), '');
  });
});
