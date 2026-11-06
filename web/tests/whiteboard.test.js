import { test, describe } from 'node:test';
import assert from 'node:assert/strict';

import {
  applyMessage, createBoardState, decodeMessage, drawSegment, encodeMessage,
  LOGICAL_HEIGHT, LOGICAL_WIDTH, makeClear, makeSegment, normalize, replay,
} from '../assets/js/whiteboard.js';

describe('normalize', () => {
  test('rect küncündəki nöqtə 0,0 verir', () => {
    const p = normalize(10, 20, { left: 10, top: 20, width: 100, height: 50 });
    assert.deepEqual(p, { x: 0, y: 0 });
  });

  test('rect-dən kənar nöqtə [0,1]-ə kəsilir', () => {
    const p = normalize(-5, 999, { left: 0, top: 0, width: 100, height: 100 });
    assert.deepEqual(p, { x: 0, y: 1 });
  });
});

describe('encodeMessage / decodeMessage', () => {
  test('seqment dəyirmi gedib-gəlir', () => {
    const seg = makeSegment(0.1, 0.2, 0.3, 0.4, '#ff0000');
    assert.deepEqual(decodeMessage(encodeMessage(seg)), seg);
  });

  test('pozuq bayt null qaytarır', () => {
    assert.equal(decodeMessage(new TextEncoder().encode('{bad')), null);
  });

  test('naməlum tip null qaytarır', () => {
    assert.equal(decodeMessage(encodeMessage({ t: 'ping' })), null);
  });
});

describe('createBoardState / applyMessage', () => {
  test('seqmentlər toplanır', () => {
    const state = createBoardState();
    applyMessage(state, makeSegment(0, 0, 1, 1, '#000'));
    applyMessage(state, makeSegment(0, 0, 0.5, 0.5, '#000'));
    assert.equal(state.segments.length, 2);
  });

  test('clear hamısını silir', () => {
    const state = createBoardState();
    applyMessage(state, makeSegment(0, 0, 1, 1, '#000'));
    applyMessage(state, makeClear());
    assert.equal(state.segments.length, 0);
  });
});

function fakeCtx() {
  const calls = [];
  return {
    calls,
    set strokeStyle(v) { calls.push(['strokeStyle', v]); },
    set lineWidth(v) { calls.push(['lineWidth', v]); },
    set lineCap(v) { calls.push(['lineCap', v]); },
    beginPath: () => calls.push(['beginPath']),
    moveTo: (x, y) => calls.push(['moveTo', x, y]),
    lineTo: (x, y) => calls.push(['lineTo', x, y]),
    stroke: () => calls.push(['stroke']),
    clearRect: (...a) => calls.push(['clearRect', ...a]),
  };
}

describe('drawSegment', () => {
  test('normallaşdırılmış koordinatları LOGICAL_* ölçüsünə köçürür', () => {
    const ctx = fakeCtx();
    drawSegment(ctx, makeSegment(0, 0.5, 1, 0, '#abc'));
    assert.deepEqual(ctx.calls.find((c) => c[0] === 'moveTo'), ['moveTo', 0, LOGICAL_HEIGHT / 2]);
    assert.deepEqual(ctx.calls.find((c) => c[0] === 'lineTo'), ['lineTo', LOGICAL_WIDTH, 0]);
  });

  test('rəng boşdursa defolt tündə çəkilir', () => {
    const ctx = fakeCtx();
    drawSegment(ctx, { t: 'seg', x0: 0, y0: 0, x1: 0, y1: 0 });
    assert.deepEqual(ctx.calls.find((c) => c[0] === 'strokeStyle'), ['strokeStyle', '#1a1a1a']);
  });
});

describe('replay', () => {
  test('əvvəlcə təmizləyir, sonra saxlanmış seqmentləri çəkir', () => {
    const ctx = fakeCtx();
    const state = createBoardState();
    applyMessage(state, makeSegment(0, 0, 1, 1, '#000'));
    applyMessage(state, makeSegment(0, 1, 1, 0, '#000'));
    replay(ctx, state);
    assert.deepEqual(ctx.calls[0], ['clearRect', 0, 0, LOGICAL_WIDTH, LOGICAL_HEIGHT]);
    assert.equal(ctx.calls.filter((c) => c[0] === 'stroke').length, 2);
  });
});
