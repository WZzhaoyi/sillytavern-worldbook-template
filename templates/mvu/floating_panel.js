/** MVU lifecycle panel: world, characters, items, locations and events. */
(() => {
  "use strict";

  __MVU_RULES_SOURCE__
  const CONFIG = __MVU_PANEL_CONFIG__;
  const subscriptions = [];
  const RUNTIME_KEY = "__sillyTavernWorldbookMvuPanel";
  const ROOT_ID = "st-worldbook-mvu-panel";
  const hostWindow = (() => {
    try { return window.parent?.document ? window.parent : window; } catch { return window; }
  })();
  const hostDocument = hostWindow.document;

  try { hostWindow[RUNTIME_KEY]?.destroy?.(); } catch { hostDocument.getElementById(ROOT_ID)?.remove(); }

  let active = true;
  let activeCollectionId = CONFIG.collections?.[0]?.id || "world";
  let latestState = {};
  let mvu = null;
  let timer = null;
  let lastSignature = "";
  let initializing = false;

  function locate(name) {
    const helper = window.TavernHelper || hostWindow.TavernHelper;
    const value = window[name] ?? hostWindow[name] ?? helper?.[name];
    return typeof value === "function" && value === helper?.[name] ? value.bind(helper) : value;
  }

  async function resolveMvu() {
    const waitGlobalInitialized = locate("waitGlobalInitialized");
    if (typeof waitGlobalInitialized === "function") {
      try { await waitGlobalInitialized("Mvu"); } catch { /* Poll below. */ }
    }
    for (let attempt = 0; attempt < 100; attempt += 1) {
      const candidate = window.Mvu || hostWindow.Mvu;
      if (candidate?.getMvuData) return candidate;
      await new Promise((resolve) => hostWindow.setTimeout(resolve, 100));
    }
    return null;
  }

  function hasState(value) {
    return Boolean(value?.stat_data && Object.keys(value.stat_data).length);
  }

  function latestSnapshot() {
    if (!mvu?.getMvuData) return { messageId: -1, variables: { stat_data: {} } };
    const ids = [-1];
    const getLastMessageId = locate("getLastMessageId");
    let lastId = -1;
    try {
      lastId = Number(getLastMessageId?.());
      if (Number.isFinite(lastId)) ids.push(lastId);
    } catch { lastId = -1; }
    if (lastId >= 0) {
      for (let offset = 1; offset <= 30; offset += 1) ids.push(lastId - offset);
    }
    let first = null;
    for (const messageId of [...new Set(ids)]) {
      if (messageId < -1) continue;
      try {
        const variables = mvu.getMvuData({ type: "message", message_id: messageId });
        if (variables && !first) first = { messageId, variables };
        if (hasState(variables)) return { messageId, variables };
      } catch { /* Continue to an older floor. */ }
    }
    return first || { messageId: -1, variables: { stat_data: {} } };
  }

  const root = hostDocument.createElement("div");
  root.id = ROOT_ID;
  (hostDocument.body || hostDocument.documentElement).appendChild(root);
  const shadow = root.attachShadow({ mode: "open" });
  shadow.innerHTML = `
    <style>
      :host { position: fixed; inset: 0; z-index: 2147482800; pointer-events: none; }
      * { box-sizing: border-box; }
      .launcher { position: fixed; right: 18px; bottom: 86px; width: 56px; height: 56px;
        border: 1px solid rgba(148,187,230,.42); border-radius: 50%; background: radial-gradient(circle at 35% 25%,#536b85,#111a25 70%);
        color: #d8e9fb; box-shadow: 0 9px 30px rgba(0,0,0,.5); cursor: pointer; pointer-events: auto; font: 700 15px/1 sans-serif; }
      .shell { position: fixed; right: 18px; bottom: 152px; width: min(${Number(CONFIG.width) || 840}px,calc(100vw - 28px));
        height: min(720px,calc(100dvh - 176px)); min-width: 420px; min-height: 380px; display: none; flex-direction: column;
        overflow: hidden; resize: both; border: 1px solid rgba(148,187,230,.28); border-radius: 14px; background: rgba(9,14,21,.98);
        color: #dce7f3; box-shadow: 0 22px 72px rgba(0,0,0,.65); pointer-events: auto; font-family: Inter,"Microsoft YaHei",sans-serif; }
      .shell.open { display: flex; }
      .toolbar { display: flex; align-items: center; gap: 8px; min-height: 42px; padding: 0 11px; border-bottom: 1px solid rgba(255,255,255,.08); background: #121c29; }
      .title { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: #bcd9f5; font-size: 13px; font-weight: 700; }
      .meta { color: #71869b; font-size: 10px; }
      .tool { width: 28px; height: 28px; border: 0; border-radius: 7px; background: rgba(255,255,255,.06); color: #a9bbcd; cursor: pointer; }
      .tabs { display: flex; gap: 4px; overflow-x: auto; padding: 8px 10px; border-bottom: 1px solid rgba(255,255,255,.07); background: #0d1621; }
      .tab { display: flex; align-items: center; gap: 6px; flex: 0 0 auto; padding: 7px 11px; border: 0; border-radius: 8px; background: transparent; color: #8297ab; cursor: pointer; font-size: 12px; }
      .tab.active { background: rgba(90,137,180,.2); color: #c9e2fa; }
      .count { min-width: 18px; padding: 1px 5px; border-radius: 999px; background: rgba(255,255,255,.07); color: #8fa6ba; font-size: 9px; text-align: center; }
      .content { min-height: 0; flex: 1; overflow: auto; padding: 14px; }
      .grid { display: grid; grid-template-columns: repeat(auto-fit,minmax(255px,1fr)); gap: 10px; }
      .card { min-width: 0; padding: 12px; border: 1px solid rgba(255,255,255,.08); border-radius: 10px; background: linear-gradient(145deg,rgba(35,49,65,.7),rgba(14,22,32,.85)); }
      .name { display: flex; align-items: center; gap: 7px; margin-bottom: 10px; color: #c9e2fa; font-size: 14px; font-weight: 700; }
      .field { display: grid; grid-template-columns: minmax(70px,auto) 1fr; gap: 9px; margin-top: 7px; align-items: start; }
      .label { color: #71869b; font-size: 10px; line-height: 1.55; }
      .value { min-width: 0; overflow-wrap: anywhere; color: #c6d4e1; font-size: 11px; line-height: 1.5; }
      .badge { display: inline-block; padding: 2px 7px; border-radius: 999px; background: rgba(93,143,188,.18); color: #a9c9e6; font-size: 10px; }
      .metric { display: grid; grid-template-columns: minmax(68px,auto) 1fr auto; align-items: center; gap: 8px; margin-top: 8px; }
      .track { height: 6px; overflow: hidden; border-radius: 999px; background: rgba(0,0,0,.42); }
      .fill { height: 100%; border-radius: inherit; background: linear-gradient(90deg,#527ba4,#91c5f2); }
      .number { min-width: 32px; color: #dce7f3; font: 11px/1 ui-monospace,monospace; text-align: right; }
      .stage { grid-column: 2 / 4; color: #71869b; font-size: 10px; }
      input, select, .action { width: 100%; padding: 9px; margin: 5px 0; color: #dce7f3; background: #172536; border: 1px solid #527ba4; border-radius: 6px; }
      .action { cursor: pointer; }
      .error { color: #ffa9a9; white-space: pre-wrap; }
      details { margin: 6px 0; }
      .empty { padding: 40px 20px; color: #71869b; text-align: center; }
      @media (max-width: 600px) {
        .launcher { right: 12px; bottom: 76px; }
        .shell { right: 8px; bottom: 140px; width: calc(100vw - 16px); height: calc(100dvh - 158px); min-width: 0; min-height: 0; resize: none; }
        .grid { grid-template-columns: 1fr; }
      }
    </style>
    <button class="launcher" type="button" title="打开 MVU 世界状态">状态</button>
    <section class="shell" aria-label="MVU lifecycle status panel">
      <div class="toolbar"><div class="title"></div><div class="meta"></div><button class="tool refresh" type="button" title="刷新">↻</button><button class="tool close" type="button" title="关闭">×</button></div>
      <div class="tabs"></div><div class="content"></div>
    </section>
  `;

  const launcher = shadow.querySelector(".launcher");
  const shell = shadow.querySelector(".shell");
  const tabs = shadow.querySelector(".tabs");
  const content = shadow.querySelector(".content");
  const meta = shadow.querySelector(".meta");
  shadow.querySelector(".title").textContent = CONFIG.title || "MVU 世界状态";

  function element(className, value = "") {
    const node = hostDocument.createElement("div");
    node.className = className;
    node.textContent = value;
    return node;
  }

  function setOpen(open) { shell.classList.toggle("open", Boolean(open)); }

  function stageFor(metric, rawValue) {
    const value = Number(rawValue);
    const ranges = metric.ranges || [0, 100];
    const stages = metric.stages || [];
    for (let index = 0; index < ranges.length - 1; index += 1) {
      const isLast = index === ranges.length - 2;
      if (value >= ranges[index] && (value < ranges[index + 1] || (isLast && value <= ranges[index + 1]))) {
        return stages[stages.length - 1 - index] || "";
      }
    }
    return "";
  }

  function displayValue(field, value) {
    if (field.type === "boolean") return value ? "是" : "否";
    if (field.type === "string_list") return Array.isArray(value) && value.length ? value.join("、") : "—";
    if (value === "" || value === null || value === undefined) return "—";
    return typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value);
  }

  function appendMetricRows(card, values) {
    for (const metric of CONFIG.metrics || []) {
      if (!Object.prototype.hasOwnProperty.call(values || {}, metric.id)) continue;
      const raw = Number(values?.[metric.id] ?? metric.initial ?? metric.ranges?.[0] ?? 0);
      const minimum = Number(metric.ranges?.[0] ?? 0);
      const maximum = Number(metric.ranges?.[metric.ranges.length - 1] ?? 100);
      const percentage = maximum === minimum ? 0 : Math.max(0, Math.min(100, (raw - minimum) / (maximum - minimum) * 100));
      const row = element("metric");
      const track = element("track");
      const fill = element("fill");
      fill.style.width = `${percentage}%`;
      track.appendChild(fill);
      row.append(element("label", metric.name), track, element("number", String(raw)), element("stage", stageFor(metric, raw)));
      card.appendChild(row);
    }
  }

  function appendFields(card, collection, record) {
    for (const [fieldName, field] of Object.entries(collection.fields || {})) {
      if (field.panel === false) continue;
      const value = record?.[fieldName] ?? field.default;
      if (['object', 'array', 'record'].includes(field.type)) {
        const details = hostDocument.createElement('details');
        const summary = hostDocument.createElement('summary');
        summary.textContent = fieldName;
        details.append(summary);
        if (field.type === 'object') appendFields(details, field, value);
        else for (const [key, item] of Object.entries(value || {})) appendFields(details, {fields:{[key]:field.items}}, {[key]:item});
        card.append(details);
        continue;
      }
      if (field.type === "metrics") {
        appendMetricRows(card, value);
        continue;
      }
      const row = element("field");
      const rendered = element(field.type === "enum" || field.type === "boolean" ? "value badge" : "value", displayValue(field, value));
      row.append(element("label", fieldName), rendered);
      card.appendChild(row);
    }
  }

  function stageDraft(text) {
    const input = hostDocument.querySelector('#send_textarea');
    if (!input) throw Error('未找到酒馆输入框，请复制下方内容。');
    if (input.value.trim()) throw Error('输入框已有草稿，请先保存或清空。');
    input.value = text;
    input.dispatchEvent(new hostWindow.Event('input', {bubbles:true}));
    input.focus();
  }

  function action(label, fn) {
    const button = hostDocument.createElement('button');
    button.type = 'button'; button.className = 'action'; button.textContent = label;
    button.addEventListener('click', fn); return button;
  }

  function renderOpening() {
    if (latestState?.世界?.已初始化) {
      content.append(element('empty', '当前聊天已初始化，请新建聊天后创建开局。')); return;
    }
    const form = hostDocument.createElement('form');
    const inputs = new Map();
    const initial = JSON.parse(JSON.stringify(CONFIG.opening.state));
    for (const field of CONFIG.opening.fields) {
      const label = hostDocument.createElement('label'); label.textContent = field.label || field.path;
      const input = hostDocument.createElement(field.type === 'select' ? 'select' : 'input');
      if (field.type !== 'select') { input.type = field.type === 'number' ? 'number' : 'text'; if (input.type === 'number') input.step = 'any'; }
      if (field.type === 'select') for (const [index, choice] of field.options.entries()) {
        const option = hostDocument.createElement('option'); option.value = String(index); option.textContent = choice.label || String(choice.value); input.append(option);
      }
      const value = WorldbookRules.get(initial, field.path);
      input.value = field.type === 'select' ? String(field.options.findIndex(option => JSON.stringify(option.value) === JSON.stringify(value))) : (value ?? '');
      input.required = field.required !== false;
      input.id = `opening-field-${inputs.size}`; label.htmlFor = input.id;
      form.append(label, input); inputs.set(field.path, input);
    }
    const error = element('error');
    const snapshot = () => {
      const state = JSON.parse(JSON.stringify(initial));
      for (const field of CONFIG.opening.fields) {
        const input = inputs.get(field.path);
        const value = field.type === 'select' ? field.options[Number(input.value)]?.value : field.type === 'number' ? Number(input.value) : input.value;
        if (value !== undefined) WorldbookRules.set(state, field.path, value);
      }
      return state;
    };
    const refreshOptions = () => {
      const state = snapshot();
      for (const field of CONFIG.opening.fields.filter(field => field.type === 'select')) {
        const input = inputs.get(field.path);
        [...input.options].forEach((option, i) => { option.disabled = !(field.options[i].when || []).every(test => WorldbookRules.condition(test, state)); });
      }
      error.textContent = '';
    };
    form.addEventListener('input', refreshOptions); refreshOptions();
    const submit = hostDocument.createElement('button'); submit.type = 'submit'; submit.className = 'action'; submit.textContent = '创建并保存开局';
    form.addEventListener('submit', async event => {
      event.preventDefault();
      if (initializing) return;
      const state = snapshot();
      const errors = WorldbookRules.validate(state, CONFIG.collections, CONFIG.metrics);
      for (const field of CONFIG.opening.fields) {
        const input = inputs.get(field.path);
        if (input.required && !input.value.trim()) errors.push(`${field.label}: 必填`);
        if (field.type === 'select' && (!input.selectedOptions.length || input.selectedOptions[0].disabled)) errors.push(`${field.label}: 选项不满足条件`);
      }
      errors.push(...WorldbookRules.transition(state, state, {constraints:CONFIG.rules.constraints || []}).errors);
      if (errors.length) { error.textContent = errors.join('\n'); return; }
      initializing = true; submit.disabled = true;
      try {
        if (typeof mvu?.replaceMvuData !== 'function') throw Error('MVU 保存接口不可用，开局未提交');
        const getLastMessageId = locate('getLastMessageId');
        const tavern = window.SillyTavern || hostWindow.SillyTavern;
        if (typeof getLastMessageId !== 'function' || typeof tavern?.getCurrentChatId !== 'function') throw Error('无法确认当前聊天，开局未提交');
        const chatId = tavern.getCurrentChatId();
        const messageId = Number(getLastMessageId());
        if (!chatId || messageId !== 0) throw Error('请在只有开场消息的新聊天中创建开局');
        const target = {type:'message', message_id:messageId};
        const current = mvu.getMvuData(target) || {};
        if (current.stat_data?.世界?.已初始化) throw Error('当前聊天已初始化，请新建聊天');
        state.世界.已初始化 = true;
        state.世界.回合 = 0;
        const variables = JSON.parse(JSON.stringify(current));
        variables.stat_data = state;
        // replaceMvuData writes the complete validated snapshot; no model request is involved.
        delete variables.display_data; delete variables.delta_data;
        await mvu.replaceMvuData(variables, target);
        if (!active || tavern.getCurrentChatId() !== chatId) throw Error('聊天已切换，请返回原聊天核对开局');
        const saved = mvu.getMvuData(target);
        if (JSON.stringify(saved?.stat_data) !== JSON.stringify(state)) throw Error('开局回读与提交内容不一致，请检查 MVU 保存结果');
        const draft = '开始故事，请从当前已保存的主角与场景展开第一轮互动。';
        try { stageDraft(draft); } catch { /* Keep an existing draft; state is already saved. */ }
        refresh(true);
        meta.textContent = '开局已保存并回读确认，回合 0；发送行动开始故事。';
      } catch (err) {
        error.textContent = String(err.message || err);
      } finally { initializing = false; submit.disabled = false; }
    });
    form.append(submit, error); content.append(form);
  }

  function renderRules() {
    const runtime = hostWindow.__worldbookRulesRuntime;
    content.append(element('error', (runtime?.errors || []).join('\n')));
    if (!runtime) content.append(element('error', '未检测到状态规则脚本；请启用角色卡中的 MVU 状态规则。'));
    const choices = WorldbookRules.candidates(latestState, CONFIG.rules);
    content.append(element('label', '候选只提供可选方向，不代表事件已经发生；不选择也合法。'));
    if (!choices.length) content.append(element('empty', '暂无可用遭遇'));
    for (const choice of choices) {
      const card = element('card'); card.append(element('name', choice.label || choice.id), element('value', choice.text || ''));
      const error = element('error');
      card.append(action('填入行动草稿', () => {
        try { stageDraft(`我想尝试以下行动：${choice.text || choice.label || choice.id}。请先检查可行性；仅正文确认遭遇发生后，将 ${CONFIG.rules.encounters.selected_path} 设为 ${JSON.stringify(choice.id)}。`); }
        catch (err) { error.textContent = err.message; }
      }), error); content.append(card);
    }
  }

  function renderCollection() {
    const collection = CONFIG.collections?.find((item) => item.id === activeCollectionId) || CONFIG.collections?.[0];
    content.replaceChildren();
    if (activeCollectionId === '__opening') { renderOpening(); return; }
    if (activeCollectionId === '__rules') { renderRules(); return; }
    if (!collection) {
      content.appendChild(element("empty", "未配置状态集合"));
      return;
    }
    const data = latestState?.[collection.path] || {};
    const grid = element("grid");
    if (collection.kind === "singleton") {
      const card = element("card");
      card.appendChild(element("name", collection.label));
      appendFields(card, collection, data);
      grid.appendChild(card);
    } else {
      for (const [entityName, record] of Object.entries(data)) {
        const card = element("card");
        card.appendChild(element("name", entityName));
        appendFields(card, collection, record);
        grid.appendChild(card);
      }
    }
    if (!grid.childElementCount) grid.appendChild(element("empty", `${collection.label}集合为空`));
    content.appendChild(grid);
  }

  function renderTabs() {
    tabs.replaceChildren();
    for (const [id, label] of [['__opening', '创建开局'], ['__rules', '规则与遭遇']]) {
      if (id === '__opening' && !CONFIG.opening?.fields?.length) continue;
      if (id === '__rules' && !Object.keys(CONFIG.rules || {}).length) continue;
      const button = hostDocument.createElement('button');
      button.type = 'button'; button.className = `tab${activeCollectionId === id ? ' active' : ''}`;
      button.dataset.collectionId = id; button.textContent = label; tabs.append(button);
    }
    for (const collection of CONFIG.collections || []) {
      const data = latestState?.[collection.path] || {};
      const count = collection.kind === "singleton" ? 1 : Object.keys(data).length;
      const button = hostDocument.createElement("button");
      button.type = "button";
      button.className = `tab${collection.id === activeCollectionId ? " active" : ""}`;
      button.dataset.collectionId = collection.id;
      button.append(element("", collection.label), element("count", String(count)));
      tabs.appendChild(button);
    }
  }

  function render(variables, messageId) {
    latestState = variables?.stat_data || {};
    renderTabs();
    renderCollection();
    meta.textContent = `${latestState.世界?.已初始化 ? "已初始化" : "待初始化：请在创建开局中保存资料"} · 状态楼层 ${messageId} · ${new Date().toLocaleTimeString()}`;
  }

  function outputStatus() {
    const readMessages = locate('getChatMessages');
    if (typeof readMessages !== 'function') return '';
    try {
      const message = readMessages(-1)?.[0];
      if (!message || message.role !== 'assistant' || message.message_id === 0) return '';
      const text = message.message || '';
      const update = text.match(/<UpdateVariable>([\s\S]*?)<\/UpdateVariable>/i);
      if (!update) return '最新回复尚无完整 UpdateVariable；生成结束后仍出现此提示，请重新生成该回复。';
      const patch = update[1].match(/<JSONPatch>([\s\S]*?)<\/JSONPatch>/i);
      try { if (!patch || !Array.isArray(JSON.parse(patch[1]))) throw Error(); }
      catch { return '最新回复的 JSONPatch 尚不是合法数组；请修正或重新生成。'; }
      const saved = mvu.getMvuData({type:'message', message_id:message.message_id});
      if (!saved?.stat_data?.世界?.已初始化) return '最新回复尚未保存已初始化状态，请检查 MVU 解析结果。';
      if (!/<StateCheck>[\s\S]*?<\/StateCheck>/i.test(text)) return '最新回复缺少 StateCheck 前检块。';
      return '';
    } catch { return '无法读取最新回复的协议状态。'; }
  }

  function renderMessageUpdates() {
    const read = locate('getChatMessages');
    if (typeof read !== 'function') return;
    for (const target of hostDocument.querySelectorAll('.mes .mvu-update-details')) {
      const id = Number(target.closest('.mes').getAttribute('mesid'));
      if (!Number.isInteger(id)) continue;
      try {
        const text = read(id)?.[0]?.message || '';
        const block = text.match(/<UpdateVariable>([\s\S]*?)<\/UpdateVariable>/i)?.[1];
        if (!block || target.__mvuSource === block) continue;
        target.__mvuSource = block;
        const analysis = block.match(/<Analy(?:sis|ze)>([\s\S]*?)<\/Analy(?:sis|ze)>/i)?.[1]?.trim() || '';
        const raw = block.match(/<JSONPatch>([\s\S]*?)<\/JSONPatch>/i)?.[1] || '';
        const pre = hostDocument.createElement('pre');
        pre.style.whiteSpace = 'pre-wrap'; pre.style.overflowWrap = 'anywhere';
        try { pre.textContent = analysis + '\n' + JSON.stringify(JSON.parse(raw), null, 2); }
        catch { pre.textContent = '更新数组解析失败\n' + raw; }
        target.replaceChildren(pre);
      } catch { target.textContent = '无法读取本楼层更新记录'; }
    }
  }

  function refresh(force = false) {
    if (!active || !mvu) return;
    renderMessageUpdates();
    const snapshot = latestSnapshot();
    const status = outputStatus();
    let signature;
    try { signature = JSON.stringify([snapshot.messageId, snapshot.variables?.stat_data || {}, hostWindow.__worldbookRulesRuntime?.errors, status]); } catch { signature = String(Date.now()); }
    if (!force && signature === lastSignature) return;
    lastSignature = signature;
    render(snapshot.variables, snapshot.messageId);
    if (status) meta.textContent = status + " · " + meta.textContent;
  }

  launcher.addEventListener("click", () => setOpen(!shell.classList.contains("open")));
  shadow.querySelector(".close").addEventListener("click", () => setOpen(false));
  shadow.querySelector(".refresh").addEventListener("click", () => refresh(true));
  tabs.addEventListener("click", (event) => {
    const button = event.target.closest(".tab");
    if (!button) return;
    activeCollectionId = button.dataset.collectionId;
    renderTabs();
    renderCollection();
  });

  const runtime = {
    open: () => setOpen(true), close: () => setOpen(false), refresh: () => refresh(true),
    destroy: () => {
      if (!active) return;
      active = false;
      if (timer !== null) hostWindow.clearInterval(timer);
      for (const [event, fn] of subscriptions) locate('eventOff')?.(event, fn);
      window.removeEventListener('pagehide', runtime.destroy);
      root.remove();
      try { delete hostWindow[RUNTIME_KEY]; } catch { hostWindow[RUNTIME_KEY] = null; }
    },
  };
  hostWindow[RUNTIME_KEY] = runtime;
  window.addEventListener('pagehide', runtime.destroy, {once:true});

  resolveMvu().then((resolved) => {
    if (!active) return;
    mvu = resolved;
    if (!mvu) {
      content.replaceChildren(element("empty", "未检测到 MVU 运行时"));
      return;
    }
    refresh(true);
    timer = hostWindow.setInterval(() => refresh(false), 1500);
    const eventOn = locate("eventOn");
    const eventName = mvu.events?.VARIABLE_UPDATE_ENDED;
    if (typeof eventOn === "function" && eventName) {
      const handler = () => { if (active) refresh(true); };
      eventOn(eventName, handler); subscriptions.push([eventName, handler]);
    }
  });
})();
