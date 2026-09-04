import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.generate_sillytavern import SillyTavernGenerator  # noqa: E402


CONFIG = r'''
## 2. 配置区

```yaml
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
  example_dialogue_file: "literature/fanfic/示例对话.txt"
  style_instructions: "保持简洁。"
  persona: "你是测试叙事者。"
```

## 3. 工作流步骤
'''


class GeneratorMvuTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        (self.root / "AGENTS.md").write_text(CONFIG, encoding="utf-8")
        (self.root / "literature/characters").mkdir(parents=True)
        (self.root / "literature/scenarios").mkdir(parents=True)
        (self.root / "literature/fanfic").mkdir(parents=True)
        (self.root / "templates/mvu").mkdir(parents=True)
        shutil.copy(
            PROJECT_ROOT / "templates/mvu/floating_panel.js",
            self.root / "templates/mvu/floating_panel.js",
        )

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
        (self.root / "literature/fanfic/示例对话.txt").write_text(
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
        self.assertEqual(card["data"]["post_history_instructions"], "保持简洁。")

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
        self.assertIn("MVU 每轮输出格式", protocol)
        self.assertTrue(by_comment["[initvar]"]["disable"])
        self.assertIn("已初始化: false", by_comment["[initvar]"]["content"])
        for entry in entries:
            if entry.get("selective"):
                self.assertTrue(entry.get("keysecondary"), entry["comment"])
        serialized = json.dumps(lorebook, ensure_ascii=False)
        self.assertNotIn("_.set(", serialized)
        self.assertNotIn("/世界/视角", serialized)

    def test_removed_pov_config_is_rejected(self):
        broken_config = CONFIG.replace(
            "  relationship:\n",
            "  pov:\n    source_file: \"literature/fanfic/视角切换.txt\"\n"
            "  relationship:\n",
            1,
        )
        (self.root / "AGENTS.md").write_text(broken_config, encoding="utf-8")
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
        (self.root / "AGENTS.md").write_text(broken_config, encoding="utf-8")
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
