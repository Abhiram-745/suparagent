import assert from 'node:assert/strict';
import { afterEach, test } from 'node:test';
import { api } from './api.ts';
import { charsLeftLabel, overLimitFields, profileDirty, profileFieldNames, profileHasContent, profileHint } from './business-profile.ts';

const originalFetch = globalThis.fetch;
afterEach(() => { globalThis.fetch = originalFetch; });

const profile = (fields = {}) => ({
  fields: { sells: '', audience: '', tone: '', links: '', hours: '', never_say: '', ...fields },
  hash: 'h', empty: true, updated_at: 0,
  limits: { sells: 600, audience: 400, tone: 200, links: 600, hours: 200, never_say: 600 },
  labels: { sells: 'What the business sells' },
});

test('fields show in form order and any new server field comes last', () => {
  const p = profile();
  assert.deepEqual(profileFieldNames(p), ['sells', 'audience', 'tone', 'links', 'hours', 'never_say']);
  p.fields.extra = '';
  assert.equal(profileFieldNames(p).at(-1), 'extra');
  assert.match(profileHint('tone'), /warm/);
  assert.equal(profileHint('nope'), '');
});

test('dirty ignores surrounding spaces and content check ignores blanks', () => {
  assert.equal(profileDirty({ sells: 'candles' }, { sells: ' candles ' }), false);
  assert.equal(profileDirty({ sells: 'candles' }, { sells: 'soap' }), true);
  assert.equal(profileDirty({}, { tone: 'warm' }), true);
  assert.equal(profileHasContent({ sells: '  ', tone: '' }), false);
  assert.equal(profileHasContent({ sells: '  ', tone: 'warm' }), true);
});

test('character counts say how many are left or over, and over-limit fields are listed', () => {
  assert.equal(charsLeftLabel('abc', 10), '7 left');
  assert.equal(charsLeftLabel('x'.repeat(12), 10), '2 over');
  assert.deepEqual(overLimitFields(profile(), { tone: 'x'.repeat(201), sells: 'ok' }), ['tone']);
});

test('saving sends the opened hash, or none when overwriting', async () => {
  const bodies = [];
  globalThis.fetch = async (url, options) => {
    bodies.push({ url: String(url), body: JSON.parse(options.body) });
    return new Response(JSON.stringify(profile()), { status: 200, headers: { 'content-type': 'application/json' } });
  };
  await api.saveBusinessProfile({ sells: 'candles' }, 'abc');
  await api.saveBusinessProfile({ sells: 'candles' }, null);
  assert.deepEqual(bodies[0].body, { fields: { sells: 'candles' }, expected_hash: 'abc' });
  assert.deepEqual(bodies[1].body, { fields: { sells: 'candles' } });
  assert.match(bodies[0].url, /\/business-profile$/);
});
