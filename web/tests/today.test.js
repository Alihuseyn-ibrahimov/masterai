import { test, describe } from 'node:test';
import assert from 'node:assert/strict';

import {
  XP_PER_CORRECT, WEEKLY_GOAL_XP, ageText, earnedCount, freshSummary, goalPercent, greeting,
  heroAction, heroLesson, teacherHeroAction, nextBadge, nextHomework, streakDays, xpSince,
} from '../assets/js/today.js';

const entry = (date, score = 1) => ({ date, score, total_questions: 5 });

describe('streakDays', () => {
  test('bu gün bitən ardıcıl günləri sayır', () => {
    const rows = [entry('2026-10-31'), entry('2026-10-30'), entry('2026-10-29'), entry('2026-10-26')];
    assert.equal(streakDays(rows, '2026-10-31'), 3);
  });

  test('dünən bitən seriya səhər sıfırlanmır', () => {
    /* Tələbə dünən məşq edib, bu gün hələ etməyib - seriyanı
       sıfır göstərmək haqsız olar. */
    assert.equal(streakDays([entry('2026-10-30'), entry('2026-10-29')], '2026-10-31'), 2);
  });

  test('iki gün boşluq seriyanı bitirir', () => {
    assert.equal(streakDays([entry('2026-10-29')], '2026-10-31'), 0);
  });

  test('eyni gündə bir neçə nəticə bir gün sayılır', () => {
    assert.equal(streakDays([entry('2026-10-31T09:00:00Z'), entry('2026-10-31T18:00:00Z')], '2026-10-31'), 1);
  });

  test('boş və ya yararsız data sıfırdır', () => {
    assert.equal(streakDays([], '2026-10-31'), 0);
    assert.equal(streakDays(null, '2026-10-31'), 0);
    assert.equal(streakDays([{ date: 'dünən' }], '2026-10-31'), 0);
  });
});

describe('xpSince', () => {
  test('yalnız pəncərədəki düzgün cavablar sayılır', () => {
    const rows = [entry('2026-10-31', 4), entry('2026-10-25', 3), entry('2026-10-24', 9)];
    assert.equal(xpSince(rows, '2026-10-31', 1), 4 * XP_PER_CORRECT);
    // 7 gün = 25-31 oktyabr; 24-ü düşmür.
    assert.equal(xpSince(rows, '2026-10-31', 7), 7 * XP_PER_CORRECT);
  });

  test('gələcək tarixli sətir sayılmır', () => {
    assert.equal(xpSince([entry('2026-11-02', 5)], '2026-10-31', 7), 0);
  });
});

describe('goalPercent', () => {
  test('faiz 0-100 arasında qalır', () => {
    assert.equal(goalPercent(WEEKLY_GOAL_XP / 2), 50);
    assert.equal(goalPercent(WEEKLY_GOAL_XP * 3), 100);
    assert.equal(goalPercent(-5), 0);
    assert.equal(goalPercent(10, 0), 0);
  });
});

describe('heroLesson / heroAction', () => {
  const live = { id: 2, mode: 'online', status: 'live' };
  const offlineLive = { id: 4, mode: 'offline', status: 'live' };
  const next = { id: 3, mode: 'online', status: 'scheduled' };

  test('canlı dərs gələcəkdən üstündür', () => {
    assert.deepEqual(heroLesson({ live: [live], upcoming: [next] }), { kind: 'live', lesson: live });
    assert.deepEqual(heroLesson({ live: [], upcoming: [next] }), { kind: 'next', lesson: next });
    assert.equal(heroLesson({ live: [], upcoming: [] }), null);
  });

  test('canlı onlayn dərs otağa aparır', () => {
    assert.deepEqual(heroAction({ kind: 'live', lesson: live }),
      { label: 'Qoşul', href: 'dars.html?id=2', primary: true });
  });

  test('sinif dərsi və gələcək dərs otağa APARMIR', () => {
    /* Auditdə tapılıb: planlaşdırılmış dərsdə «Dərs otağı» düyməsi
       görünürdü. Sinif dərsində davamiyyət QR iləyədir. */
    assert.equal(heroAction({ kind: 'live', lesson: offlineLive }).href, 'dersim.html?id=4');
    const action = heroAction({ kind: 'next', lesson: next });
    assert.equal(action.href, 'dersim.html?id=3');
    assert.equal(action.primary, false);
    assert.equal(heroAction(null), null);
  });
});

describe('nextHomework / nextBadge', () => {
  test('bitməmiş ilk tapşırıq', () => {
    const rows = [{ status: 'tamamlanıb' }, { status: 'davam edir', title: 'A' }, { status: 'gözləyir' }];
    assert.equal(nextHomework(rows).title, 'A');
    assert.equal(nextHomework([{ status: 'tamamlanıb' }]), null);
  });

  test('ilk qazanılmamış nişan və say', () => {
    const badges = [{ key: 'a', earned: true }, { key: 'b', earned: false }, { key: 'c', earned: false }];
    assert.equal(nextBadge(badges).key, 'b');
    assert.equal(earnedCount(badges), 1);
    assert.equal(nextBadge([{ earned: true }]), null);
  });
});

describe('greeting', () => {
  test('adın birinci sözü', () => {
    assert.equal(greeting('Əli Məmmədov'), 'Salam, Əli');
    assert.equal(greeting('  '), 'Salam');
    assert.equal(greeting(null), 'Salam');
  });
});

describe('freshSummary', () => {
  const s = (id, published_at) => ({ id, title: `K${id}`, published_at });

  test('son 14 gündən ən yenisini seçir', () => {
    const rows = [s(1, '2026-10-20T08:00:00+00:00'), s(2, '2026-10-30T09:00:00+00:00'), s(3, '2026-10-30T07:00:00+00:00')];
    const got = freshSummary(rows, '2026-11-01');
    assert.equal(got.summary.id, 2);
    assert.equal(got.ageDays, 2);
  });

  test('köhnə, dərc olunmamış və gələcək tarixli konspekt göstərilmir', () => {
    const rows = [s(1, '2026-10-01T08:00:00+00:00'), s(2, null), s(3, '2026-11-05T08:00:00+00:00')];
    assert.equal(freshSummary(rows, '2026-11-01'), null);
    assert.equal(freshSummary(undefined, '2026-11-01'), null);
  });

  test('sərhəd: 13 gün əvvəl görünür, 14 gün əvvəl yox', () => {
    assert.equal(freshSummary([s(1, '2026-10-19T08:00:00+00:00')], '2026-11-01').ageDays, 13);
    assert.equal(freshSummary([s(1, '2026-10-18T08:00:00+00:00')], '2026-11-01'), null);
  });
});

describe('ageText', () => {
  test('gün sayını sözə çevirir', () => {
    assert.equal(ageText(0), 'Bu gün');
    assert.equal(ageText(1), 'Dünən');
    assert.equal(ageText(5), '5 gün əvvəl');
  });
});

describe('teacherHeroAction', () => {
  const now = new Date('2026-11-05T09:30:00Z');
  const at = (iso, extra = {}) => ({ id: 7, mode: 'online', status: 'scheduled', starts_at: iso, ...extra });

  test('canlı onlayn dərs birbaşa otağa', () => {
    const action = teacherHeroAction({ kind: 'live', lesson: at('2026-11-05T09:00:00Z', { status: 'live' }) }, now);
    assert.deepEqual(action, { label: 'Dərs otağına gir', href: 'dars.html?id=7', primary: true });
  });

  test('yaxın onlayn dərs bir kliklə başlayır', () => {
    /* Əvvəl: Dərslər → başlat → «Dərs otağı» → «Otağa gir». */
    const soon = teacherHeroAction({ kind: 'next', lesson: at('2026-11-05T10:30:00Z') }, now);
    assert.deepEqual(soon, { label: 'Başlat və gir', href: 'dars.html?id=7&start=1', primary: true });
    const late = teacherHeroAction({ kind: 'next', lesson: at('2026-11-05T09:00:00Z') }, now);
    assert.equal(late.href, 'dars.html?id=7&start=1');
  });

  test('uzaq dərs və sinif dərsi «Dərslər»ə aparır', () => {
    /* Günlər əvvəl başlatmaq sinfə vaxtsız «Dərs başladı» yazardı. */
    assert.equal(teacherHeroAction({ kind: 'next', lesson: at('2026-11-05T10:31:00Z') }, now).href, 'dersler.html');
    const offline = at('2026-11-05T09:00:00Z', { mode: 'offline', status: 'live' });
    assert.deepEqual(teacherHeroAction({ kind: 'live', lesson: offline }, now),
      { label: 'Dərsi idarə et', href: 'dersler.html', primary: true });
    assert.equal(teacherHeroAction(null, now), null);
  });
});
