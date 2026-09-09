import base64
import json
import shutil
import struct
import subprocess
import tempfile
import unittest
import zlib
from pathlib import Path

import yaml

from test_generate_sillytavern import CONFIG, PROJECT_ROOT
from scripts.generate_sillytavern import SillyTavernGenerator
from scripts.card_io import chunk, png_chunks, read_card, write_card_png, inspect_card, restore, SIGNATURE


def feature_config():
    config = yaml.safe_load(CONFIG)
    world = config['state_model']['collections']['world']['fields']
    world['选项'] = {'type': 'string', 'default': '基础'}
    world['档案'] = {'type': 'object', 'default': {}, 'fields': {
        '消息': {'type': 'array', 'default': [], 'max_items': 3, 'items': {'type': 'object', 'default': {}, 'fields': {
            '内容': {'type': 'string', 'default': ''}, '编号': {'type': 'number', 'default': 0}}}},
        '技能': {'type': 'record', 'default': {}, 'items': {'type': 'number', 'default': 0, 'min': 0}},
    }}
    config['opening'] = {'state': {}, 'fields': [
        {'path': '/世界/当前地点', 'label': '地点', 'type': 'text'},
        {'path': '/世界/选项', 'label': '方式', 'type': 'select', 'options': [
            {'value': '基础'}, {'value': '扩展', 'when': [{'path': '/世界/当前地点', 'value': '中心'}]}]},
        {'path': '/世界/回合', 'label': '初始回合', 'type': 'number'},
    ]}
    config['runtime_rules'] = {'retention': [{'path': '/世界/档案/消息', 'max_items': 3}]}
    return config


class FeatureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.config = feature_config()

    def tearDown(self):
        self.temp.cleanup()

    def generator(self):
        (self.root / 'config.yaml').write_text(yaml.safe_dump(self.config, allow_unicode=True), encoding='utf-8')
        return SillyTavernGenerator(str(self.root))

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        return path

    def test_update_rules_validate_and_reach_update_prompt(self):
        self.config['mvu']['update_rules'] = [{'path': '/人物/*/所在地点', 'when': '已经到达', 'update': '同步在场'}]
        generator = self.generator()
        entries = generator.generate_lorebook()['entries'].values()
        content = '\n'.join(e['content'] for e in entries if '[mvu_update]' in e['comment'])
        self.assertIn('已经到达', content)
        self.assertIn('同步在场', content)
        self.config['mvu']['update_rules'][0]['path'] = '/人物/*/不存在'
        with self.assertRaises(ValueError):
            self.generator()

    def test_metric_scope_normalization_and_runtime_validation(self):
        metric = self.config['state_model']['character_metrics'][0]
        metric['exclude_entities'] = ['主角']
        generator = self.generator()
        state = generator._build_initial_state({'state': {'人物': {'主角': {}, '访客': {}}}})
        self.assertNotIn(metric['id'], state['人物']['主角']['数值'])
        self.assertIn(metric['id'], state['人物']['访客']['数值'])
        with self.assertRaises(ValueError):
            generator._build_initial_state({'state': {'人物': {'主角': {'数值': {metric['id']: 0}}}}})
        payload = self.write('scope.json', json.dumps({'state': state, 'collections': list(generator.collections.values()), 'metrics': generator.metrics}, ensure_ascii=False))
        runner = self.write('scope.cjs', """
const assert=require('node:assert/strict'),fs=require('node:fs');
const rules=require(process.argv[2]), p=JSON.parse(fs.readFileSync(process.argv[3]));
assert.deepEqual(rules.validate(p.state,p.collections,p.metrics),[]);
const id=p.metrics[0].id;
p.state.人物.主角.数值[id]=0;
assert(rules.validate(p.state,p.collections,p.metrics).length);
delete p.state.人物.主角.数值[id];delete p.state.人物.访客.数值[id];
assert(rules.validate(p.state,p.collections,p.metrics).length);
""")
        result = subprocess.run(['node', str(runner), str(PROJECT_ROOT / 'templates/mvu/rules.js'), str(payload)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_opening_payload_is_pending_and_protocol_is_depth_system(self):
        generator = self.generator()
        script = generator._build_panel_script()
        marker = 'const CONFIG = '
        start = script.index(marker) + len(marker)
        payload, _ = json.JSONDecoder().raw_decode(script[start:])
        self.assertFalse(payload['opening']['state']['世界']['已初始化'])
        self.assertFalse(generator._build_initial_state()['世界']['已初始化'])
        self.assertTrue(generator._build_initial_state({}, Path('scenario'))['世界']['已初始化'])
        card = generator.generate_narrator_card(generator.generate_lorebook())
        self.assertEqual(card['data']['extensions']['world'], card['data']['character_book']['name'])
        entries = card['data']['character_book']['entries']
        self.assertTrue(any('[mvu_update]' in e['comment'] for e in entries))
        self.assertTrue(any(e['comment'] == '合理性审查与开局' for e in entries))
        for entry in entries:
            if entry['comment'].startswith('[mvu_'):
                self.assertEqual(entry['extensions']['position'], 4)
                self.assertEqual(entry['extensions']['depth'], 0)
                self.assertEqual(entry['extensions']['role'], 0)
        del self.config['state_model']['collections']['world']['fields']['当前地点']
        self.config.pop('opening')
        self.generator()  # Scene location is an author field, not a lifecycle requirement.

    def test_nested_state_normalization_and_schema(self):
        generator = self.generator()
        initial = generator._build_initial_state({'state': {'世界': {'档案': {'消息': [{'内容': 'hello'}], '技能': {'观察': 2}}}}})
        self.assertEqual(initial['世界']['档案']['消息'][0]['编号'], 0)
        self.assertEqual(initial['世界']['档案']['技能']['观察'], 2)
        script = generator._build_zod_script()
        self.assertIn('z.array(z.object', script)
        self.assertIn('z.record(z.string(), z.coerce.number()', script)
        with self.assertRaisesRegex(ValueError, 'unknown fields'):
            generator._build_initial_state({'state': {'世界': {'档案': {'额外': True}}}})
        with self.assertRaisesRegex(ValueError, 'max_items'):
            generator._build_initial_state({'state': {'世界': {'档案': {'消息': [{}] * 4}}}})
        self.config['state_model']['collections']['world']['fields']['坏字段'] = {'type': 'array', 'items': {'type': 'mystery'}}
        with self.assertRaisesRegex(ValueError, 'Unsupported'):
            self.generator()

    def test_packages_cover_all_asset_types_without_leaks(self):
        self.config['content'] = {'enabled': ['a'], 'packages': {
            'common': {'root': 'packs/common'}, 'a': {'root': 'packs/a', 'requires': ['common'], 'exclusive_group': 'era'},
            'b': {'root': 'packs/b', 'exclusive_group': 'era'}}}
        self.config['entry_types']['setting']['source_files'] = ['**/设定.txt']
        self.config['entry_types']['relationship']['source_file'] = 'literature/fanfic/关系.txt'
        self.config['imports'] = {'scripts': ['literature/scripts/*.json']}
        for package in ['common', 'a', 'b']:
            prefix = f'packs/{package}/literature'
            self.write(f'{prefix}/characters/{package}.md', f'名称: {package}\n性格: {package}')
            self.write(f'{prefix}/fanfic/设定.txt', f'【规则{package}】（词{package}）\n{package}内容')
            self.write(f'{prefix}/fanfic/关系.txt', f'【关系{package}】（甲,乙）\n{package}关系')
            self.write(f'{prefix}/scenarios/{package}.md', f'---\nname: {package}\nstate: {{}}\n---\n{package}开局')
            self.write(f'{prefix}/scripts/{package}.json', json.dumps({'type': 'script', 'id': package, 'name': package, 'content': '// empty', 'enabled': False}))
        generator = self.generator()
        self.assertEqual([name for name, _ in generator.discover_characters()], ['a', 'common'])
        book = generator.generate_lorebook()
        comments = [e['comment'] for e in book['entries'].values()]
        self.assertIn('规则a', comments)
        self.assertNotIn('规则b', comments)
        self.assertIn('关系_关系a', comments)
        self.assertNotIn('关系_关系b', comments)
        self.assertEqual([s['metadata']['name'] for s in generator.load_scenarios()], ['common', 'a'])
        scripts = generator.build_tavern_helper_extension()['scripts']
        self.assertIn('a', [s['name'] for s in scripts])
        self.assertNotIn('b', [s['name'] for s in scripts])
        self.config['content']['enabled'] = ['a', 'b']
        with self.assertRaisesRegex(ValueError, 'Exclusive'):
            self.generator()
        self.config['content']['enabled'] = ['a']
        self.config['content']['packages']['common']['requires'] = ['a']
        with self.assertRaisesRegex(ValueError, 'cycle'):
            self.generator()

    def test_duplicate_character_and_missing_reference_are_errors(self):
        self.config['content'] = {'enabled': ['extra'], 'packages': {'extra': {'root': 'packs/extra'}}}
        self.write('literature/characters/甲.md', '名称: 甲')
        self.write('packs/extra/literature/characters/甲.md', '名称: 甲')
        with self.assertRaisesRegex(ValueError, 'Duplicate character'):
            self.generator()
        self.config['content'] = {}
        self.config['imports'] = {'entries': ['literature/raw.json']}
        self.write('literature/raw.json', json.dumps({'entries': [{'comment': '引用', 'content': "<%- await getwi(null, '缺失') -%>"}]}))
        with self.assertRaisesRegex(ValueError, 'Missing worldbook reference'):
            self.generator().generate_lorebook()

    def test_rule_and_form_paths_are_validated(self):
        self.config['opening']['fields'][0]['path'] = '/世界/不存在'
        with self.assertRaisesRegex(ValueError, 'Unknown schema path'):
            self.generator()
        self.config = feature_config()
        self.config['runtime_rules']['transitions'] = [{'path': '/事件/*/阶段', 'allowed': {'起': ['不存在']}}]
        with self.assertRaisesRegex(ValueError, 'enum'):
            self.generator()

    def test_generated_js_parses_and_panel_exports_independently(self):
        generator = self.generator()
        generator.save_files()
        panel = json.loads((self.root / 'output/悬浮状态栏.json').read_text())
        card = json.loads((self.root / 'output/测试作品叙事者.json').read_text())
        scripts = card['data']['extensions']['tavern_helper']['scripts']
        self.assertEqual(panel, next(s for s in scripts if s['name'] == 'MVU 悬浮状态面板'))
        self.assertIn('character_book', card['data'])
        for script in scripts[1:]:
            path = self.write('check.mjs', script['content'])
            result = subprocess.run(['node', '--check', str(path)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_png_roundtrip_preserves_pixels_and_metadata(self):
        cover = self.root / 'cover.png'
        cover.write_bytes(SIGNATURE + chunk(b'IHDR', struct.pack('>IIBBBBB', 1, 1, 8, 6, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(b'\x00\x00\x00\x00\xff')) + chunk(b'IEND', b''))
        card = {'spec': 'chara_card_v3', 'spec_version': '3.0', 'data': {'name': '通用测试', 'character_book': {'entries': [
            {'id': 1, 'name': '禁用但被引用', 'enabled': False, 'keys': ['甲'], 'content': '原文\n原样保留'},
            {'id': 2, 'name': '引用', 'content': "<%- await getwi(null, '禁用但被引用') -%>"}]}, 'extensions': {'scripts': [{'content': 'DO NOT EXECUTE'}]}}}
        output = self.root / 'card.png'
        write_card_png(cover, card, output)
        self.assertEqual(read_card(output), card)
        self.assertEqual([data for kind, data in png_chunks(cover.read_bytes()) if kind == b'IDAT'], [data for kind, data in png_chunks(output.read_bytes()) if kind == b'IDAT'])
        report = inspect_card(output)
        self.assertEqual(report['entries'][1]['missing_references'], [])
        with self.assertRaisesRegex(ValueError, 'Review'):
            restore(report, self.root)
        for row in report['entries']:
            row['category'] = 'raw'
        restore(report, self.root)
        entries = json.loads((self.root / 'literature/imported/entries.json').read_text())['entries']
        self.assertTrue(entries[0]['disable'])
        self.assertEqual(entries[0]['content'], '原文\n原样保留')
        self.assertEqual(json.loads((self.root / 'literature/imported/original-card.json').read_text()), card)
        self.config['imports'] = {'entries': ['literature/imported/entries.json']}
        book = self.generator().generate_lorebook()
        self.assertTrue(next(e for e in book['entries'].values() if e['comment'] == '禁用但被引用')['disable'])
        broken = bytearray(cover.read_bytes()); broken[20] ^= 1
        with self.assertRaisesRegex(ValueError, 'CRC'):
            list(png_chunks(broken))

    def test_live_hook_rejects_invalid_batch_and_cleans_up(self):
        generator = self.generator()
        script = self.write('guard.js', generator._build_rules_script())
        state = generator._build_initial_state()
        state['世界']['已初始化'] = True
        initial = self.write('initial.json', json.dumps(state, ensure_ascii=False))
        runner = self.write('hook.cjs', r"""
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const handlers = new Map();
const host = {parent:null, console, addEventListener(){}, removeEventListener(){},
  Mvu:{events:{VARIABLE_UPDATE_ENDED:'updated',COMMAND_PARSED:'commands'}},
  eventOn(name, fn){handlers.set(name,fn)}, eventOff(name){handlers.delete(name)}};
host.parent=host;
vm.runInNewContext(fs.readFileSync(process.argv[2],'utf8'), {window:host, console});
const before=JSON.parse(fs.readFileSync(process.argv[3],'utf8'));
const next={stat_data:structuredClone(before)};
next.stat_data.世界.回合=-1;
handlers.get('updated')(next,{stat_data:before});
assert.deepEqual(JSON.parse(JSON.stringify(next.stat_data)),before);
assert(host.__worldbookRulesRuntime.errors.length);
const valid={stat_data:structuredClone(before)};valid.stat_data.世界.回合=1;
valid.stat_data.$internal={display_data:structuredClone(before),delta_data:{}};
handlers.get('updated')(valid,{stat_data:before});
assert.equal(valid.stat_data.世界.回合,1);
assert.equal(host.__worldbookRulesRuntime.errors.length,0);
// Model/API output is untrusted: reject unknown commands and lifecycle resets before execution.
for (const operation of [{op:'execute',path:'/世界/回合',value:9}, {op:'replace',path:'/世界',value:{已初始化:true,回合:9}}, {op:'delta',path:'/世界/回合',value:'9'}]) {
 const data={stat_data:structuredClone(before)};
 const commands=[{type:'set'}];
 handlers.get('commands')(data,commands,'<UpdateVariable><JSONPatch>'+JSON.stringify([operation])+'</JSONPatch></UpdateVariable>');
 assert.equal(commands.length,0);
 handlers.get('updated')(data,{stat_data:before});
 assert.deepEqual(JSON.parse(JSON.stringify(data.stat_data)),before);
 assert(host.__worldbookRulesRuntime.errors.length);
}
const data={stat_data:structuredClone(before)}, commands=[{type:'add'}];
handlers.get('commands')(data,commands,'<UpdateVariable><JSONPatch>[{"op":"delta","path":"/世界/回合","value":1}]</JSONPatch></UpdateVariable>');
assert.equal(commands.length,1);
data.stat_data.世界.回合=1;
handlers.get('updated')(data,{stat_data:before});
assert.equal(data.stat_data.世界.回合,1);
assert.equal(host.__worldbookRulesRuntime.errors.length,0);

host.__worldbookRulesRuntime.destroy();
assert.equal(handlers.size,0);
""")
        result = subprocess.run(['node', str(runner), str(script), str(initial)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_multi_turn_replay(self):
        result = subprocess.run(['node', str(PROJECT_ROOT / 'scripts/replay_state.js'), str(PROJECT_ROOT / 'tests/fixtures/multi_turn.json')], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(json.loads(result.stdout)['results']), 10)


if __name__ == '__main__':
    unittest.main()
