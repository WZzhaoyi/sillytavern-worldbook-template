/* Pure state rules: shared by the live hook, opening form and replay tests. */
const WorldbookRules = (() => {
  const clone = value => JSON.parse(JSON.stringify(value));
  const own = (obj, key) => Object.prototype.hasOwnProperty.call(obj || {}, key);
  function parts(path) {
    if (typeof path !== 'string' || !path.startsWith('/')) throw Error(`Invalid state path: ${path}`);
    return path.slice(1).split('/').map(p => {
      const key = p.replace(/~1/g, '/').replace(/~0/g, '~');
      if (['__proto__', 'prototype', 'constructor'].includes(key)) throw Error('Unsafe state key');
      return key;
    });
  }
  function get(state, path) {
    return parts(path).reduce((value, key) => own(value, key) ? value[key] : undefined, state);
  }
  function set(state, path, value) {
    const keys = parts(path), last = keys.pop();
    let cursor = state;
    for (const key of keys) {
      if (!own(cursor, key)) cursor[key] = {};
      if (!cursor[key] || typeof cursor[key] !== 'object') throw Error(`Invalid parent: ${path}`);
      cursor = cursor[key];
    }
    cursor[last] = value;
  }
  function matches(state, pattern) {
    const result = [];
    const walk = (value, keys, path) => {
      if (!keys.length) { result.push(path); return; }
      const [key, ...rest] = keys;
      for (const child of key === '*' ? Object.keys(value || {}) : [key]) {
        if (own(value, child)) walk(value[child], rest, `${path}/${child.replace(/~/g, '~0').replace(/\//g, '~1')}`);
      }
    };
    walk(state, parts(pattern), '');
    return result;
  }
  function condition(test, after, before = after, binding = '') {
    const path = test.path.replace('*', binding);
    const value = get(test.source === 'before' ? before : after, path);
    const expected = own(test, 'value_path') ? get(test.value_source === 'before' ? before : after, test.value_path.replace('*', binding)) : test.value;
    switch (test.op || 'eq') {
      case 'eq': return JSON.stringify(value) === JSON.stringify(expected);
      case 'ne': return JSON.stringify(value) !== JSON.stringify(expected);
      case 'gte': return typeof value === 'number' && value >= expected;
      case 'lte': return typeof value === 'number' && value <= expected;
      case 'gt': return typeof value === 'number' && value > expected;
      case 'lt': return typeof value === 'number' && value < expected;
      case 'in': return Array.isArray(expected) && expected.includes(value);
      case 'contains': return Array.isArray(value) && value.includes(expected);
      case 'exists': return (value !== undefined) === (expected !== false);
      case 'changed': return JSON.stringify(get(before, path)) !== JSON.stringify(get(after, path));
      default: throw Error(`Unknown condition operator: ${test.op}`);
    }
  }
  function candidates(state, config) {
    const rules = config.encounters;
    if (!rules || Number(get(state, rules.cooldown_path)) > 0) return [];
    const seen = get(state, rules.seen_path) || [];
    const eligible = (rules.candidates || []).filter(c => !seen.includes(c.id) && (c.when || []).every(t => condition(t, state)));
    // Stable per state tick; rerendering never rerolls or mutates state.
    const tick = Number(get(state, config.clock_path || '/世界/回合')) || 0;
    return eligible.map(c => ({...c, rank: [...`${tick}:${c.id}`].reduce((h, ch) => (h * 31 + ch.charCodeAt(0)) >>> 0, 0)}))
      .sort((a, b) => a.rank - b.rank || a.id.localeCompare(b.id));
  }
  function validateNode(value, field, path, errors, metrics = []) {
    const fail = msg => errors.push(`${path}: ${msg}`);
    switch (field.type) {
      case 'number':
        if (typeof value !== 'number' || !Number.isFinite(value)) fail('must be finite number');
        else if (value < (field.min ?? -Infinity) || value > (field.max ?? Infinity)) fail('outside range');
        break;
      case 'string': if (typeof value !== 'string') fail('must be string'); break;
      case 'boolean': if (typeof value !== 'boolean') fail('must be boolean'); break;
      case 'enum': if (!field.values.includes(value)) fail('invalid enum'); break;
      case 'metrics':
        validateNode(value, {type:'object', fields:Object.fromEntries(metrics.filter(m => !(m.exclude_entities || []).includes(path.startsWith('/人物/') ? path.split('/')[2].replace(/~1/g,'/').replace(/~0/g,'~') : null)).map(m => [m.id, {type:'number', min:m.ranges[0], max:m.ranges.at(-1)}]))}, path, errors);
        break;
      case 'object':
        if (!value || Array.isArray(value) || typeof value !== 'object') { fail('must be object'); break; }
        for (const key of Object.keys(value)) if (!own(field.fields, key)) fail(`unknown field ${key}`);
        for (const [key, child] of Object.entries(field.fields)) validateNode(value[key], child, `${path}/${key}`, errors, metrics);
        break;
      case 'array': case 'record': case 'string_list': {
        const array = field.type !== 'record';
        if (!value || typeof value !== 'object' || Array.isArray(value) !== array) { fail(`must be ${array ? 'array' : 'record'}`); break; }
        if (Object.keys(value).length > (field.max_items ?? Infinity)) fail('max_items exceeded');
        for (const [key, child] of Object.entries(value)) validateNode(child, field.type === 'string_list' ? {type:'string'} : field.items, `${path}/${key}`, errors, metrics);
        break;
      }
      default: fail(`unknown type ${field.type}`);
    }
  }
  function validate(state, collections, metrics) {
    const errors = [];
    const fields = Object.fromEntries(collections.map(c => [c.path, c.kind === 'singleton' ? {type:'object', fields:c.fields} : {type:'record', items:{type:'object', fields:c.fields}}]));
    validateNode(state, {type:'object', fields}, '', errors, metrics);
    return errors;
  }
  function transition(before, proposed, config = {}) {
    const state = clone(proposed), errors = [];
    const clock = config.clock_path || '/世界/回合';
    const elapsed = Number(get(state, clock)) - Number(get(before, clock));
    if (!Number.isFinite(elapsed) || elapsed < 0) errors.push(`${clock}: clock must not go backwards`);
    for (const rule of config.transitions || []) {
      for (const path of matches(state, rule.path)) {
        const old = get(before, path), next = get(state, path);
        if (old !== undefined && old !== next && !(rule.allowed[old] || []).includes(next)) errors.push(`${path}: illegal transition ${old} → ${next}`);
      }
    }
    for (const rule of config.constraints || []) {
      const paths = rule.for_each ? matches(state, rule.for_each) : [''];
      for (const path of paths) {
        const binding = path.split('/').at(-1);
        if ((rule.when || []).every(t => condition(t, state, before, binding)) && !(rule.require || []).every(t => condition(t, state, before, binding))) errors.push(`${path}: ${rule.message || 'precondition failed'}`);
      }
    }
    for (const rule of config.growth || []) {
      const ticks = Number(get(state, rule.clock_path || clock)) - Number(get(before, rule.clock_path || clock));
      for (const path of matches(state, rule.path)) {
        const old = get(before, path), next = get(state, path);
        if (old !== undefined && next > old && (!Number.isFinite(ticks) || ticks <= 0 || next - old > ticks * rule.max_per_tick)) errors.push(`${path}: growth exceeds elapsed-time budget`);
      }
    }
    const encounter = config.encounters;
    if (encounter) {
      const selected = get(state, encounter.selected_path);
      const oldSelected = get(before, encounter.selected_path);
      if (selected && selected !== oldSelected) {
        if (!candidates(before, config).some(c => c.id === selected)) errors.push('Encounter is unavailable, seen or cooling down');
        else {
          set(state, encounter.cooldown_path, encounter.cooldown_turns);
          set(state, encounter.seen_path, [...new Set([...(get(before, encounter.seen_path) || []), selected])]);
        }
      } else {
        set(state, encounter.cooldown_path, Math.max(0, Number(get(before, encounter.cooldown_path)) - Math.max(0, elapsed)));
        set(state, encounter.seen_path, clone(get(before, encounter.seen_path) || []));
      }
    }
    for (const rule of config.archives || []) {
      const records = get(state, rule.collection) || {}, oldRecords = get(before, rule.collection) || {};
      const history = clone(get(before, rule.target) || []);
      if (elapsed > 0) for (const [name, value] of Object.entries(oldRecords)) {
        if (rule.terminal_states.includes(value[rule.status_field]) && (!records[name] || JSON.stringify(records[name]) === JSON.stringify(value))) {
          history.push({name, ...Object.fromEntries(rule.summary_fields.map(key => [key, clone(value[key] ?? '')]))});
          delete records[name];
        }
      }
      set(state, rule.target, history.slice(-rule.max_entries));
    }
    for (const rule of config.retention || []) {
      for (const path of matches(state, rule.path)) {
        const value = get(state, path);
        if (!Array.isArray(value)) errors.push(`${path}: retention requires array`);
        else set(state, path, value.slice(-rule.max_items));
      }
    }
    return {state: errors.length ? clone(before) : state, errors};
  }
  function patch(state, operations) {
    const result = clone(state);
    for (const op of operations) {
      if (op.op === 'move') {
        const value = get(result, op.from);
        if (value === undefined) throw Error('Missing move source');
        remove(result, op.from); set(result, op.to, value); continue;
      }
      const old = get(result, op.path);
      if (op.op === 'remove') { remove(result, op.path); continue; }
      if (op.op === 'replace' && old === undefined) throw Error(`Missing replace target: ${op.path}`);
      if (op.op === 'insert' && old !== undefined) throw Error(`Existing insert target: ${op.path}`);
      if (op.op === 'delta') {
        if (typeof old !== 'number' || typeof op.value !== 'number') throw Error('delta requires numbers');
        set(result, op.path, old + op.value);
      } else if (['replace','insert'].includes(op.op)) set(result, op.path, clone(op.value));
      else throw Error(`Unsupported operation: ${op.op}`);
    }
    return result;
  }
  function remove(state, path) {
    const keys = parts(path), key = keys.pop();
    const parent = keys.reduce((obj, part) => obj?.[part], state);
    if (!own(parent, key)) throw Error(`Missing remove target: ${path}`);
    if (Array.isArray(parent)) parent.splice(Number(key), 1); else delete parent[key];
  }
  return {get, set, matches, condition, candidates, validate, transition, patch};
})();
if (typeof module !== 'undefined') module.exports = WorldbookRules;
