import { test } from 'node:test';
import assert from 'node:assert/strict';

import { createLessonRecorder, extensionFor, pickMimeType } from '../assets/js/lesson-recorder.js';

test('pickMimeType ilk dəstəklənən formatı seçir', () => {
  assert.equal(pickMimeType((t) => t === 'audio/mp4'), 'audio/mp4');
  assert.equal(pickMimeType(() => true), 'audio/webm;codecs=opus');
  assert.equal(pickMimeType(() => false), '');
  assert.equal(pickMimeType(undefined), '');
  assert.equal(pickMimeType(() => { throw new Error('x'); }), '');
});

test('extensionFor serverin qəbul etdiyi uzantını verir', () => {
  assert.equal(extensionFor('audio/webm;codecs=opus'), '.webm');
  assert.equal(extensionFor('audio/ogg;codecs=opus'), '.ogg');
  assert.equal(extensionFor('audio/mp4'), '.m4a');
  assert.equal(extensionFor(''), '.webm');
});

class FakeRecorder {
  static isTypeSupported(t) { return t === 'audio/webm'; }
  static all = [];
  constructor(stream, options) {
    this.options = options;
    this.state = 'inactive';
    this.listeners = {};
    FakeRecorder.all.push(this);
  }
  addEventListener(name, fn, opts) {
    (this.listeners[name] ||= []).push({ fn, once: opts && opts.once });
  }
  fire(name, event) {
    const list = this.listeners[name] || [];
    this.listeners[name] = list.filter((l) => !l.once);
    list.forEach((l) => l.fn(event));
  }
  start() { this.state = 'recording'; }
  stop() {
    this.state = 'inactive';
    this.fire('dataavailable', { data: new Blob(['səs']) });
    this.fire('stop');
  }
}

function harness(upload) {
  FakeRecorder.all = [];
  const timers = [];
  const recorder = createLessonRecorder({
    stream: {}, Recorder: FakeRecorder, upload, firstSeq: 3,
    setTimer: (fn) => { timers.push(fn); return timers.length; }, clearTimer: () => {},
  });
  return { recorder, timers };
}

test('hər seqment ayrıca, ardıcıl nömrə ilə göndərilir', async () => {
  const sent = [];
  const { recorder, timers } = harness(async (blob, seq, ext) => { sent.push([seq, ext]); });
  recorder.start();
  timers[0]();          // 5 dəqiqə keçdi: köhnə hissə bağlanır, yenisi açılır
  assert.equal(FakeRecorder.all.length, 2);
  assert.equal(FakeRecorder.all[1].state, 'recording');
  await recorder.stop();
  assert.deepEqual(sent, [[3, '.webm'], [4, '.webm']]);
  assert.equal(recorder.nextSeq, 5);
  assert.equal(FakeRecorder.all[0].options.mimeType, 'audio/webm');
});

test('uğursuz göndəriş bir dəfə təkrarlanır, sonra sayılır', async () => {
  let calls = 0;
  const states = [];
  FakeRecorder.all = [];
  const recorder = createLessonRecorder({
    stream: {}, Recorder: FakeRecorder,
    upload: async () => { calls += 1; throw new Error('şəbəkə'); },
    onChange: (s) => states.push(s), setTimer: () => 0, clearTimer: () => {},
  });
  recorder.start();
  await recorder.stop();
  assert.equal(calls, 2);
  assert.equal(states.at(-1).failed, 1);
  assert.equal(states.at(-1).recording, false);
});
