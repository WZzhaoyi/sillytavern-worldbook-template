import json
import shutil
import subprocess

import yaml
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.generate_sillytavern import SillyTavernGenerator  # noqa: E402


CONFIG = r'''
project:
  name: "测试作品"
  version: "3.0.0"
state_model:
  character_metrics:
    - id: "affection"
      name: "好感"
      description: "角色对主角的信任与亲近"
      initial: 10
      change:
        minor: [1, 2]
        major: [3, 5]
      ranges: [0, 50, 100]
      stages: ["亲密", "疏离"]
    - id: "power"
      name: "实力"
      description: "角色当前成长程度"
      initial: 0
      change:
        minor: [1, 2]
        major: [3, 5]
      ranges: [0, 100]
      stages: ["成长中"]
  collections:
    world:
      path: "世界"
      label: "世界"
      kind: "singleton"
      fields:
        已初始化: {type: "boolean", default: false, panel: false}
        回合: {type: "number", default: 0, min: 0}
        场景: {type: "string", default: "未初始化"}
        场景摘要: {type: "string", default: ""}
        时间: {type: "string", default: "未设定"}
        当前地点: {type: "string", default: "未设定"}
        天气: {type: "string", default: "未设定"}
    characters:
      path: "人物"
      label: "人物"
      kind: "collection"
      fields:
        在场: {type: "boolean", default: false}
        所在地点: {type: "string", default: ""}
        状态: {type: "string_list", default: []}
        当前目标: {type: "string", default: ""}
        关系: {type: "string", default: ""}
        数值: {type: "metrics", default: {}}
        备注: {type: "string", default: ""}
    items:
      path: "物品"
      label: "物品"
      kind: "collection"
      fields:
        已知: {type: "boolean", default: false}
        持有者: {type: "string", default: ""}
        所在地点: {type: "string", default: ""}
        数量: {type: "number", default: 1, min: 0}
        状态: {type: "string", default: "完好"}
    locations:
      path: "地点"
      label: "地点"
      kind: "collection"
      fields:
        已发现: {type: "boolean", default: false}
        状态: {type: "string", default: "正常"}
        描述: {type: "string", default: ""}
    events:
      path: "事件"
      label: "事件"
      kind: "collection"
      fields:
        状态: {type: "enum", default: "未触发", values: ["未触发", "进行中", "已完成"]}
        阶段: {type: "enum", default: "起", values: ["起", "承", "转", "合"]}
        地点: {type: "string", default: ""}
        参与者: {type: "string_list", default: []}
        摘要: {type: "string", default: ""}
mvu:
  max_characters_per_turn: 2
  max_entities_per_turn: 5
  max_active_events: 2
  preflight_max_words: 60
  preflight_checks:
    - "事实一致性：检查测试事实"
    - "行动可行性：检查测试资源"
    - "因果裁决：选择最小处理"
  update_analysis_max_words: 80
  panel:
    enabled: true
    width: 840
paths:
  scenarios_dir: "literature/scenarios"
  output_dir: "output"
character_generation:
  output_dir: "literature/characters"
  stages_format: "json"
entry_types:
  style:
    enabled: false
    source_file: "literature/fanfic/风格样本.txt"
  protagonist:
    prefix: ""
    order_start: 100
    order_step: 1
    depth: 4
    position: 0
    constant: false
    ignore_budget: true
  supporting:
    prefix: "配角_"
    order_start: 200
    order_step: 1
    depth: 5
    position: 0
    constant: false
    ignore_budget: true
  setting:
    source_files: []
    active_layer: ""
    layers: {}
  relationship:
    source_file: ""
sillytavern_defaults:
  entry:
    probability: 100
    use_probability: true
    scan_depth: 2
    selective_logic: 0
  narrator:
    spec: "chara_card_v3"
    spec_version: "3.0"
narrator:
  name: "测试叙事者"
  description: "测试"
  personality: "测试"
  creator: "test"
  persona: "你是测试叙事者。"
'''


class GeneratorMvuTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        (self.root / "config.yaml").write_text(CONFIG, encoding="utf-8")
        (self.root / "literature/characters").mkdir(parents=True)
        (self.root / "literature/scenarios").mkdir(parents=True)
        (self.root / "literature/fanfic").mkdir(parents=True)

        (self.root / "literature/characters/林青.md").write_text(
            "名称: 林青\n性格: 克制\n",
            encoding="utf-8",
        )
        stages = {
            "metrics": {
                "affection": {
                    "亲密": "主动信任",
                    "疏离": "保持距离",
                },
                "power": {
                    "成长中": "谨慎运用当前能力",
                },
            },
        }
        (self.root / "literature/characters/林青_stages.json").write_text(
            json.dumps(stages, ensure_ascii=False),
            encoding="utf-8",
        )
        (self.root / "literature/fanfic/风格样本.txt").write_text(
            "【这只是正文标题】\n它属于文风样本，不是世界设定。\n",
            encoding="utf-8",
        )
        (self.root / "literature/scenarios/01_start.md").write_text(
            """---
name: 初见
description: 林中相遇
time: 黄昏
location: 青竹林
weather: 小雨
state:
  世界:
    回合: 0
  人物:
    林青:
      在场: true
      所在地点: 青竹林
      状态: [戒备]
      当前目标: 观察来客
      关系: 陌生人
      数值: {affection: 25, power: 120}
      备注: ""
  物品:
    青竹伞:
      已知: true
      持有者: 林青
      所在地点: ""
      数量: 1
      状态: 完好
  地点:
    青竹林:
      已发现: true
      状态: 正常
      描述: 林雨绵密
  事件:
    林中初见:
      状态: 进行中
      阶段: 起
      地点: 青竹林
      参与者: [林青]
      摘要: 陌生人相遇
---
林青从树影中走出。
""",
            encoding="utf-8",
        )
        self.generator = SillyTavernGenerator(str(self.root))

    def tearDown(self):
        self.tempdir.cleanup()

    def run_cli(self, script, *args):
        return subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "scripts" / script), *args],
            cwd=self.root, capture_output=True, text=True,
        )

    def test_cli_keeps_same_named_works_and_shared_template_independent(self):
        # Both works deliberately use the same project name and filenames.
        works = self.root / "works"
        for name in ("甲作品", "乙作品"):
            work = works / name
            shutil.copytree(self.root / "literature", work / "literature")
            (work / "config.yaml").write_text(
                CONFIG.replace('source_files: []', 'source_files: ["literature/fanfic/*.txt"]'),
                encoding="utf-8",
            )
            (work / "literature/fanfic/设定.txt").write_text(
                f"【{name}专属】（{name}）\n{name}的独有规则。", encoding="utf-8",
            )
        first_output = None
        for name, other in (("甲作品", "乙作品"), ("乙作品", "甲作品")):
            result = self.run_cli("generate_sillytavern.py", "--work", f"works/{name}")
            self.assertEqual(result.returncode, 0, result.stderr)
            output = works / name / "output"
            self.assertEqual(
                {p.name for p in output.iterdir()},
                {"测试作品世界书.json", "测试作品叙事者.json", "悬浮状态栏.json"},
            )
            book = (output / "测试作品世界书.json").read_text(encoding="utf-8")
            self.assertIn(f"{name}专属", book)
            self.assertNotIn(f"{other}专属", book)
            card = json.loads((output / "测试作品叙事者.json").read_text(encoding="utf-8"))
            self.assertIn("MVU 悬浮状态面板", str(card))
            self.assertFalse((works / name / "templates").exists())
            if name == "甲作品":
                first_output = book
        self.assertEqual(
            (works / "甲作品/output/测试作品世界书.json").read_text(encoding="utf-8"),
            first_output,
        )

    def test_conversion_only_changes_selected_work_and_preserves_data(self):
        work = self.root / "另一作品"
        shutil.copytree(self.root / "literature", work / "literature")
        (work / "config.yaml").write_text(CONFIG, encoding="utf-8")
        source = work / "literature/characters/林青_stages.json"
        original = json.loads(source.read_text(encoding="utf-8"))
        args = ("yaml", "--work", str(work))
        preview = self.run_cli("convert_stages_format.py", *args, "--dry-run")
        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertTrue(source.exists())
        self.assertFalse(source.with_suffix(".yaml").exists())
        self.assertEqual((work / "config.yaml").read_text(encoding="utf-8"), CONFIG)
        result = self.run_cli("convert_stages_format.py", *args)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(source.exists())
        self.assertEqual(yaml.safe_load(source.with_suffix(".yaml").read_text(encoding="utf-8")), original)
        config = yaml.safe_load((work / "config.yaml").read_text(encoding="utf-8"))
        self.assertEqual(config["character_generation"]["stages_format"], "yaml")
        self.assertEqual((self.root / "config.yaml").read_text(encoding="utf-8"), CONFIG)
        self.assertTrue((self.root / "literature/characters/林青_stages.json").exists())
        generated = self.run_cli("generate_sillytavern.py", "--work", str(work))
        self.assertEqual(generated.returncode, 0, generated.stderr)

    def test_cli_requires_work_and_bad_config_does_not_convert_files(self):
        for script, args in (("generate_sillytavern.py", ()), ("convert_stages_format.py", ("yaml",))):
            result = self.run_cli(script, *args)
            self.assertEqual(result.returncode, 2)
            self.assertIn("--work", result.stderr)
        (self.root / "config.yaml").write_text("state_model: [\n", encoding="utf-8")
        result = self.run_cli("convert_stages_format.py", "yaml", "--work", ".")
        self.assertEqual(result.returncode, 1)
        self.assertIn("config.yaml", result.stderr)
        self.assertTrue((self.root / "literature/characters/林青_stages.json").exists())
        self.assertFalse((self.root / "literature/characters/林青_stages.yaml").exists())
        result = self.run_cli("generate_sillytavern.py", "--work", ".")
        self.assertEqual(result.returncode, 1)
        self.assertIn("config.yaml", result.stderr)
        self.assertIn("line 2", result.stderr)

    def test_scenario_initializes_all_state_collections(self):
        scenario = self.generator.load_scenarios()[0]["body"]
        self.assertIn("<UpdateVariable>", scenario)
        for path in ("世界", "人物", "物品", "地点", "事件"):
            self.assertIn(f'"path": "/{path}"', scenario)
        self.assertIn('"已初始化": true', scenario)
        self.assertIn('"当前地点": "青竹林"', scenario)
        self.assertIn('"affection": 25', scenario)
        self.assertIn('"power": 100', scenario)
        self.assertIn('"阶段": "起"', scenario)
        self.assertNotIn('"视角"', scenario)
        self.assertNotIn("_.set(", scenario)
        self.assertNotIn("character_states_init", scenario)

    def test_character_entry_uses_mvu_stage_contract(self):
        entry = self.generator.create_character_entry("林青", 0)
        self.assertIn("<mvu_stage_contract>", entry["content"])
        self.assertIn("/人物/林青/数值/affection", entry["content"])
        self.assertIn("0 ≤ x < 50 => 疏离", entry["content"])
        self.assertIn('"亲密": "主动信任"', entry["content"])
        self.assertNotIn("<character_states>", entry["content"])
        self.assertFalse(entry["selective"])

    def test_generated_card_embeds_runtime_schema_panel_and_regexes(self):
        card = self.generator.generate_narrator_card()
        extensions = card["data"]["extensions"]
        scripts = extensions["tavern_helper"]["scripts"]
        self.assertEqual([script["name"] for script in scripts], [
            "MVU", "MVU Schema", "MVU 悬浮状态面板"
        ])
        self.assertIn("registerMvuSchema", scripts[1]["content"])
        for path in ("世界", "人物", "物品", "地点", "事件"):
            self.assertIn(path, scripts[1]["content"])
        self.assertIn("attachShadow", scripts[2]["content"])
        self.assertIn("activeCollectionId", scripts[2]["content"])
        self.assertNotIn("iframe", scripts[2]["content"].lower())
        self.assertEqual(len(extensions["regex_scripts"]), 3)
        self.assertIn("StateCheck", extensions["regex_scripts"][1]["findRegex"])
        self.assertEqual(card["data"]["post_history_instructions"], "")

    def test_lorebook_contains_mvu_protocol(self):
        lorebook = self.generator.generate_lorebook()
        entries = list(lorebook["entries"].values())
        by_comment = {entry["comment"]: entry for entry in entries}
        self.assertIn("[mvu_protocol]生命周期协议", by_comment)
        self.assertIn("[mvu_current]变量列表", by_comment)
        self.assertNotIn("身份_模式目录", by_comment)
        self.assertEqual(
            [key for key in by_comment if key.startswith("[mvu_")],
            ["[mvu_protocol]生命周期协议", "[mvu_current]变量列表"],
        )
        protocol = by_comment["[mvu_protocol]生命周期协议"]["content"]
        self.assertIn(
            "同时最多维持 2 个“进行中”事件",
            protocol,
        )
        self.assertIn(
            "不得为刷新状态栏而强制推进",
            protocol,
        )
        self.assertIn("开局创建规则", protocol)
        self.assertIn("正文前一致性检查", protocol)
        self.assertIn("事实一致性：检查测试事实", protocol)
        self.assertIn("行动可行性：检查测试资源", protocol)
        self.assertIn("因果裁决：选择最小处理", protocol)
        self.assertIn("proceed、constrain、reframe、reject", protocol)
        self.assertIn("最小事实提交批次", protocol)
        self.assertIn("用户请求但正文未发生", protocol)
        self.assertIn("move 使用 op/from/to", protocol)
        self.assertIn("MVU 每轮输出格式", protocol)
        self.assertTrue(by_comment["[initvar]"]["disable"])
        self.assertIn("已初始化: false", by_comment["[initvar]"]["content"])
        for entry in entries:
            if entry.get("selective"):
                self.assertTrue(entry.get("keysecondary"), entry["comment"])
        serialized = json.dumps(lorebook, ensure_ascii=False)
        self.assertNotIn("_.set(", serialized)
        self.assertNotIn("/世界/视角", serialized)
        self.assertNotIn("审理人格", serialized)
        self.assertNotIn("<logic_check>", serialized)

    def test_preflight_checks_must_be_exactly_three_non_empty_strings(self):
        broken_config = CONFIG.replace(
            '  preflight_checks:\n'
            '    - "事实一致性：检查测试事实"\n'
            '    - "行动可行性：检查测试资源"\n'
            '    - "因果裁决：选择最小处理"\n',
            '  preflight_checks: "不是列表"\n',
            1,
        )
        (self.root / "config.yaml").write_text(broken_config, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "mvu\\.preflight_checks"):
            SillyTavernGenerator(str(self.root))

        broken_config = CONFIG.replace(
            '    - "因果裁决：选择最小处理"\n',
            '',
            1,
        )
        (self.root / "config.yaml").write_text(broken_config, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "exactly three"):
            SillyTavernGenerator(str(self.root))

    def test_removed_pov_config_is_rejected(self):
        broken_config = CONFIG.replace(
            "  relationship:\n",
            "  pov:\n    source_file: \"literature/fanfic/视角切换.txt\"\n"
            "  relationship:\n",
            1,
        )
        (self.root / "config.yaml").write_text(broken_config, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "entry_types\\.pov has been removed"):
            SillyTavernGenerator(str(self.root))

    def test_removed_scenario_pov_is_rejected(self):
        path = self.root / "literature/scenarios/02_old_pov.md"
        path.write_text(
            "---\nname: 旧场景\npov: 第一人称\n---\n开场。\n",
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "pov frontmatter has been removed"):
            self.generator.parse_scenario_file(path)

    def test_invalid_change_range_is_rejected_before_generation(self):
        broken_config = CONFIG.replace("minor: [1, 2]", "minor: [3, 1]", 1)
        (self.root / "config.yaml").write_text(broken_config, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, r"change\.minor"):
            SillyTavernGenerator(str(self.root))

    def test_stage_files_cannot_redeclare_numeric_boundaries(self):
        old_format = {
            "metrics": {
                "affection": {
                    "ranges": [{"min": 0, "max": 100, "content": "冲突边界"}],
                },
                "power": {"成长中": "正常"},
            }
        }
        path = self.root / "literature/characters/林青_stages.json"
        path.write_text(json.dumps(old_format, ensure_ascii=False), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "missing stages|unknown stages"):
            self.generator.create_character_entry("林青", 0)

    def test_relationship_requires_primary_and_optional_filter(self):
        path = self.root / "literature/fanfic/关系网.txt"
        path.write_text(
            "【林青与沈月】（林青,沈月,月儿）\n两人曾共同守城。\n",
            encoding="utf-8",
        )
        self.generator.entry_types["relationship"]["source_file"] = str(path)
        entry = self.generator.extract_relationship_entries(0)[0]
        self.assertEqual(entry["key"], ["林青"])
        self.assertEqual(entry["keysecondary"], ["沈月", "月儿"])
        self.assertTrue(entry["selective"])

    def test_setting_entries_only_become_constant_with_star(self):
        path = self.root / "literature/fanfic/设定总集.txt"
        path.write_text(
            "★【世界公理】（规则）\n代价不可凭空消失。\n\n"
            "【青竹林】（青竹林）\n城外竹林。\n",
            encoding="utf-8",
        )
        self.generator.entry_types["setting"]["source_files"] = [str(path)]
        entries = self.generator.extract_setting_entries(0)
        self.assertTrue(entries[0]["constant"])
        self.assertFalse(entries[1]["constant"])
        self.assertFalse(entries[1]["selective"])

    def test_generic_setting_scan_excludes_files_owned_by_other_modules(self):
        self.generator.entry_types["setting"]["source_files"] = [
            str(self.root / "literature/fanfic/*.txt")
        ]
        comments = [entry["comment"] for entry in self.generator.extract_setting_entries(0)]
        self.assertNotIn("这只是正文标题", comments)

    def test_style_is_disabled_lorebook_entry_and_preserves_complete_sample(self):
        sample = "第一段。\n\n  保留缩进。\n【只是样本文字】\n" + "长句。" * 1500 + "\n"
        (self.root / "literature/fanfic/风格样本.txt").write_text(sample, encoding="utf-8")
        book = self.generator.generate_lorebook()
        entries = [e for e in book['entries'].values() if e['comment'] == '[style]风格样本']
        self.assertEqual(len(entries), 1)
        self.assertTrue(entries[0]['disable'])
        self.assertTrue(entries[0]['constant'])
        self.assertFalse(entries[0]['ignoreBudget'])
        self.assertEqual(entries[0]['content'], sample)
        card = self.generator.generate_narrator_card(book)['data']
        self.assertEqual(card['description'], '测试')
        self.assertEqual(card['post_history_instructions'], '')
        self.assertFalse(next(e for e in card['character_book']['entries'] if e['comment'] == '[style]风格样本')['enabled'])
        self.generator.entry_types['style']['enabled'] = True
        self.assertFalse(self.generator.extract_style_entries(0)[0]['disable'])

    def test_style_missing_or_empty_is_optional_unless_enabled(self):
        path = self.root / 'literature/fanfic/风格样本.txt'
        path.unlink()
        self.assertEqual(self.generator.extract_style_entries(0), [])
        self.generator.entry_types['style']['enabled'] = True
        with self.assertRaisesRegex(ValueError, 'no nonempty style sample'):
            self.generator.extract_style_entries(0)
        path.write_text(' \n\n', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'no nonempty style sample'):
            self.generator.extract_style_entries(0)

    def test_style_follows_package_selection_and_excludes_generic_scan(self):
        from scripts.content_packages import ContentPackages
        for name in ('active', 'inactive'):
            directory = self.root / f'packs/{name}/literature/fanfic'
            directory.mkdir(parents=True)
            (directory / '风格样本.txt').write_text(f'【{name}样本】\n{name}', encoding='utf-8')
        self.generator.content = ContentPackages(self.root, {
            'enabled': ['active'], 'packages': {'active': {'root': 'packs/active'}, 'inactive': {'root': 'packs/inactive'}},
        })
        self.generator.entry_types['setting']['source_files'] = ['**/*.txt']
        entry = self.generator.extract_style_entries(0)[0]
        self.assertIn('active样本', entry['content'])
        self.assertNotIn('inactive样本', entry['content'])
        self.assertEqual(self.generator.extract_setting_entries(1), [])

    def test_setting_build_includes_only_active_content_layer(self):
        common = self.root / "literature/fanfic/common.txt"
        early_dir = self.root / "literature/fanfic/layers/early"
        late_dir = self.root / "literature/fanfic/layers/late"
        early_dir.mkdir(parents=True)
        late_dir.mkdir(parents=True)
        common.write_text("【共同规则】（共同规则）\n始终有效。\n", encoding="utf-8")
        (early_dir / "early.txt").write_text(
            "【前期地点】（前期地点）\n当前层内容。\n", encoding="utf-8"
        )
        (late_dir / "late.txt").write_text(
            "【后期地点】（后期地点）\n互斥层内容。\n", encoding="utf-8"
        )
        setting = self.generator.entry_types["setting"]
        setting["source_files"] = [str(common)]
        setting["active_layer"] = "early"
        setting["layers"] = {
            "early": [str(early_dir / "*.txt")],
            "late": [str(late_dir / "*.txt")],
        }
        comments = [entry["comment"] for entry in self.generator.extract_setting_entries(0)]
        self.assertEqual(comments, ["共同规则", "前期地点"])
        self.assertNotIn("后期地点", comments)

    def test_initvar_is_uninitialized_and_scenario_is_initialized(self):
        self.assertFalse(self.generator._build_initial_state()["世界"]["已初始化"])
        scenario_state = self.generator._build_initial_state(
            {"state": {"世界": {"已初始化": False}}},
            self.root / "custom.md",
        )
        self.assertTrue(scenario_state["世界"]["已初始化"])

    def test_unknown_state_field_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unknown fields"):
            self.generator._build_initial_state(
                {"state": {"人物": {"林青": {"不存在字段": 1}}}},
                self.root / "broken.md",
            )

    def test_each_opening_replaces_complete_snapshot_without_cross_contamination(self):
        second = self.root / "literature/scenarios/02_second.md"
        second.write_text(
            """---
name: 第二开局
state:
  世界: {}
  人物:
    沈月:
      数值: {affection: 40}
  物品: {}
  地点: {}
  事件: {}
---
沈月推门而入。
""",
            encoding="utf-8",
        )
        first_body = self.generator.parse_scenario_file(
            self.root / "literature/scenarios/01_start.md"
        )["body"]
        second_body = self.generator.parse_scenario_file(second)["body"]
        self.assertIn("林青", first_body)
        self.assertNotIn("沈月", first_body)
        self.assertIn("沈月", second_body)
        self.assertNotIn("林青", second_body)
        self.assertEqual(second_body.count('"op": "replace"'), 5)


if __name__ == "__main__":
    unittest.main()
