/* Runs once per MVU update. It never sends prompts or edits lorebooks. */
(() => {
  const CONFIG = __MVU_RULES_CONFIG__;
  const host = window.parent || window;
  const KEY = '__worldbookRulesRuntime';
  host[KEY]?.destroy?.();
  let active = true;
  const subscriptions = [];
  const helper = window.TavernHelper || host.TavernHelper || {};
  const locate = name => window[name] || host[name] || helper[name]?.bind(helper);
  const runtime = {rules:WorldbookRules, config:CONFIG, errors:[], destroy() {
    active = false;
    for (const [event, fn] of subscriptions) locate('eventOff')?.(event, fn);
    window.removeEventListener('pagehide', runtime.destroy);
    if (host[KEY] === runtime) delete host[KEY];
  }};
  host[KEY] = runtime;
  window.addEventListener('pagehide', runtime.destroy, {once:true});
  (async () => {
    const wait = locate('waitGlobalInitialized');
    if (wait) await wait('Mvu');
    if (!active) return;
    const mvu = window.Mvu || host.Mvu;
    if (!mvu?.events?.VARIABLE_UPDATE_ENDED || !locate('eventOn')) {
      runtime.errors = ['MVU 更新事件不可用，规则未启用']; return;
    }
    const onUpdate = (variables, previous) => {
      if (!active) return;
      if (!previous?.stat_data || !variables?.stat_data) { runtime.errors = ['缺少更新前快照，无法校验']; return; }
      try {
        // Opening snapshots are checked for shape; subsequent updates also obey causal rules.
        const result = previous.stat_data.世界?.已初始化 ? WorldbookRules.transition(previous.stat_data, variables.stat_data, CONFIG.rules) : {state:variables.stat_data, errors:[]};
        const errors = result.errors.concat(WorldbookRules.validate(result.state, CONFIG.collections, CONFIG.metrics));
        if (errors.length) throw Error(errors.join('\n'));
        variables.stat_data = result.state;
        runtime.errors = [];
      } catch (error) {
        variables.stat_data = JSON.parse(JSON.stringify(previous.stat_data));
        runtime.errors = [String(error.message || error)];
        console.warn('MVU state update rejected', runtime.errors);
      }
    };
    locate('eventOn')(mvu.events.VARIABLE_UPDATE_ENDED, onUpdate);
    subscriptions.push([mvu.events.VARIABLE_UPDATE_ENDED, onUpdate]);
  })().catch(error => { runtime.errors = [String(error)]; });
})();
