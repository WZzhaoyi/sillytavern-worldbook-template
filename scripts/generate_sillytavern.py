#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SillyTavern 世界书和角色卡生成器
版本: 3.0.0 (MVU lifecycle)
"""

import argparse
import json
import math
import re
import sys
import uuid
import yaml
from copy import deepcopy
from pathlib import Path
from typing import Dict, List, Any, Tuple
from datetime import datetime

if __package__:
    from .content_packages import ContentPackages
else:
    from content_packages import ContentPackages


DEFAULT_PREFLIGHT_CHECKS = [
    "事实一致性：核对时间、地点、在场实体、物品归属、事件阶段与当前变量，不从旧聊天重新累计状态",
    "行动可行性：核对能力、资源、知识来源、地理可达性、人物动机与玩家控制权",
    "因果裁决：在 proceed、constrain、reframe、reject 中选择最小必要处理，优先保留用户意图并落实合理代价",
]


class IndentedSafeDumper(yaml.SafeDumper):
    """PyYAML dumper that indents list items under their parent key."""

    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, False)


class ConfigLoader:
    """读取作品目录中的独立 YAML 配置。"""

    @staticmethod
    def load_config(project_root: Path) -> Dict[str, Any]:
        config_file = project_root / "config.yaml"
        try:
            config = yaml.safe_load(config_file.read_text(encoding='utf-8'))
        except yaml.YAMLError as exc:
            raise ValueError(f"YAML 解析失败: {config_file}\n{exc}") from exc
        if not isinstance(config, dict):
            raise ValueError(f"{config_file} must contain a YAML mapping")
        return config


class SillyTavernGenerator:
    def __init__(self, project_root: str):
        self.project_root = Path(project_root).resolve()
        self.config = ConfigLoader.load_config(self.project_root)

        paths = self.config.get('paths', {})
        char_gen = self.config.get('character_generation', {})
        self.characters_dir = self.project_root / char_gen.get('output_dir', 'literature/characters')
        self.scenarios_dir = self.project_root / paths.get('scenarios_dir', 'literature/scenarios')
        self.output_dir = self.project_root / paths.get('output_dir', 'output')
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.state_model = self.config.get('state_model') or {}
        self.metrics = self.state_model.get('character_metrics') or []
        self.collections = self.state_model.get('collections') or {}
        self.mvu_config = self.config.get('mvu') or {}
        self.entry_types = self.config.get('entry_types', {})
        self.silly_defaults = self.config.get('sillytavern_defaults', {})
        self.preflight_checks = self._load_preflight_checks()
        self.content = ContentPackages(self.project_root, self.config.get('content'))
        self.character_files = {}
        for path in self.content.files([str(Path(char_gen.get('output_dir', 'literature/characters')) / '*.md')]):
            if path.stem in self.character_files:
                raise ValueError(f'Duplicate character across selected packages: {path.stem}')
            self.character_files[path.stem] = path
        if self.content.selected and self.entry_types.get('setting', {}).get('active_layer'):
            raise ValueError('Use content packages or legacy active_layer, not both')

        if 'pov' in self.entry_types:
            raise ValueError(
                "entry_types.pov has been removed; choose one fixed narrative viewpoint "
                "and write it in narrator.persona"
            )
        
        # 阶段数据文件格式：json 或 yaml（选定后统一使用，不可混用）
        self.stages_format = char_gen.get('stages_format', 'json')
        if self.stages_format not in ('json', 'yaml'):
            raise ValueError(f"character_generation.stages_format must be 'json' or 'yaml', got: '{self.stages_format}'")

        self._validate_state_model()
        self._build_initial_state()
        self._validate_features()
        update_rules = self.mvu_config.get("update_rules", [])
        if not isinstance(update_rules, list):
            raise ValueError("mvu.update_rules must be a list")
        for rule in update_rules:
            if not isinstance(rule, dict):
                raise ValueError("mvu.update_rules entries must be mappings")
            self._field_at_path(rule.get("path"))
            for key in ("when", "update"):
                if not isinstance(rule.get(key), str) or not rule[key].strip():
                    raise ValueError(f"mvu.update_rules requires nonempty {key}")

    def _field_at_path(self, path):
        if not isinstance(path, str) or not path.startswith('/'):
            raise ValueError(f'Expected JSON pointer: {path}')
        keys = [key.replace('~1', '/').replace('~0', '~') for key in path[1:].split('/')]
        if any(key in ('__proto__', 'constructor', 'prototype') for key in keys):
            raise ValueError(f'Unsafe path: {path}')
        root = {'type': 'object', 'fields': {
            c['path']: {'type': 'object', 'fields': c['fields']} if c['kind'] == 'singleton'
            else {'type': 'record', 'items': {'type': 'object', 'fields': c['fields']}}
            for c in self.collections.values()
        }}
        field = root
        for key in keys:
            if field['type'] == 'object':
                if key not in field['fields']:
                    raise ValueError(f'Unknown schema path: {path}')
                field = field['fields'][key]
            elif field['type'] in ('array', 'record'):
                field = field['items']
            elif field['type'] == 'metrics':
                metric = self._metric_by_id(key)
                field = {'type': 'number', 'min': metric['ranges'][0], 'max': metric['ranges'][-1]}
            else:
                raise ValueError(f'Path descends into scalar: {path}')
        return field

    def _validate_features(self):
        rules = self.config.get('runtime_rules') or {}
        self._field_at_path(rules.get('clock_path', '/世界/回合'))
        def condition(test):
            self._field_at_path(test['path'])
            if 'value_path' in test:
                self._field_at_path(test['value_path'])
            if test.get('op', 'eq') not in ('eq', 'ne', 'gte', 'lte', 'gt', 'lt', 'in', 'contains', 'exists', 'changed'):
                raise ValueError(f'Unknown condition operator: {test}')
        for rule in rules.get('transitions', []):
            field = self._field_at_path(rule['path'])
            values = field.get('values', [])
            if field['type'] != 'enum' or any(k not in values or any(v not in values for v in dest) for k, dest in rule['allowed'].items()):
                raise ValueError('Transitions must reference enum values')
        for rule in rules.get('constraints', []):
            if rule.get('for_each'):
                self._field_at_path(rule['for_each'])
            for test in rule.get('when', []) + rule.get('require', []):
                condition(test)
        for rule in rules.get('growth', []):
            if self._field_at_path(rule['path'])['type'] != 'number' or rule['max_per_tick'] < 0:
                raise ValueError('Growth requires numeric path and nonnegative max_per_tick')
            self._field_at_path(rule.get('clock_path', rules.get('clock_path', '/世界/回合')))
        for rule in rules.get('retention', []):
            if self._field_at_path(rule['path'])['type'] not in ('array', 'string_list') or rule['max_items'] < 1:
                raise ValueError('Retention requires array and positive max_items')
        for rule in rules.get('archives', []):
            source = self._field_at_path(rule['collection'])
            target = self._field_at_path(rule['target'])
            if source['type'] != 'record' or target['type'] != 'array' or rule['max_entries'] < 1:
                raise ValueError('Archives require collection, array target and positive max_entries')
            fields = source['items']['fields']
            for name in [rule['status_field']] + rule['summary_fields']:
                if name not in fields:
                    raise ValueError(f'Unknown archive field: {name}')
            if not set(rule['terminal_states']) <= set(fields[rule['status_field']].get('values', [])):
                raise ValueError('Unknown archive terminal state')
        encounter = rules.get('encounters')
        if encounter:
            for name, kind in [('cooldown_path', 'number'), ('seen_path', 'string_list'), ('selected_path', 'string')]:
                if self._field_at_path(encounter[name])['type'] != kind:
                    raise ValueError(f'encounters.{name} must point to {kind}')
            if encounter['cooldown_turns'] < 0:
                raise ValueError('Encounter cooldown must be nonnegative')
            ids = [c['id'] for c in encounter.get('candidates', [])]
            if len(ids) != len(set(ids)) or any(not value for value in ids):
                raise ValueError('Encounter ids must be unique and nonempty')
            for candidate in encounter.get('candidates', []):
                for test in candidate.get('when', []):
                    condition(test)
        opening = self.config.get('opening') or {}
        seen = set()
        for field in opening.get('fields', []):
            target = self._field_at_path(field['path'])
            if '*' in field['path'] or field['path'] in seen:
                raise ValueError('Opening fields need unique concrete paths')
            seen.add(field['path'])
            if field.get('type', 'text') not in ('text', 'number', 'select'):
                raise ValueError('Opening field type must be text, number or select')
            if field.get('type') == 'number' and target['type'] != 'number':
                raise ValueError('Opening number input requires numeric schema')
            if field.get('type') == 'select' and not field.get('options'):
                raise ValueError('Opening select requires options')
            for option in field.get('options', []):
                self._normalize_field_value(target, option['value'], field['path'])
                for test in option.get('when', []):
                    condition(test)
        if opening:
            self._build_initial_state({'state': opening.get('state', {})}, Path('custom'))

    def _runtime_payload(self):
        return {
            'rules': self.config.get('runtime_rules') or {},
            'collections': list(self.collections.values()), 'metrics': self.metrics,
        }

    def _build_rules_script(self):
        directory = Path(__file__).resolve().parents[1] / 'templates/mvu'
        return (directory / 'rules.js').read_text(encoding='utf-8') + '\n' + (directory / 'guard.js').read_text(encoding='utf-8').replace(
            '__MVU_RULES_CONFIG__', json.dumps(self._runtime_payload(), ensure_ascii=False))

    def _load_preflight_checks(self) -> List[str]:
        raw_checks = self.mvu_config.get('preflight_checks', DEFAULT_PREFLIGHT_CHECKS)
        if not isinstance(raw_checks, list) or len(raw_checks) != 3:
            raise ValueError("mvu.preflight_checks must contain exactly three strings")
        checks = []
        for index, check in enumerate(raw_checks):
            if not isinstance(check, str) or not check.strip():
                raise ValueError(
                    f"mvu.preflight_checks[{index}] must be a non-empty string"
                )
            checks.append(check.strip())
        return checks

    def _validate_state_model(self) -> None:
        """Validate the sole-source-of-truth schema before emitting MVU artifacts."""
        if not isinstance(self.collections, dict) or not self.collections:
            raise ValueError("state_model.collections must be a non-empty mapping")

        required_paths = {"世界", "人物", "物品", "地点", "事件"}
        path_list = [
            str(collection.get('path', '')).strip()
            for collection in self.collections.values()
            if isinstance(collection, dict)
        ]
        actual_paths = set(path_list)
        if len(path_list) != len(actual_paths):
            raise ValueError("state_model collection paths must be unique")
        missing_paths = required_paths - actual_paths
        if missing_paths:
            raise ValueError(
                "state_model.collections is missing required paths: "
                + ", ".join(sorted(missing_paths))
            )

        required_fields = {
            '世界': {'已初始化', '回合'},
            '人物': {'所在地点', '数值'},
            '物品': {'持有者', '所在地点'},
            '地点': {'已发现', '状态'},
            '事件': {'状态', '阶段'},
        }

        allowed_types = {"string", "number", "boolean", "string_list", "enum", "metrics", "object", "array", "record"}
        for collection_id, collection in self.collections.items():
            if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', str(collection_id)):
                raise ValueError(f"Invalid collection id: {collection_id!r}")
            if not isinstance(collection, dict):
                raise ValueError(f"Collection {collection_id} must be a mapping")
            if collection.get('kind') not in ("singleton", "collection"):
                raise ValueError(
                    f"Collection {collection_id}.kind must be singleton or collection"
                )
            expected_kind = 'singleton' if collection.get('path') == '世界' else 'collection'
            if collection.get('path') in required_paths and collection.get('kind') != expected_kind:
                raise ValueError(
                    f"Collection {collection_id}.kind must be {expected_kind} for {collection.get('path')}"
                )
            fields = collection.get('fields')
            if not isinstance(fields, dict) or not fields:
                raise ValueError(f"Collection {collection_id}.fields must be a non-empty mapping")
            missing_fields = required_fields.get(collection['path'], set()) - set(fields)
            if missing_fields:
                raise ValueError(
                    f"Collection {collection_id} is missing lifecycle fields: "
                    + ", ".join(sorted(missing_fields))
                )
            for field_name, field in fields.items():
                if not isinstance(field, dict) or field.get('type') not in allowed_types:
                    raise ValueError(
                        f"Collection {collection_id}.{field_name} has an unsupported field type"
                    )
                self._validate_field(field, f'{collection_id}.{field_name}')
                if field.get('type') == 'enum':
                    values = field.get('values')
                    if not isinstance(values, list) or not values or field.get('default') not in values:
                        raise ValueError(
                            f"Collection {collection_id}.{field_name}: enum requires values and a valid default"
                        )
            if collection['path'] == '人物' and fields['数值'].get('type') != 'metrics':
                raise ValueError("Collection characters.数值 must use type metrics")

        seen_ids = set()
        seen_names = set()
        for index, metric in enumerate(self.metrics):
            excluded = metric.get("exclude_entities", [])
            if not isinstance(excluded, list) or any(not isinstance(key, str) or not key for key in excluded):
                raise ValueError("metric.exclude_entities must be a list of entity keys")
            dim_id = str(metric.get('id', '')).strip()
            name = str(metric.get('name', '')).strip()
            ranges = metric.get('ranges', [])
            stages = metric.get('stages', [])

            if not dim_id or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', dim_id):
                raise ValueError(
                    f"state_model.character_metrics[{index}].id must be a stable ASCII identifier, got: {dim_id!r}"
                )
            if dim_id in seen_ids:
                raise ValueError(f"Duplicate character metric id: {dim_id}")
            if not name:
                raise ValueError(f"state_model.character_metrics[{index}].name cannot be empty")
            if name in seen_names:
                raise ValueError(f"Duplicate character metric name: {name}")
            if len(ranges) < 2 or len(stages) != len(ranges) - 1:
                raise ValueError(
                    f"Character metric {dim_id}: stages count must equal ranges count - 1"
                )
            if any(not isinstance(value, (int, float)) for value in ranges):
                raise ValueError(f"Character metric {dim_id}: ranges must contain numbers only")
            if any(left >= right for left, right in zip(ranges, ranges[1:])):
                raise ValueError(f"Character metric {dim_id}: ranges must be strictly increasing")

            initial = metric.get('initial', ranges[0])
            if not isinstance(initial, (int, float)) or not ranges[0] <= initial <= ranges[-1]:
                raise ValueError(
                    f"Character metric {dim_id}: initial must be within {ranges[0]}..{ranges[-1]}"
                )

            change = metric.get('change', {})
            if not isinstance(change, dict):
                raise ValueError(f"Character metric {dim_id}: change must be a mapping")
            for change_name, fallback in (("minor", [1, 2]), ("major", [3, 5])):
                bounds = change.get(change_name, fallback)
                if (
                    not isinstance(bounds, list)
                    or len(bounds) != 2
                    or any(not isinstance(value, (int, float)) or value < 0 for value in bounds)
                    or bounds[0] > bounds[1]
                ):
                    raise ValueError(
                        f"Character metric {dim_id}: change.{change_name} must be "
                        "[non-negative minimum, maximum]"
                    )

            seen_ids.add(dim_id)
            seen_names.add(name)

    def _validate_field(self, field, context):
        kind = field.get('type')
        if kind == 'object':
            if not isinstance(field.get('fields'), dict):
                raise ValueError(f'{context}.fields must be a mapping')
            for name, child in field['fields'].items():
                self._validate_field(child, f'{context}.{name}')
        elif kind in ('array', 'record'):
            if not isinstance(field.get('items'), dict):
                raise ValueError(f'{context}.items must describe values')
            self._validate_field(field['items'], f'{context}.items')
            if 'max_items' in field and (not isinstance(field['max_items'], int) or field['max_items'] < 1):
                raise ValueError(f'{context}.max_items must be positive')
        elif kind not in ('string', 'number', 'boolean', 'enum', 'string_list', 'metrics'):
            raise ValueError(f'Unsupported field type: {context}')
        self._normalize_field_value(field, field.get('default'), context)

    def find_stages_file(self, char_name: str) -> Tuple[Path, str]:
        preferred_file = self.character_files.get(char_name, self.characters_dir / f"{char_name}.md").parent / f"{char_name}_stages.{self.stages_format}"
        if preferred_file.exists():
            return preferred_file, self.stages_format

        for stages_format, suffix in (("json", ".json"), ("yaml", ".yaml"), ("yaml", ".yml")):
            stages_file = self.character_files.get(char_name, self.characters_dir / f"{char_name}.md").parent / f"{char_name}_stages{suffix}"
            if stages_file.exists():
                return stages_file, stages_format

        return preferred_file, self.stages_format

    def normalize_stages_content(self, raw: str, stages_file: Path, stages_format: str) -> str:
        if stages_format == 'yaml':
            try:
                data = yaml.safe_load(raw) if raw.strip() else {}
            except yaml.YAMLError as e:
                raise ValueError(f"Invalid YAML in {stages_file}: {e}")
            data = self._validate_stage_rules(data, stages_file)
            return yaml.dump(data, Dumper=IndentedSafeDumper, allow_unicode=True, sort_keys=False)

        try:
            data = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in {stages_file}: {e}")
        data = self._validate_stage_rules(data, stages_file)
        return json.dumps(data, ensure_ascii=False, indent=2)

    def _validate_stage_rules(self, data: Any, stages_file: Path) -> Dict[str, Any]:
        """Keep metric boundaries global; character files only map stage labels to behavior."""
        if not isinstance(data, dict) or set(data) != {'metrics'}:
            raise ValueError(
                f"{stages_file}: stage data must contain exactly one root key: metrics"
            )
        raw_metrics = data.get('metrics')
        if not isinstance(raw_metrics, dict):
            raise ValueError(f"{stages_file}: metrics must be a mapping")

        expected_ids = {metric['id'] for metric in self.metrics}
        actual_ids = set(raw_metrics)
        if actual_ids != expected_ids:
            missing = sorted(expected_ids - actual_ids)
            unknown = sorted(actual_ids - expected_ids)
            details = []
            if missing:
                details.append(f"missing metrics: {', '.join(missing)}")
            if unknown:
                details.append(f"unknown metrics: {', '.join(unknown)}")
            raise ValueError(f"{stages_file}: " + '; '.join(details))

        normalized = {'metrics': {}}
        for metric in self.metrics:
            metric_id = metric['id']
            behaviors = raw_metrics[metric_id]
            if not isinstance(behaviors, dict):
                raise ValueError(f"{stages_file}: metrics.{metric_id} must be a mapping")
            expected_stages = list(metric['stages'])
            actual_stages = set(behaviors)
            if actual_stages != set(expected_stages):
                missing = sorted(set(expected_stages) - actual_stages)
                unknown = sorted(actual_stages - set(expected_stages))
                details = []
                if missing:
                    details.append(f"missing stages: {', '.join(missing)}")
                if unknown:
                    details.append(f"unknown stages: {', '.join(unknown)}")
                raise ValueError(
                    f"{stages_file}: metrics.{metric_id} " + '; '.join(details)
                )
            normalized['metrics'][metric_id] = {}
            for stage_name in expected_stages:
                content = behaviors[stage_name]
                if not isinstance(content, str) or not content.strip():
                    raise ValueError(
                        f"{stages_file}: metrics.{metric_id}.{stage_name} must be a non-empty string"
                    )
                normalized['metrics'][metric_id][stage_name] = content.strip()
        return normalized

    def get_entry_type_config(self, entry_type: str) -> Dict[str, Any]:
        return self.entry_types.get(entry_type, {
            'prefix': '', 'order_start': 100, 'order_step': 1, 'depth': 4,
            'position': 0, 'constant': False, 'ignore_budget': True
        })

    def merge_character_files(self, char_name: str, entry_type: str = "protagonist") -> str:
        md_file = self.character_files.get(char_name, self.characters_dir / f"{char_name}.md")
        stages_file, stages_format = self.find_stages_file(char_name)

        if not md_file.exists():
            print(f"Warning: {md_file} not found")
            return ""

        with open(md_file, 'r', encoding='utf-8') as f:
            md_content = f.read()

        stages_content = "{}"
        has_stage_rules = stages_file.exists()
        if has_stage_rules:
            with open(stages_file, 'r', encoding='utf-8') as f:
                raw = f.read()
                stages_content = self.normalize_stages_content(raw, stages_file, stages_format)

        metric_paths = "\n".join(
            f'- {metric["name"]}: /人物/{self._json_pointer_escape(char_name)}/数值/{metric["id"]}'
            for metric in self.metrics
        )
        metric_stage_contracts = []
        for metric in self.metrics:
            intervals = []
            for index in range(len(metric['ranges']) - 1):
                minimum = metric['ranges'][index]
                maximum = metric['ranges'][index + 1]
                stage_name = metric['stages'][-1 - index]
                comparison = '≤' if index == len(metric['ranges']) - 2 else '<'
                intervals.append(
                    f"{minimum} ≤ x {comparison} {maximum} => {stage_name}"
                )
            metric_stage_contracts.append(
                f'- {metric["id"]}: ' + '; '.join(intervals)
            )
        stage_guidance = (
            "先按当前数值确定唯一阶段，再从下方同名阶段读取行为与心理描述；"
            "其他阶段不代表当前状态。"
            if has_stage_rules else
            "此角色没有专属阶段行为文件；只按基础档案与数值语义表现，不自行补写阶段规则。"
        )

        return f"""<character name="{char_name}" type="{entry_type}">
{md_content}

<mvu_stage_contract>
运行时数值只从 <status_current_variables> 中的 MVU stat_data 读取，不得从聊天历史重新累计。
人物基础状态路径：/人物/{self._json_pointer_escape(char_name)}
数值路径：
{metric_paths or '- 此角色未配置可追踪数值'}
阶段边界（唯一来源为 state_model.character_metrics）：
{chr(10).join(metric_stage_contracts) or '- 此角色未配置阶段'}
{stage_guidance}

<stage_rules>
{stages_content}
</stage_rules>
</mvu_stage_contract>
</character>"""

    @staticmethod
    def _json_pointer_escape(value: str) -> str:
        return str(value).replace('~', '~0').replace('/', '~1')

    def has_character_stages(self, char_name: str) -> bool:
        return any(
            (self.character_files.get(char_name, self.characters_dir / f"{char_name}.md").parent / f"{char_name}_stages{suffix}").exists()
            for suffix in (".json", ".yaml", ".yml")
        )

    def discover_characters(self) -> List[Tuple[str, str]]:
        chars = []
        for char_name in self.character_files:
            entry_type = "protagonist" if self.has_character_stages(char_name) else "supporting"
            chars.append((char_name, entry_type))
        return sorted(chars)

    def create_character_entry(self, char_name: str, entry_id: int, entry_type: str = "protagonist") -> Dict[str, Any]:
        type_config = self.get_entry_type_config(entry_type)
        defaults = self.silly_defaults.get('entry', {})

        content = self.merge_character_files(char_name, entry_type)
        keys = [char_name]
        md_path = self.character_files.get(char_name, self.characters_dir / f"{char_name}.md")
        if md_path.exists():
            first_line = md_path.read_text(encoding='utf-8').split('\n', 1)[0]
            alias_match = re.search(r'[（(]([^）)]+)[）)]', first_line)
            if alias_match:
                aliases = [a.strip() for a in re.split(r'[，,、]', alias_match.group(1)) if a.strip()]
                for alias in aliases:
                    if alias not in keys:
                        keys.append(alias)
        order = type_config.get('order_start', 100) + entry_id * type_config.get('order_step', 1)

        return {
            "uid": entry_id,
            "key": keys,
            "keysecondary": [],
            "comment": f"{type_config.get('prefix', '')}{char_name}",
            "content": content,
            "constant": type_config.get('constant', False),
            "selective": False,
            "selectiveLogic": defaults.get('selective_logic', 0),
            "addMemo": defaults.get('add_memo', True),
            "order": order,
            "position": type_config.get('position', 0),
            "disable": False,
            "probability": defaults.get('probability', 100),
            "useProbability": defaults.get('use_probability', True),
            "depth": type_config.get('depth', 4),
            "delay": defaults.get('delay', 0),
            "cooldown": defaults.get('cooldown', 0),
            "sticky": defaults.get('sticky', 0),
            "scanDepth": defaults.get('scan_depth', 2),
            "vectorized": defaults.get('vectorized', False),
            "ignoreBudget": type_config.get('ignore_budget', True),
            "excludeRecursion": defaults.get('exclude_recursion', False),
            "preventRecursion": defaults.get('prevent_recursion', False)
        }

    def _collect_dedicated_source_files(self) -> set:
        """Exclude files with another owner from the generic setting scanner."""
        dedicated = set()
        for et_config in self.entry_types.values():
            sf = et_config.get('source_file')
            if sf:
                dedicated.update(self.content.files([sf]))
        return dedicated

    def extract_setting_entries(self, start_id: int) -> List[Dict[str, Any]]:
        entries = []
        type_config = self.get_entry_type_config('setting')
        defaults = self.silly_defaults.get('entry', {})

        raw_source_files = type_config.get('source_files', [])
        if not isinstance(raw_source_files, list):
            raise ValueError("entry_types.setting.source_files must be a list of glob patterns")
        source_files = list(raw_source_files)
        active_layer = str(type_config.get('active_layer', '') or '').strip()
        layers = type_config.get('layers') or {}
        if not isinstance(layers, dict):
            raise ValueError("entry_types.setting.layers must be a mapping")
        if active_layer:
            if active_layer not in layers:
                raise ValueError(
                    f"entry_types.setting.active_layer references unknown layer: {active_layer}"
                )
            layer_patterns = layers[active_layer]
            if not isinstance(layer_patterns, list):
                raise ValueError(
                    f"entry_types.setting.layers.{active_layer} must be a list of glob patterns"
                )
            source_files.extend(layer_patterns)
        dedicated_files = self._collect_dedicated_source_files()
        seen_setting_files = set()

        for settings_file in self.content.files(source_files):
            resolved_file = settings_file.resolve()
            if resolved_file in dedicated_files or resolved_file in seen_setting_files:
                continue
            seen_setting_files.add(resolved_file)
            with open(settings_file, 'r', encoding='utf-8') as f:
                content = f.read()

            header_pattern = r'(★?)【([^】]+)】(?:[（(]([^）)]+)[）)])?'
            headers = list(re.finditer(header_pattern, content))

            for idx, match in enumerate(headers):
                is_constant = bool(match.group(1))
                name = match.group(2).strip()
                keywords_text = match.group(3)

                if not name:
                    continue

                keys = [k.strip() for k in re.split(r'[，,、]', keywords_text) if k.strip()] if keywords_text else [name]

                start_pos = match.end()
                end_pos = headers[idx + 1].start() if idx + 1 < len(headers) else len(content)
                setting_content = content[start_pos:end_pos].strip()

                if not setting_content:
                    continue

                order = type_config.get('order_start', 50) + len(entries) * type_config.get('order_step', 1)

                entries.append({
                    "uid": start_id + len(entries),
                    "key": keys,
                    "keysecondary": [],
                    "comment": f"{type_config.get('prefix', '')}{name}",
                    "content": f"### {name}\n\n{setting_content}",
                    "constant": is_constant or type_config.get('constant', False),
                    "selective": False,
                    "selectiveLogic": defaults.get('selective_logic', 0),
                    "addMemo": defaults.get('add_memo', True),
                    "order": order,
                    "position": type_config.get('position', 0),
                    "disable": False,
                    "probability": defaults.get('probability', 100),
                    "useProbability": defaults.get('use_probability', True),
                    "depth": type_config.get('depth', 2),
                    "delay": defaults.get('delay', 0),
                    "cooldown": defaults.get('cooldown', 0),
                    "sticky": defaults.get('sticky', 0),
                    "scanDepth": defaults.get('scan_depth', 2),
                    "vectorized": defaults.get('vectorized', False),
                    "ignoreBudget": type_config.get('ignore_budget', True),
                    "excludeRecursion": defaults.get('exclude_recursion', False),
                    "preventRecursion": defaults.get('prevent_recursion', False)
                })
        return entries

    def extract_relationship_entries(self, start_id: int) -> List[Dict[str, Any]]:
        entries = []
        type_config = self.get_entry_type_config('relationship')
        defaults = self.silly_defaults.get('entry', {})

        source_file = type_config.get('source_file')
        if not source_file:
            return []
        entries = []
        for relationship_file in self.content.files([source_file]):
            entries.extend(self._parse_relationship_file(relationship_file, start_id + len(entries)))
        return entries

    def _parse_relationship_file(self, relationship_file, start_id):
        entries = []
        type_config = self.get_entry_type_config('relationship')
        defaults = self.silly_defaults.get('entry', {})

        with open(relationship_file, 'r', encoding='utf-8') as f:
            content = f.read()

        pattern = r'【([^】]+)】(?:[（(]([^）)]+)[）)])?'
        matches = list(re.finditer(pattern, content))

        for idx, match in enumerate(matches):
            name = match.group(1).strip()
            keywords_text = match.group(2)

            start_pos = match.end()
            end_pos = matches[idx + 1].start() if idx + 1 < len(matches) else len(content)
            block_content = content[start_pos:end_pos].strip()

            keys = [k.strip() for k in re.split(r'[，,、]', keywords_text) if k.strip()] if keywords_text else [name]
            primary_keys = keys[:1]
            optional_filters = keys[1:]

            order = type_config.get('order_start', 300) + len(entries) * type_config.get('order_step', 1)

            entries.append({
                "uid": start_id + len(entries),
                "key": primary_keys,
                "keysecondary": optional_filters,
                "comment": f"{type_config.get('prefix', '关系_')}{name}",
                "content": f"### {name}\n\n{block_content}",
                "constant": type_config.get('constant', False),
                "selective": bool(optional_filters),
                "selectiveLogic": defaults.get('selective_logic', 0),
                "addMemo": defaults.get('add_memo', True),
                "order": order,
                "position": type_config.get('position', 0),
                "disable": False,
                "probability": defaults.get('probability', 100),
                "useProbability": defaults.get('use_probability', True),
                "depth": type_config.get('depth', 6),
                "delay": defaults.get('delay', 0),
                "cooldown": defaults.get('cooldown', 0),
                "sticky": defaults.get('sticky', 0),
                "scanDepth": defaults.get('scan_depth', 2),
                "vectorized": defaults.get('vectorized', False),
                "ignoreBudget": type_config.get('ignore_budget', True),
                "excludeRecursion": defaults.get('exclude_recursion', False),
                "preventRecursion": defaults.get('prevent_recursion', False)
            })

        return entries

    def extract_style_entries(self, start_id: int) -> List[Dict[str, Any]]:
        config = self.entry_types.get('style') or {}
        enabled = config.get('enabled', False)
        if not isinstance(enabled, bool):
            raise ValueError('entry_types.style.enabled must be a boolean')
        source = config.get('source_file')
        files = list(self.content.files([source])) if source else []
        samples = [path.read_text(encoding='utf-8') for path in files]
        samples = [sample for sample in samples if sample.strip()]
        if not samples:
            if enabled:
                raise ValueError('Style is enabled but no nonempty style sample was found')
            return []
        entry = self._make_system_entry(
            start_id, '[style]风格样本', '\n\n'.join(samples), 40, disabled=not enabled,
        )
        # A disabled constant entry can be enabled directly in the lorebook UI.
        entry['constant'] = True
        entry['ignoreBudget'] = False
        return [entry]

    def _metric_by_id(self, key: str) -> Dict[str, Any]:
        normalized = str(key).strip()
        for metric in self.metrics:
            if normalized == metric['id']:
                return metric
        raise ValueError(
            f"Unknown character metric id {normalized!r}; use an id declared in config.yaml"
        )

    def _normalize_metrics(self, raw_value: Any, context: str, entity_name=None) -> Dict[str, Any]:
        if raw_value is None:
            raw_value = {}
        if not isinstance(raw_value, dict):
            raise ValueError(f"{context} must be a mapping")
        metrics = {
            metric['id']: metric.get('initial', metric['ranges'][0])
            for metric in self.metrics if entity_name not in metric.get('exclude_entities', [])
        }
        for raw_key, raw_number in raw_value.items():
            metric = self._metric_by_id(raw_key)
            if entity_name in metric.get("exclude_entities", []):
                raise ValueError(f"{context}.{raw_key} does not apply to {entity_name}")
            try:
                value = float(raw_number)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{context}.{raw_key} must be numeric") from exc
            minimum, maximum = metric['ranges'][0], metric['ranges'][-1]
            value = min(maximum, max(minimum, value))
            numeric_value = float(value)
            metrics[metric['id']] = int(numeric_value) if numeric_value.is_integer() else numeric_value
        return metrics

    def _normalize_field_value(self, field: Dict[str, Any], value: Any, context: str) -> Any:
        field_type = field['type']
        if value is None:
            value = deepcopy(field.get('default'))
        if field_type == 'object':
            return self._normalize_record(value, field, context)
        if field_type in ('array', 'record'):
            value = value if value is not None else ([] if field_type == 'array' else {})
            if not isinstance(value, list if field_type == 'array' else dict):
                raise ValueError(f'{context} must be {field_type}')
            if len(value) > field.get('max_items', float('inf')):
                raise ValueError(f'{context} exceeds max_items')
            if field_type == 'array':
                return [self._normalize_field_value(field['items'], item, f'{context}[{i}]') for i, item in enumerate(value)]
            return {key: self._normalize_field_value(field['items'], item, f'{context}.{key}') for key, item in value.items()}
        if field_type == 'metrics':
            return self._normalize_metrics(value, context)
        if field_type == 'string':
            return str(value)
        if field_type == 'boolean':
            if not isinstance(value, bool):
                raise ValueError(f"{context} must be true or false")
            return value
        if field_type == 'string_list':
            if not isinstance(value, list):
                raise ValueError(f"{context} must be a list")
            return [str(item) for item in value]
        if field_type == 'enum':
            if value not in field['values']:
                raise ValueError(f"{context} must be one of {field['values']}")
            return value
        if field_type == 'number':
            if isinstance(value, bool):
                raise ValueError(f"{context} must be numeric")
            try:
                number = float(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{context} must be numeric") from exc
            if not math.isfinite(number):
                raise ValueError(f'{context} must be finite')
            if 'min' in field:
                number = max(float(field['min']), number)
            if 'max' in field:
                number = min(float(field['max']), number)
            return int(number) if number.is_integer() else number
        raise ValueError(f"Unsupported field type at {context}: {field_type}")

    def _normalize_record(
        self,
        raw_record: Any,
        collection: Dict[str, Any],
        context: str,
        entity_name=None,
    ) -> Dict[str, Any]:
        if raw_record is None:
            raw_record = {}
        if not isinstance(raw_record, dict):
            raise ValueError(f"{context} must be a mapping")
        fields = collection['fields']
        unknown = set(raw_record) - set(fields)
        if unknown:
            raise ValueError(f"{context} contains unknown fields: {', '.join(map(str, unknown))}")
        return {
            field_name: self._normalize_metrics(raw_record.get(field_name, {}), f"{context}.{field_name}", entity_name)
            if field["type"] == "metrics" else self._normalize_field_value(
                field,
                raw_record.get(field_name, deepcopy(field.get('default'))),
                f"{context}.{field_name}",
            )
            for field_name, field in fields.items()
        }

    def _build_initial_state(self, metadata: Dict[str, Any] = None, file_path: Path = None) -> Dict[str, Any]:
        metadata = metadata or {}
        raw_state = metadata.get('state') or {}
        context_name = file_path.name if file_path else '[initvar]'
        if not isinstance(raw_state, dict):
            raise ValueError(f"Scenario {context_name}: state must be a mapping")

        known_paths = {collection['path'] for collection in self.collections.values()}
        unknown_paths = set(raw_state) - known_paths
        if unknown_paths:
            raise ValueError(
                f"Scenario {context_name}: unknown state collections: "
                + ", ".join(map(str, unknown_paths))
            )

        state = {}
        for collection_id, collection in self.collections.items():
            path = collection['path']
            raw_collection = raw_state.get(path, {})
            context = f"Scenario {context_name}.state.{path}"
            if collection['kind'] == 'singleton':
                state[path] = self._normalize_record(raw_collection, collection, context)
                continue
            if not isinstance(raw_collection, dict):
                raise ValueError(f"{context} must be a mapping of entity names")
            state[path] = {
                str(entity_name): self._normalize_record(
                    entity_value,
                    collection,
                    f"{context}.{entity_name}",
                    entity_name=str(entity_name) if path == "人物" else None,
                )
                for entity_name, entity_value in raw_collection.items()
            }

        world = state.get('世界', {})
        metadata_defaults = {
            '场景': metadata.get('name') or (file_path.stem if file_path else '未初始化'),
            '场景摘要': metadata.get('description') or '',
            '时间': metadata.get('time'),
            '当前地点': metadata.get('location'),
            '天气': metadata.get('weather'),
        }
        explicitly_set_world = raw_state.get('世界') or {}
        for field_name, fallback in metadata_defaults.items():
            if field_name in world and field_name not in explicitly_set_world and fallback is not None:
                world[field_name] = fallback
        if '已初始化' in world:
            world['已初始化'] = file_path is not None
        return state

    def _build_scenario_mvu_init(self, metadata: Dict[str, Any], file_path: Path) -> str:
        initial_state = self._build_initial_state(metadata, file_path)
        operations = [
            {
                "op": "replace",
                "path": f"/{self._json_pointer_escape(path)}",
                "value": value,
            }
            for path, value in initial_state.items()
        ]
        patch = json.dumps(operations, ensure_ascii=False, indent=2)
        return (
            "\n<UpdateVariable>\n"
            "<Analysis>将所选开局写入世界、人物、物品、地点与事件的完整快照。</Analysis>\n"
            f"<JSONPatch>\n{patch}\n</JSONPatch>\n"
            "</UpdateVariable>"
        )

    def parse_scenario_file(self, file_path: Path) -> dict:
        """Parse scenario frontmatter and append an MVU initialization patch."""
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        parts = re.split(r'^---\s*$', content, maxsplit=2, flags=re.MULTILINE)
        if len(parts) < 3:
            return {
                'body': content.strip(),
                'source_body': content.strip(),
                'file': file_path.name,
                'metadata': {},
            }

        frontmatter = parts[1]
        body = parts[2].strip()
        try:
            metadata = yaml.safe_load(frontmatter) or {}
        except yaml.YAMLError as exc:
            raise ValueError(f"Invalid scenario frontmatter in {file_path}: {exc}") from exc
        if not isinstance(metadata, dict):
            raise ValueError(f"Scenario {file_path.name}: frontmatter must be a mapping")
        if 'pov' in metadata:
            raise ValueError(
                f"Scenario {file_path.name}: pov frontmatter has been removed; "
                "use the fixed viewpoint in narrator.persona"
            )

        body += self._build_scenario_mvu_init(metadata, file_path)
        return {
            'body': body,
            'source_body': parts[2].strip(),
            'file': file_path.name,
            'metadata': metadata,
        }

    def load_scenarios(self) -> List[dict]:
        scenarios = []
        pattern = str(Path(self.config.get('paths', {}).get('scenarios_dir', 'literature/scenarios')) / '*.md')
        for file_path in self.content.files([pattern]):
            result = self.parse_scenario_file(file_path)
            if result['body']:
                scenarios.append(result)

        return scenarios

    def _build_state_schema_summary(self) -> str:
        lines = []
        for collection in self.collections.values():
            kind = "单例" if collection['kind'] == 'singleton' else "按名称索引的集合"
            field_parts = []
            for field_name, field in collection['fields'].items():
                if field['type'] == 'metrics':
                    field_parts.append(f"{field_name}(人物数值对象，默认 {{}})")
                else:
                    default = json.dumps(field.get('default'), ensure_ascii=False)
                    allowed = (
                        f"，可选 {json.dumps(field['values'], ensure_ascii=False)}"
                        if field['type'] == 'enum' else ""
                    )
                    field_parts.append(
                        f"{field_name}({field['type']}，默认 {default}{allowed})"
                    )
            lines.append(
                f"  - /{collection['path']}: {kind}；字段 " + "、".join(field_parts)
            )
        return '\n'.join(lines)

    def _build_opening_rules(self) -> str:
        return f"""---
开局创建规则:
  - 开局资料由创建开局表单校验并写入当前会话，预设开场由生成器提供快照；两者都在剧情生成前完成初始化。
  - 读取 <status_current_variables> 中的 /世界/已初始化。false 时请用户在面板中完成建角，不推进剧情。
  - true 时依据已有主角与场景推进正文。开局已保存的身份、地点和资源直接从当前变量读取。
  - 首次剧情与后续剧情均先完成正文前检，再展开故事。
  - 模型输出的是待校验补丁文本，MVU 脚本负责解析、校验和保存。初始化与存储成功由程序确认，正文只叙述世界内发生的事。

"""

    def _build_preflight_rules(self) -> str:
        max_words = int(self.mvu_config.get('preflight_max_words', 100))
        check_lines = '\n'.join(
            f"    {index}. {check}"
            for index, check in enumerate(self.preflight_checks, 1)
        )
        return f"""---
正文前一致性检查:
  - 生成故事正文前，先读取 <status_current_variables>，用 <StateCheck> 标签包裹不超过 {max_words} 字的裁决结果，再写正文。
  - 依次应用下列审查职责，但只报告与本轮有关的约束和违规，不逐项展示思维过程：
{check_lines}
  - 变量与较早的聊天叙述冲突时，以变量为准；不得从历史重新累计。
  - StateCheck 使用紧凑 JSON，字段为 scene、constraints、violations、verdict、focus。
  - violations 只列实际问题；每项包含 type、issue、handling。没有问题时写空数组。
  - verdict 只能是 proceed、constrain、reframe、reject；reject 仅用于无法转化为世界内尝试或触犯内容边界的请求。
  - 检查块只写可观察的裁决结果，不写隐藏思维链，不修改变量，不预先宣布尚未发生的剧情结果。
  - 如 /世界/已初始化 为 false，检查块改为概括用户的开局条件与缺失项。
"""

    def _build_mvu_update_rules(self) -> str:
        max_characters = int(self.mvu_config.get('max_characters_per_turn', 3))
        max_entities = int(self.mvu_config.get('max_entities_per_turn', 6))
        max_active_events = int(self.mvu_config.get('max_active_events', 3))
        metric_lines = []
        for metric in self.metrics:
            change = metric.get('change', {})
            minor = change.get('minor', [1, 2])
            major = change.get('major', [3, 5])
            metric_lines.append(
                f"  - {metric['id']}（{metric['name']}）: "
                f"范围 {metric['ranges'][0]}~{metric['ranges'][-1]}；"
                f"初始 {metric.get('initial', metric['ranges'][0])}；"
                f"轻微 ±{minor[0]}~{minor[-1]}，重大 ±{major[0]}~{major[-1]}；"
                f"{metric.get('description', '按剧情中的明确行为变化')}；不适用实体键：{metric.get('exclude_entities', [])}"
            )

        return f"""---
正文后变量更新规则:
  人物数值:
{chr(10).join(metric_lines) or '  - 未配置人物数值'}

  唯一事实源:
  - 当前场景地点只写 /世界/当前地点。
  - 人物位置只写 /人物/<名称>/所在地点；地点对象不反向保存人物列表。
  - 物品归属以 /物品/<名称>/持有者 为准；持有者非空时 /所在地点 应为空。
  - 地点只保存地点自身状态；事件只保存阶段、参与者、摘要和结果。

  事件调度:
  - 同时最多维持 {max_active_events} 个“进行中”事件；这是上限，不是必须填满的配额。
  - 只有时间流逝、参与者行动或明确因果使事件前进时才更新；不得为刷新状态栏而强制推进。
  - 若 Schema 定义了“阶段”枚举，按枚举声明顺序逐级推进，禁止无依据跳级。
  - 事件收束时先更新状态与结果，并把永久后果落实到世界、人物、物品或地点；配置 archives 时由脚本在后续时间推进中归档并移除终结事件；未配置归档时，在保存长期后果后移除事件。

  更新原则:
  - 根据已经完成的本轮正文，提取已发生的持久变化。
  - <StateCheck> 约束的是“允许如何叙述”；<UpdateVariable> 只记录正文最终确认的结果。用户请求但正文未发生、被 constrain/reframe 改写或失败的预期结果不得直接写入变量。
  - 每次剧情回复对 /世界/回合 使用 delta +1；纯 OOC/配置说明不增加回合。
  - 已初始化后的每轮最多更新 {max_characters} 个人物、总计 {max_entities} 个实体；只更新本轮直接变化的实体。
  - 把更新视为最小事实提交批次：先筛选会影响后续叙事的持久变化，再选择最少操作；不得把描写性细节、计划、推测或未完成动作写入状态。
  - replace 用于已存在字段的新值；delta 用于可证明的数值增减；insert 用于新实体且一次写入完整对象；remove 用于已消耗或按保留策略退出的实体；move 只用于真实改名或键迁移。
  - 同一事实涉及多个权威字段时必须放在同一提交批次，例如物品有持有者时清空其所在地点，人物跨入或离开当前场景时同步其所在地点与在场状态。
  - 已消耗物品和离场后不再影响后续的一次性人物应 remove；事件按上述归档规则处理；有持续关系、目标或后果的人物不得仅因暂时离场而删除。
  - 数值变化优先使用 delta；无变化时不输出 replace 或 delta 0。
  - 人物普通互动使用轻微变化；不可逆选择、关系转折、重大创伤或成就才使用重大变化。
  - 只被提及、背景中存在、重复已有态度或模型自己推测的状态不更新。
  - <Analysis> 只列最终变化路径及正文证据，不复述审查过程；变量路径必须来自已定义 Schema，禁止临时创建新字段。
"""

    def _build_mvu_output_format(self) -> str:
        analysis_words = int(self.mvu_config.get('update_analysis_max_words', 120))
        checklist = '\n'.join(
            f"    {i}. {collection['path']}: 检查该集合各字段的更新条件；记录已确认变化，未变化写无变化。"
            for i, collection in enumerate(self.collections.values(), 1)
        )
        return f"""---
MVU 每轮输出格式:
  rule:
  - 更新分析与实际更新命令一并放在回复末尾。
  - 分析最多 {analysis_words} 字，按下列集合逐项给出简短变化结论；未变化也须说明，不省略集合，不展开思维过程。
  - 更新命令为合法 JSON 数组，按字段更新规则选择 replace、delta、insert、remove、move；无变化的字段不生成操作。
  - path 必须以 / 开头，使用当前变量中的实体键和 Schema 字段；新实体一次 insert 完整对象。
  - replace、delta、insert 使用 op/path/value；remove 使用 op/path；move 使用 op/from/to。
  - 禁止更新以下划线开头的只读字段；数值遵循已定义边界。
  - 开局由脚本保存，首次剧情与后续剧情都从已有快照计算增量，不重新初始化五集合。
  - 剧情推进时回合 delta +1；没有剧情推进和状态变化时输出空数组。
  format: |-
    <UpdateVariable>
    <Analysis>
    0. 开局：确认已保存快照，不重复初始化。
{checklist}
    </Analysis>
    <JSONPatch>
    []
    </JSONPatch>
    </UpdateVariable>
  示例说明: 上面的空数组是无变化示例；有变化时填入实际操作，例如推进一轮使用 {{"op":"delta","path":"/世界/回合","value":1}}。
"""

    def _build_mvu_init_data(self) -> str:
        initial = self._build_initial_state()
        return yaml.dump(
            initial,
            Dumper=IndentedSafeDumper,
            allow_unicode=True,
            sort_keys=False,
        ).strip()

    def _make_system_entry(
        self,
        uid: int,
        comment: str,
        content: str,
        order: int,
        disabled: bool = False,
    ) -> Dict[str, Any]:
        defaults = self.silly_defaults.get('entry', {})
        return {
            "uid": uid,
            "key": [],
            "keysecondary": [],
            "comment": comment,
            "content": content,
            "constant": not disabled,
            "selective": False,
            "selectiveLogic": defaults.get('selective_logic', 0),
            "addMemo": defaults.get('add_memo', True),
            "order": order,
            "position": 0 if disabled else 4,
            "role": 0,
            "disable": disabled,
            "probability": 100,
            "useProbability": True,
            "depth": 0,
            "delay": 0,
            "cooldown": 0,
            "sticky": 0,
            "scanDepth": defaults.get('scan_depth', 2),
            "vectorized": False,
            "ignoreBudget": True,
            "excludeRecursion": True,
            "preventRecursion": False,
        }

    def generate_mvu_entries(self, start_id: int) -> List[Dict[str, Any]]:
        plot = "\n\n".join([self._build_opening_rules(), self._build_preflight_rules()])
        update = "\n\n".join([
            '变量结构：\n' + self._build_state_schema_summary(),
            self._build_mvu_update_rules(),
            '变量更新条件：\n' + '\n'.join(f"{rule['path']}:\n  check:\n    - {rule['when']}\n    - {rule['update']}" for rule in self.mvu_config.get('update_rules', [])),
            '本作可执行状态规则：\n' + json.dumps(self.config.get('runtime_rules') or {}, ensure_ascii=False),
        ])
        return [
            self._make_system_entry(start_id, "合理性审查与开局", plot, 900),
            self._make_system_entry(start_id + 1, "[mvu_update]变量更新", update, 902),
            self._make_system_entry(
                start_id + 2, "[mvu_current]变量列表",
                "---\n<status_current_variables>\n"
                "{{format_message_variable::stat_data}}\n"
                "</status_current_variables>", 901,
            ),
            self._make_system_entry(start_id + 3, "[mvu_update]变量输出格式", self._build_mvu_output_format(), 903),
            self._make_system_entry(start_id + 4, "[initvar]", self._build_mvu_init_data(), 904, disabled=True),
        ]

    def _build_zod_script(self) -> str:
        metric_fields = []
        for metric in self.metrics:
            minimum, maximum = metric['ranges'][0], metric['ranges'][-1]
            initial = metric.get('initial', minimum)
            key = json.dumps(metric['id'], ensure_ascii=False)
            metric_fields.append(
                f"  {key}: z.coerce.number().catch({json.dumps(initial)})."
                f"transform(value => Math.min({json.dumps(maximum)}, Math.max({json.dumps(minimum)}, "
                f"Number.isFinite(value) ? value : {json.dumps(initial)}))).prefault({json.dumps(initial)})"
            )
            if metric.get("exclude_entities"):
                metric_fields[-1] = metric_fields[-1].rsplit(".prefault(", 1)[0] + ".optional()"

        def field_expression(field: Dict[str, Any]) -> str:
            field_type = field['type']
            default = json.dumps(field.get('default'), ensure_ascii=False)
            if field_type == 'object':
                children = ', '.join(f'{json.dumps(k, ensure_ascii=False)}: {field_expression(v)}' for k, v in field['fields'].items())
                return f'z.object({{{children}}}).strict().prefault({default if default != "null" else "{}"})'
            if field_type in ('array', 'record'):
                child = field_expression(field['items'])
                expr = f'z.array({child})' if field_type == 'array' else f'z.record(z.string(), {child})'
                if 'max_items' in field:
                    expr += f'.refine(value => Object.keys(value).length <= {field["max_items"]}, "max_items exceeded")'
                fallback = '[]' if field_type == 'array' else '{}'
                return expr + f'.prefault({default if default != "null" else fallback})'
            if field_type == 'metrics':
                return "CharacterMetrics.prefault({})"
            if field_type == 'string':
                return f"z.string().catch({default}).prefault({default})"
            if field_type == 'boolean':
                return f"z.boolean().catch({default}).prefault({default})"
            if field_type == 'string_list':
                return f"z.array(z.string()).catch({default}).prefault({default})"
            if field_type == 'enum':
                values = json.dumps(field['values'], ensure_ascii=False)
                return f"z.enum({values}).catch({default}).prefault({default})"
            if field_type == 'number':
                expression = f"z.coerce.number().catch({default})"
                if 'min' in field:
                    expression += f".transform(value => Math.max({json.dumps(field['min'])}, value))"
                if 'max' in field:
                    expression += f".transform(value => Math.min({json.dumps(field['max'])}, value))"
                return expression + f".prefault({default})"
            raise ValueError(f"Unsupported field type: {field_type}")

        schema_blocks = []
        root_fields = []
        for collection_id, collection in self.collections.items():
            schema_name = f"Collection_{collection_id}"
            fields = [
                f"  {json.dumps(field_name, ensure_ascii=False)}: {field_expression(field)}"
                for field_name, field in collection['fields'].items()
            ]
            joined_fields = ',\n'.join(fields)
            schema_blocks.append(
                f"const {schema_name} = z.object({{\n{joined_fields}\n}}).strict();"
            )
            path = json.dumps(collection['path'], ensure_ascii=False)
            if collection['kind'] == 'singleton':
                root_fields.append(f"  {path}: {schema_name}.prefault({{}})")
            else:
                expression = f"z.record(z.string(), {schema_name}).prefault({{}})"
                if collection['path'] == '人物' and any(m.get('exclude_entities') for m in self.metrics):
                    scopes = json.dumps([{ 'id': m['id'], 'exclude_entities': m.get('exclude_entities', [])} for m in self.metrics], ensure_ascii=False)
                    expression += f".superRefine((records, ctx) => {{ for (const [name, record] of Object.entries(records)) for (const metric of {scopes}) {{ const has = Object.prototype.hasOwnProperty.call(record.数值, metric.id); if (has === metric.exclude_entities.includes(name)) ctx.addIssue({{code:'custom', path:[name,'数值',metric.id], message:'metric does not match entity scope'}}); }} }})"
                root_fields.append(f"  {path}: {expression}")

        joined_metric_fields = ',\n'.join(metric_fields)
        joined_schema_blocks = '\n'.join(schema_blocks)
        joined_root_fields = ',\n'.join(root_fields)

        schema_url = self.mvu_config.get(
            'schema_helper_url',
            'https://testingcf.jsdelivr.net/gh/StageDog/tavern_resource/dist/util/mvu_zod.js',
        )
        return f"""import {{ registerMvuSchema }} from {json.dumps(schema_url)};

const CharacterMetrics = z.object({{
{joined_metric_fields}
}}).strict();

{joined_schema_blocks}

export const Schema = z.object({{
{joined_root_fields}
}}).strict().prefault({{}});

$(() => registerMvuSchema(Schema));
"""

    def _stable_id(self, name: str) -> str:
        project_name = self.config.get('project', {}).get('name', '作品')
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"sillytavern-worldbook-template:{project_name}:{name}"))

    def _script_record(self, name: str, content: str, buttons: List[Dict[str, Any]] = None) -> Dict[str, Any]:
        return {
            "type": "script",
            "enabled": True,
            "name": name,
            "id": self._stable_id(f"script:{name}"),
            "content": content,
            "info": "",
            "button": {"enabled": True, "buttons": buttons or []},
            "data": {},
            "export_with": {"data": True, "button": True},
        }

    def _build_panel_script(self) -> str:
        template_path = Path(__file__).resolve().parents[1] / 'templates/mvu/floating_panel.js'
        if not template_path.exists():
            raise FileNotFoundError(f"MVU panel template not found: {template_path}")
        source = template_path.read_text(encoding='utf-8')
        project_name = self.config.get('project', {}).get('name', '作品')
        panel = self.mvu_config.get('panel') or {}
        config = {
            "title": panel.get('title') or f"{project_name} · 世界状态",
            "width": panel.get('width', 840),
            "rules": self.config.get('runtime_rules') or {},
            "opening": {
                **(self.config.get('opening') or {}),
                'state': self._build_initial_state({'state': (self.config.get('opening') or {}).get('state', {})}),
            } if self.config.get('opening') else {},
            "collections": [
                {
                    "id": collection_id,
                    "path": collection['path'],
                    "label": collection.get('label') or collection['path'],
                    "kind": collection['kind'],
                    "fields": collection['fields'],
                }
                for collection_id, collection in self.collections.items()
            ],
            "metrics": [
                {
                    "id": metric['id'],
                    "name": metric['name'],
                    "initial": metric.get('initial', metric['ranges'][0]),
                    "exclude_entities": metric.get("exclude_entities", []),
                    "ranges": metric['ranges'],
                    "stages": metric['stages'],
                }
                for metric in self.metrics
            ],
        }
        source = source.replace('__MVU_RULES_SOURCE__', (template_path.parent / 'rules.js').read_text(encoding='utf-8'))
        return source.replace(
            '__MVU_PANEL_CONFIG__',
            json.dumps(config, ensure_ascii=False),
            1,
        )

    def build_tavern_helper_extension(self) -> Dict[str, Any]:
        runtime_url = self.mvu_config.get(
            'runtime_url',
            'https://testingcf.jsdelivr.net/gh/NLKASHEI/MVU-offline@v1.0.2/mvu_bundle_full.js',
        )
        scripts = [
            self._script_record(
                "MVU",
                f"import {json.dumps(runtime_url)};",
                buttons=[
                    {"name": "重新处理变量", "visible": True},
                    {"name": "重新读取初始变量", "visible": True},
                    {"name": "快照楼层", "visible": False},
                    {"name": "重演楼层", "visible": False},
                    {"name": "重试额外模型解析", "visible": False},
                    {"name": "清除旧楼层变量", "visible": False},
                ],
            ),
            self._script_record("MVU Schema", self._build_zod_script()),
        ]
        if self.config.get('runtime_rules') or self.config.get('opening'):
            scripts.append(self._script_record("MVU 状态规则", self._build_rules_script()))
        if (self.mvu_config.get('panel') or {}).get('enabled', True):
            scripts.append(self._script_record("MVU 悬浮状态面板", self._build_panel_script()))
        for path in self.content.files((self.config.get('imports') or {}).get('scripts', [])):
            script = json.loads(path.read_text(encoding='utf-8'))
            if script.get('type') != 'script' or not isinstance(script.get('content'), str) or not isinstance(script.get('id'), str) or not script['id']:
                raise ValueError(f'Expected Tavern Helper script JSON: {path}')
            if any(item.get('id') == script.get('id') for item in scripts):
                raise ValueError(f'Duplicate script id: {path}')
            scripts.append(script)
        return {"scripts": scripts, "variables": {}}

    def _regex_record(
        self,
        name: str,
        find_regex: str,
        markdown_only: bool,
        prompt_only: bool,
    ) -> Dict[str, Any]:
        return {
            "id": self._stable_id(f"regex:{name}"),
            "scriptName": name,
            "disabled": False,
            "runOnEdit": True,
            "findRegex": find_regex,
            "trimStrings": [],
            "replaceString": "",
            "placement": [2],
            "substituteRegex": 0,
            "minDepth": None,
            "maxDepth": None,
            "markdownOnly": markdown_only,
            "promptOnly": prompt_only,
        }

    def build_mvu_regexes(self) -> List[Dict[str, Any]]:
        records = [
            self._regex_record(
                "[MVU]隐藏生成中的内部块",
                r"/<(StateCheck|UpdateVariable)>(?![\s\S]*<\/\1>)[\s\S]*$/gi",
                markdown_only=True,
                prompt_only=False,
            ),
            self._regex_record(
                "[MVU]隐藏完整内部块",
                r"/<StateCheck>[\s\S]*?<\/StateCheck>/gi",
                markdown_only=True,
                prompt_only=False,
            ),
            self._regex_record(
                "[MVU]不发送历史内部块",
                r"/<(StateCheck|UpdateVariable)>(?:[\s\S]*?<\/\1>|[\s\S]*$)/gi",
                markdown_only=False,
                prompt_only=True,
            ),
        ]
        display = self._regex_record("[MVU]楼层更新记录", r"/<UpdateVariable>[\s\S]*?<\/UpdateVariable>/gi", True, False)
        display['replaceString'] = '<details class="mvu-update-record"><summary>变量更新记录（保存结果见状态面板）</summary><div class="mvu-update-details">等待面板读取更新内容</div></details>'
        records.append(display)
        return records

    def generate_narrator_card(self, lorebook=None) -> Dict[str, Any]:
        project = self.config.get('project', {})
        narrator = self.config.get('narrator', {})
        defaults = self.silly_defaults.get('narrator', {})

        scenarios = self.load_scenarios()
        first_mes = scenarios[0]['body'] if scenarios else ('请通过悬浮状态栏的“创建开局”填写资料并保存，再发送行动开始故事。' if self.config.get('opening') else '本作品尚无预设开局或建角表单，请先配置开局后生成。')
        alternate_greetings = [s['body'] for s in scenarios[1:]] if len(scenarios) > 1 else []

        metric_names = [metric['name'] for metric in self.metrics]

        data = {
            "name": narrator.get('name', '叙事者'),
            "description": narrator.get('description', ''),
            "personality": narrator.get('personality', ''),
            "scenario": "",
            "first_mes": first_mes,
            "alternate_greetings": alternate_greetings,
            "mes_example": "",
            "creator_notes": narrator.get(
                'creator_notes',
                "MVU 生命周期：开局创建 → 正文前检查 → 正文后更新 → 状态栏实时订阅；"
                f"人物数值：{', '.join(metric_names)}。",
            ),
            "system_prompt": narrator.get('persona', ''),
            "post_history_instructions": "",
            "tags": project.get('tags', []),
            "creator": narrator.get('creator', ''),
            "character_version": project.get('version', '1.0.0'),
            "extensions": {
                "created_at": datetime.now().isoformat(),
                "world": f"{project.get('name', '作品')}世界书",
                "regex_scripts": self.build_mvu_regexes(),
                "tavern_helper": self.build_tavern_helper_extension(),
            }
        }

        if lorebook is not None:
            data['character_book'] = {'name': f"{project.get('name', '作品')}世界书", 'entries': [
                {**entry, 'id': entry['uid'], 'keys': entry.get('key', []),
                 'secondary_keys': entry.get('keysecondary', []), 'enabled': not entry.get('disable', False),
                 'insertion_order': entry.get('order', 100), 'position': 'before_char' if entry.get('position', 0) == 0 else 'after_char',
                 'extensions': {**entry.get('extensions', {}), **entry}}
                for entry in lorebook['entries'].values()
            ]}
        return {
            "spec": defaults.get('spec', 'chara_card_v3'),
            "spec_version": defaults.get('spec_version', '3.0'),
            "data": data
        }

    def generate_lorebook(self) -> Dict[str, Any]:
        entries = []
        current_id = 0

        print("扫描角色文件...")
        characters = self.discover_characters()
        print(f"发现 {len(characters)} 个角色")

        print("\n生成角色条目...")
        for char_name, entry_type in characters:
            entries.append(self.create_character_entry(char_name, current_id, entry_type))
            current_id += 1
            print(f"  [OK] {char_name} ({entry_type})")

        print("\n生成设定条目...")
        setting_entries = self.extract_setting_entries(current_id)
        entries.extend(setting_entries)
        current_id += len(setting_entries)
        print(f"  [OK] 共{len(setting_entries)}个设定条目")

        print("\n生成关系网条目...")
        relationship_entries = self.extract_relationship_entries(current_id)
        entries.extend(relationship_entries)
        current_id += len(relationship_entries)
        print(f"  [OK] 共{len(relationship_entries)}个关系组")

        style_entries = self.extract_style_entries(current_id)
        entries.extend(style_entries)
        current_id += len(style_entries)

        print("\n生成 MVU 系统条目...")
        mvu_entries = self.generate_mvu_entries(current_id)
        entries.extend(mvu_entries)
        current_id += len(mvu_entries)
        print(f"  [OK] 共{len(mvu_entries)}个 MVU 条目")

        for source in self.content.files((self.config.get('imports') or {}).get('entries', [])):
            raw = json.loads(source.read_text(encoding='utf-8'))
            imported = raw.get('entries', [])
            for entry in imported.values() if isinstance(imported, dict) else imported:
                restored = deepcopy(entry)
                restored['uid'] = len(entries)
                entries.append(restored)
        titles = {entry.get('comment') for entry in entries}
        for entry in entries:
            for reference in re.findall(r"getwi\([^,]*,\s*['\"]([^'\"]+)", entry.get('content', '')):
                if reference not in titles:
                    raise ValueError(f'Missing worldbook reference {reference!r} in {entry.get("comment")}')
        return {"entries": {str(e["uid"]): e for e in entries}}

    def save_files(self):
        project = self.config.get('project', {})
        project_name = project.get('name', '作品')

        print(f"\n{'='*60}")
        print(f"生成SillyTavern文件: {project_name}")
        print(f"{'='*60}\n")

        lorebook = self.generate_lorebook()
        lorebook_file = self.output_dir / f"{project_name}世界书.json"
        with open(lorebook_file, 'w', encoding='utf-8') as f:
            json.dump(lorebook, f, ensure_ascii=False, indent=2)
        print(f"\n[OK] 世界书: {lorebook_file}")

        narrator_file = self.output_dir / f"{project_name}叙事者.json"
        with open(narrator_file, 'w', encoding='utf-8') as f:
            json.dump(self.generate_narrator_card(lorebook), f, ensure_ascii=False, indent=2)
        print(f"[OK] 角色卡: {narrator_file}")
        if (self.mvu_config.get('panel') or {}).get('enabled', True):
            panel_file = self.output_dir / "悬浮状态栏.json"
            panel_file.write_text(json.dumps(self._script_record("MVU 悬浮状态面板", self._build_panel_script()), ensure_ascii=False, indent=2), encoding='utf-8')
            print(f"[OK] 悬浮状态栏: {panel_file}")

        print(f"\n{'='*60}")
        print("[OK] 所有文件生成完成！")
        print(f"{'='*60}")


def main():
    parser = argparse.ArgumentParser(description="生成指定作品的世界书与角色卡")
    parser.add_argument("--work", required=True, type=Path, help="作品目录，如 works/示例作品；相对当前工作目录")
    args = parser.parse_args()
    project_root = args.work

    try:
        generator = SillyTavernGenerator(str(project_root))
        generator.save_files()
    except Exception as e:
        print(f"[Error] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
