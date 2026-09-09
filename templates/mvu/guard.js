/* Runs once per MVU update. It never sends prompts or edits lorebooks. */
(() => {
  const CONFIG = __MVU_RULES_CONFIG__;
  const host = window.parent || window;
  const KEY = '__worldbookRulesRuntime';
  host[KEY]?.destroy?.();
  let active = true;
  const subscriptions = [];
  const rejected = new WeakMap();
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
    const onCommands = (variables, commands, text) => {
      rejected.delete(variables);
      if (!commands.length && !/<(?:UpdateVariable|JSONPatch)>/i.test(text)) return;
      try {
        const blocks = [...text.matchAll(/<JSONPatch>([\s\S]*?)<\/JSONPatch>/gi)];
        if (blocks.length !== 1) throw Error('每次更新须包含一个 JSONPatch 数组');
        const operations = JSON.parse(blocks[0][1]);
        if (!Array.isArray(operations) || commands.length !== operations.length) throw Error('解析命令与 JSONPatch 不一致');
        for (const op of operations) {
          if (!op || typeof op !== 'object' || !['replace','delta','insert','remove','move'].includes(op.op)) throw Error('不支持的更新操作');
          const paths = op.op === 'move' ? [op.from, op.to] : [op.path];
          for (const path of paths) {
            if (typeof path !== 'string' || !path.startsWith('/')) throw Error('更新路径必须是 JSON pointer');
            if (variables.stat_data?.世界?.已初始化 && (path.split('/').length === 2 || path === '/世界/已初始化')) throw Error('已初始化聊天只能更新字段和实体，不能重置集合或初始化标记');
            // Check unsafe keys using the same path parser as the state rules.
            WorldbookRules.get(variables.stat_data, path);
          }
          if (['replace','insert','delta'].includes(op.op) && !Object.prototype.hasOwnProperty.call(op,'value')) throw Error('更新操作缺少 value');
          if (op.op === 'delta' && (typeof op.value !== 'number' || !Number.isFinite(op.value))) throw Error('delta 必须使用有限数值');
        }
      } catch (error) {
        rejected.set(variables, String(error.message || error));
        commands.splice(0); // Reject the entire command batch before MVU executes it.
      }
    };
    if (mvu.events.COMMAND_PARSED) {
      locate('eventOn')(mvu.events.COMMAND_PARSED, onCommands);
      subscriptions.push([mvu.events.COMMAND_PARSED, onCommands]);
    }
    const onUpdate = (variables, previous) => {
      if (!active) return;
      if (!previous?.stat_data || !variables?.stat_data) { runtime.errors = ['缺少更新前快照，无法校验']; return; }
      try {
        if (rejected.has(variables)) throw Error(rejected.get(variables));
        if (previous.stat_data.世界?.已初始化 && !variables.stat_data.世界?.已初始化) throw Error('已初始化状态不能退回未初始化');
        // MVU v1.0.2 removes its temporary $internal AFTER this event.
        // Validate only authored state, not that runtime-owned display/delta payload.
        const {$internal: ignoredInternal, ...proposed} = variables.stat_data;
        const {$internal: ignoredPrevious, ...before} = previous.stat_data;
        const result = before.世界?.已初始化 ? WorldbookRules.transition(before, proposed, CONFIG.rules) : {state:proposed, errors:[]};
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
