import test from 'node:test';
import assert from 'node:assert/strict';
import { createAutosave } from '../assets/js/note-autosave.js';

function fakeTimers() {
  const timers = new Map();
  let id = 0;
  return {
    setTimer: (fn) => { id += 1; timers.set(id, fn); return id; },
    clearTimer: (t) => timers.delete(t),
    fire: async () => {
      const fns = [...timers.values()];
      timers.clear();
      for (const fn of fns) await fn();
    },
    get count() { return timers.size; },
  };
}

test('yazmaq dayananda bir dəfə, son mətnlə saxlanır', async () => {
  const t = fakeTimers();
  const sent = [];
  const states = [];
  const a = createAutosave({ save: async (x) => sent.push(x), onState: (s) => states.push(s), ...t });
  a.schedule('M');
  a.schedule('Ma');
  a.schedule('Maddə');
  assert.equal(t.count, 1);
  await t.fire();
  assert.deepEqual(sent, ['Maddə']);
  assert.equal(states.at(-1), 'saved');
});

test('dəyişməyən mətn göndərilmir', async () => {
  const t = fakeTimers();
  const sent = [];
  const a = createAutosave({ save: async (x) => sent.push(x), initial: 'köhnə', ...t });
  a.schedule('köhnə');
  await t.fire();
  assert.deepEqual(sent, []);
});

test('saxlama gedərkən yazılan mətn sonra ayrıca göndərilir', async () => {
  const t = fakeTimers();
  const sent = [];
  let release;
  const a = createAutosave({
    save: (x) => { sent.push(x); return new Promise((r) => { release = r; }); },
    ...t,
  });
  a.schedule('bir');
  const first = t.fire();
  await Promise.resolve();
  a.schedule('bir iki');
  release();
  await first;
  const second = t.fire();
  await Promise.resolve();
  release();
  await second;
  assert.deepEqual(sent, ['bir', 'bir iki']);
  assert.equal(a.saved, 'bir iki');
});

test('xəta mətni itirmir, flush yenidən göndərir', async () => {
  const t = fakeTimers();
  const sent = [];
  let fail = true;
  const states = [];
  const a = createAutosave({
    save: async (x) => { sent.push(x); if (fail) throw new Error('şəbəkə'); },
    onState: (s) => states.push(s),
    ...t,
  });
  a.schedule('vacib');
  await t.fire();
  assert.equal(states.at(-1), 'error');
  fail = false;
  await a.flush();
  assert.deepEqual(sent, ['vacib', 'vacib']);
  assert.equal(states.at(-1), 'saved');
});

test('flush gözləyən taymeri ləğv edib dərhal saxlayır', async () => {
  const t = fakeTimers();
  const sent = [];
  const a = createAutosave({ save: async (x) => sent.push(x), ...t });
  a.schedule('çıxıram');
  await a.flush();
  assert.deepEqual(sent, ['çıxıram']);
  assert.equal(t.count, 0);
});
