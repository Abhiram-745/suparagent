import assert from 'node:assert/strict';
import { test } from 'node:test';
import { agentNames, cleanAddress, describeServiceError, kindOf, outcomeTone, toggleAgent } from './agent-services.ts';

test('a named provider holds one kind of address and "other" asks', () => {
  assert.equal(kindOf('agentmail'), 'email');
  assert.equal(kindOf('agentphone'), 'phone');
  assert.equal(kindOf('other'), null);
});

test('an email is trimmed and lowercased, and a malformed one is refused', () => {
  assert.equal(cleanAddress('email', '  Helper@AgentMail.to '), 'helper@agentmail.to');
  for (const bad of ['', 'not-an-address', 'a@b', 'a b@example.com', '@example.com']) assert.equal(cleanAddress('email', bad), null, bad);
});

test('a phone number is kept as +E.164 and anything else is refused', () => {
  assert.equal(cleanAddress('phone', '+1 (415) 555-0100'), '+14155550100');
  assert.equal(cleanAddress('phone', '+14155550100'), '+14155550100');
  for (const bad of ['4155550100', '+0123456789', '+123', 'abc', '']) assert.equal(cleanAddress('phone', bad), null, bad);
});

test('the agents an address is given to are named, or "No agent"', () => {
  const agents = [{ id: 1, name: 'Mail helper' }, { id: 2, name: 'Research' }];
  assert.equal(agentNames([2, 1], agents), 'Research, Mail helper');
  assert.equal(agentNames([], agents), 'No agent');
  assert.equal(agentNames([9], agents), 'No agent');
});

test('switching one agent on or off keeps the rest, sorted, without duplicates', () => {
  assert.deepEqual(toggleAgent([3, 1], 2, true), [1, 2, 3]);
  assert.deepEqual(toggleAgent([1, 2], 2, true), [1, 2]);
  assert.deepEqual(toggleAgent([1, 2], 1, false), [2]);
  assert.deepEqual(toggleAgent([], 5, false), []);
});

test('known causes use our wording and other errors keep the backend message', () => {
  assert.match(describeServiceError({ code: 'resource_limit_reached' }), /limit/);
  assert.match(describeServiceError({ code: 'invalid_address' }), /valid address/);
  assert.match(describeServiceError({ code: 'connection_changed' }), /another window/); // from the custom MCP list
  assert.equal(describeServiceError(new Error('Boom')), 'Boom');
  assert.equal(describeServiceError(undefined), 'The request failed.');
});

test('only a finished call is green; failed and unknown are flagged', () => {
  assert.equal(outcomeTone('completed'), 'success');
  assert.equal(outcomeTone('failed'), 'danger');
  assert.equal(outcomeTone('outcome_unknown'), 'danger');
  assert.equal(outcomeTone('dispatched'), 'neutral');
});
