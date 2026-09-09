const {chromium} = require('playwright');
const fs = require('fs');
const path = require('node:path');
const fixture = process.argv[2];
if (!fixture) throw Error('Usage: node tests/browser_panel.cjs <fixture-directory>');
const assert = require('node:assert/strict');
(async () => {
 const browser = await chromium.launch({headless:true, ...(process.env.WORLDBOOK_BROWSER ? {executablePath:process.env.WORLDBOOK_BROWSER} : {})});
 try {
 const page = await browser.newPage({viewport:{width:1150,height:900}});
 const errors=[];page.on('pageerror', error=>errors.push(error.message));
 await page.setContent('<html><body style="background:#202020"><textarea id="send_textarea"></textarea></body></html>');
 const state=JSON.parse(fs.readFileSync(path.join(fixture, 'initial.json')));
 await page.evaluate(state=>{
  window.fixtureState = state;window.handlers={};window.offCount=0;
  window.eventOn=(name,fn)=>{(window.handlers[name] ||= []).push(fn)};
  window.eventOff=(name,fn)=>{window.handlers[name]=(window.handlers[name]||[]).filter(f=>f!==fn);window.offCount++};
  window.SillyTavern={getCurrentChatId:()=> 'fixture-chat'};window.getLastMessageId=()=>0;window.saveCount=0;
  window.Mvu={getMvuData:()=>({stat_data:structuredClone(window.fixtureState)}),replaceMvuData:async data=>{if(window.failSave) throw Error('保存失败');window.saveCount++;window.fixtureState=structuredClone(data.stat_data)},events:{VARIABLE_UPDATE_ENDED:'updated',COMMAND_PARSED:'commands'}};
 }, state);
 const card=JSON.parse(fs.readFileSync(path.join(fixture, 'output/测试作品叙事者.json')));
 const scripts=card.data.extensions.tavern_helper.scripts;
 // Helper scripts use independent module scopes, as they do in Tavern Helper.
 for(const script of scripts.filter(s=>['MVU 状态规则','MVU 悬浮状态面板'].includes(s.name))) await page.addScriptTag({type:'module',content:script.content});
 await page.locator('.launcher').click();
 await page.getByRole('button',{name:'创建开局',exact:true}).click();
 await page.getByLabel('地点',{exact:true}).fill('外部');
 assert.equal(await page.getByRole('option',{name:'扩展',exact:true}).evaluate(n=>n.disabled),true);
 await page.getByLabel('地点',{exact:true}).fill('中心');
 assert.equal(await page.getByRole('option',{name:'扩展',exact:true}).evaluate(n=>n.disabled),false);
 await page.getByLabel('方式',{exact:true}).selectOption({label:'扩展'});
 // A failed save must leave the form and previous state intact.
 await page.evaluate(()=>{window.failSave=true});
 await page.getByRole('button',{name:'创建并保存开局'}).click();
 assert(await page.getByText('保存失败',{exact:true}).isVisible());
 assert.equal(await page.evaluate(()=>window.fixtureState.世界.已初始化),false);
 assert.equal(await page.locator('#send_textarea').inputValue(),'');
 await page.evaluate(()=>{window.failSave=false});
 await page.locator('#send_textarea').fill('保留原草稿');
 await page.getByRole('button',{name:'创建并保存开局'}).click();
 await page.getByText(/开局已保存并回读确认/).waitFor();
 assert.equal(await page.evaluate(()=>window.fixtureState.世界.已初始化),true);
 assert.equal(await page.evaluate(()=>window.fixtureState.世界.回合),0);
 assert.equal(await page.evaluate(()=>window.fixtureState.世界.当前地点),'中心');
 assert.equal(await page.evaluate(()=>window.saveCount),1);
 assert.equal(await page.locator('#send_textarea').inputValue(),'保留原草稿');
 assert(await page.getByText('当前聊天已初始化，请新建聊天后创建开局。',{exact:true}).isVisible());
 await page.evaluate(()=>{window.getChatMessages=()=>[{message_id:2,role:'assistant',message:'只有正文'}];window.__sillyTavernWorldbookMvuPanel.refresh()});
 assert(await page.getByText(/最新回复尚无完整 UpdateVariable/).isVisible());
 await page.evaluate(()=>{
  const mes=document.createElement('div');mes.className='mes';mes.setAttribute('mesid','2');
  mes.innerHTML='<details open><summary>变量更新记录</summary><div class="mvu-update-details"></div></details>';document.body.append(mes);
  window.getChatMessages=()=>[{message:'<UpdateVariable><Analyze>说明<img src=x onerror=alert(1)></Analyze><JSONPatch>[{"op":"delta","path":"/世界/回合","value":1}]</JSONPatch></UpdateVariable>'}];
  window.__sillyTavernWorldbookMvuPanel.refresh();
 });
 assert((await page.locator('.mvu-update-details').textContent()).includes('说明<img'));
 assert((await page.locator('.mvu-update-details').textContent()).includes('/世界/回合'));
 assert.equal(await page.locator('.mvu-update-details img').count(),0);
 await page.evaluate(()=>{delete window.getChatMessages});
 await page.screenshot({path:path.join(fixture, 'opening.png')});
 // Test actual emitted callback with an invalid numeric update.
 const outcome=await page.evaluate(()=>{
  const before=structuredClone(window.fixtureState);before.世界.已初始化=true;
  const next={stat_data:structuredClone(before)};next.stat_data.$internal={display_data:before,delta_data:{}};next.stat_data.世界.回合=-1;
  for(const fn of window.handlers.updated) fn(next,{stat_data:before});
  return {state:next.stat_data,errors:window.__worldbookRulesRuntime.errors};
 });
 assert.equal(outcome.state.世界.回合,0);assert(outcome.errors.length);
 await page.evaluate(()=>{
  window.fixtureState.世界.档案={消息:[{内容:'测试嵌套内容',编号:1}],技能:{观察:2}};
  window.fixtureState.世界.已初始化=true;
  window.__sillyTavernWorldbookMvuPanel.refresh();
 });
 await page.getByRole('button',{name:/^世界/}).click();
 await page.getByText('档案',{exact:true}).click();
 await page.getByText('消息',{exact:true}).click();
 await page.getByText('0',{exact:true}).last().click();
 assert(await page.getByText('测试嵌套内容',{exact:true}).isVisible());
 await page.screenshot({path:path.join(fixture, 'nested.png')});
 const cleanup=await page.evaluate(()=>{
  window.__sillyTavernWorldbookMvuPanel.destroy();window.__worldbookRulesRuntime.destroy();
  return {roots:document.querySelectorAll('#st-worldbook-mvu-panel').length,handlers:window.handlers.updated.length,off:window.offCount};
 });
 assert.equal(cleanup.roots,0);assert.equal(cleanup.handlers,0);assert(cleanup.off>=2);
 assert.deepEqual(errors,[]);
 console.log('Browser QA passed: dependent form, schema, draft preservation, live hook, nested display, cleanup.');
 } finally { await browser.close(); }
})().catch(e=>{console.error(e);process.exit(1)});
