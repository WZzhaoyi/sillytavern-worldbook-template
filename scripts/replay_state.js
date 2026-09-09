#!/usr/bin/env node
/* Run a recorded multi-turn state fixture against the exact runtime rules. */
const fs = require('node:fs');
const assert = require('node:assert/strict');
const rules = require('../templates/mvu/rules.js');
function replay(fixture) {
  let state = structuredClone(fixture.initial);
  const results = [];
  for (const [index, turn] of fixture.turns.entries()) {
    let result;
    try {
      const proposed = turn.state || rules.patch(state, turn.patch || []);
      result = rules.transition(state, proposed, fixture.rules);
      if (!result.errors.length && fixture.collections) result.errors.push(...rules.validate(result.state, fixture.collections, fixture.metrics || []));
    } catch (error) { result = {errors:[error.message], state}; }
    assert.equal(result.errors.length === 0, turn.accept !== false, `Turn ${index + 1}: ${result.errors.join('; ')}`);
    if (!result.errors.length) state = result.state;
    for (const [path, expected] of Object.entries(turn.expect || {})) assert.deepEqual(rules.get(state, path), expected, `Turn ${index + 1}: ${path}`);
    results.push({turn:index + 1, errors:result.errors});
  }
  return {state, results};
}
module.exports = replay;
if (require.main === module) {
  if (process.argv.length !== 3) { console.error('Usage: node scripts/replay_state.js <fixture.json>'); process.exit(2); }
  try { console.log(JSON.stringify(replay(JSON.parse(fs.readFileSync(process.argv[2], 'utf8'))), null, 2)); }
  catch (error) { console.error(error.message); process.exit(1); }
}
