#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SillyTavern 世界书和角色卡生成器
版本: 3.0.0
"""

import json
import os
import re
import yaml
from pathlib import Path
from typing import Dict, List, Any
from datetime import datetime


class ConfigLoader:
    """从AGENTS.md加载YAML配置"""

    @staticmethod
    def load_config(project_root: Path) -> Dict[str, Any]:
        agents_file = project_root / "AGENTS.md"
        if not agents_file.exists():
            raise FileNotFoundError(f"AGENTS.md not found")

        with open(agents_file, 'r', encoding='utf-8') as f:
            content = f.read()

        pattern = r'##\s*2\.\s*配置区.*?(```yaml\s*\n(.*?)```)\s*(?:---\s*)?##\s*3\.'
        match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
        if not match:
            raise ValueError("Cannot extract config from AGENTS.md")

        try:
            return yaml.safe_load(match.group(2))
        except yaml.YAMLError as e:
            raise ValueError(f"YAML parse error: {e}")


class SillyTavernGenerator:
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.config = ConfigLoader.load_config(self.project_root)

        paths = self.config.get('paths', {})
        char_gen = self.config.get('character_generation', {})
        self.characters_dir = self.project_root / char_gen.get('output_dir', 'literature/characters')
        self.scenarios_dir = self.project_root / paths.get('scenarios_dir', 'literature/scenarios')
        self.output_dir = self.project_root / paths.get('output_dir', 'output')
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.dimensions = self.config.get('dimensions', [])
        self.entry_types = self.config.get('entry_types', {})
        self.silly_defaults = self.config.get('sillytavern_defaults', {})
        self.narrator_config = self.config.get('narrator', {})

    def get_entry_type_config(self, entry_type: str) -> Dict[str, Any]:
        return self.entry_types.get(entry_type, {
            'prefix': '', 'order_start': 100, 'order_step': 1, 'depth': 4,
            'position': 0, 'constant': False, 'selective': True, 'ignore_budget': True
        })

    def merge_character_files(self, char_name: str, entry_type: str = "protagonist") -> str:
        md_file = self.characters_dir / f"{char_name}.md"
        stages_file = self.characters_dir / f"{char_name}_stages.json"

        if not md_file.exists():
            print(f"Warning: {md_file} not found")
            return ""

        with open(md_file, 'r', encoding='utf-8') as f:
            md_content = f.read()

        stages_content = "{}"
        if stages_file.exists():
            with open(stages_file, 'r', encoding='utf-8') as f:
                stages_content = f.read()

        return f"""<character name="{char_name}" type="{entry_type}">
{md_content}

<character_states>
{stages_content}
</character_states>
</character>"""

    def discover_characters(self) -> List[str]:
        if not self.characters_dir.exists():
            return []
        chars = []
        for md_file in self.characters_dir.glob("*.md"):
            if not md_file.stem.endswith('_stages'):
                chars.append(md_file.stem)
        return sorted(chars)

    def create_character_entry(self, char_name: str, entry_id: int, entry_type: str = "protagonist") -> Dict[str, Any]:
        type_config = self.get_entry_type_config(entry_type)
        defaults = self.silly_defaults.get('entry', {})

        content = self.merge_character_files(char_name, entry_type)
        keys = [char_name]
        md_path = self.characters_dir / f"{char_name}.md"
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
            "selective": type_config.get('selective', True),
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
        """Collect source_file paths from entry_types that have dedicated parsers."""
        dedicated = set()
        for et_config in self.entry_types.values():
            sf = et_config.get('source_file')
            if sf:
                dedicated.add((self.project_root / sf).resolve())
        return dedicated

    def extract_setting_entries(self, start_id: int) -> List[Dict[str, Any]]:
        entries = []
        type_config = self.get_entry_type_config('setting')
        defaults = self.silly_defaults.get('entry', {})

        source_files = self.config.get('character_generation', {}).get('source_files', [])
        dedicated_files = self._collect_dedicated_source_files()

        for source_pattern in source_files:
            source_dir = self.project_root / Path(source_pattern).parent
            source_glob = Path(source_pattern).name

            if not source_dir.exists():
                continue

            for settings_file in source_dir.glob(source_glob):
                if settings_file.resolve() in dedicated_files:
                    continue
                with open(settings_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                header_pattern = r'【([^】]+)】(?:[（(]([^）)]+)[）)])?'
                headers = list(re.finditer(header_pattern, content))

                for idx, match in enumerate(headers):
                    name = match.group(1).strip()
                    keywords_text = match.group(2)

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
                        "constant": type_config.get('constant', False),
                        "selective": type_config.get('selective', True),
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

    def extract_pov_entries(self, start_id: int) -> List[Dict[str, Any]]:
        type_config = self.get_entry_type_config('pov')
        defaults = self.silly_defaults.get('entry', {})

        source_path = type_config.get('source_file')
        if not source_path:
            return []
        source_file = self.project_root / source_path
        if not source_file.exists():
            return []

        with open(source_file, 'r', encoding='utf-8') as f:
            content = f.read()

        header_pattern = r'【([^】]+)】(?:[（(]([^）)]+)[）)])?'
        headers = list(re.finditer(header_pattern, content))

        default_index = type_config.get('default_index', 0)
        group_name = type_config.get('group', 'pov')
        sticky_val = type_config.get('sticky', 999)
        entries = []

        for idx, match in enumerate(headers):
            name = match.group(1).strip()
            keywords_text = match.group(2)
            if not name:
                continue

            keys = [k.strip() for k in re.split(r'[，,、]', keywords_text) if k.strip()] if keywords_text else [name]

            start_pos = match.end()
            end_pos = headers[idx + 1].start() if idx + 1 < len(headers) else len(content)
            pov_content = content[start_pos:end_pos].strip()
            if not pov_content:
                continue

            is_default = (len(entries) == default_index)
            order = type_config.get('order_start', 40) + len(entries) * type_config.get('order_step', 1)

            entry = {
                "uid": start_id + len(entries),
                "key": keys,
                "keysecondary": [],
                "comment": f"{type_config.get('prefix', '视角_')}{name}",
                "content": f"### {name}\n\n{pov_content}",
                "constant": is_default,
                "selective": not is_default,
                "selectiveLogic": defaults.get('selective_logic', 0),
                "addMemo": defaults.get('add_memo', True),
                "order": order,
                "position": type_config.get('position', 0),
                "disable": False,
                "group": group_name,
                "probability": defaults.get('probability', 100),
                "useProbability": defaults.get('use_probability', True),
                "depth": type_config.get('depth', 2),
                "delay": defaults.get('delay', 0),
                "cooldown": defaults.get('cooldown', 0),
                "sticky": sticky_val,
                "scanDepth": defaults.get('scan_depth', 2),
                "vectorized": defaults.get('vectorized', False),
                "ignoreBudget": type_config.get('ignore_budget', True),
                "excludeRecursion": defaults.get('exclude_recursion', False),
                "preventRecursion": defaults.get('prevent_recursion', False)
            }
            entries.append(entry)

        return entries

    def extract_relationship_entries(self, start_id: int) -> List[Dict[str, Any]]:
        entries = []
        type_config = self.get_entry_type_config('relationship')
        defaults = self.silly_defaults.get('entry', {})

        source_file = type_config.get('source_file')
        if not source_file:
            return []
        relationship_file = self.project_root / source_file
        if not relationship_file.exists():
            return []

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

            order = type_config.get('order_start', 300) + len(entries) * type_config.get('order_step', 1)

            entries.append({
                "uid": start_id + len(entries),
                "key": keys,
                "keysecondary": [],
                "comment": f"{type_config.get('prefix', '关系_')}{name}",
                "content": f"### {name}\n\n{block_content}",
                "constant": type_config.get('constant', False),
                "selective": type_config.get('selective', True),
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

    def extract_example_dialogue(self) -> str:
        narrator = self.config.get('narrator', {})
        example_path = narrator.get('example_dialogue_file')
        if not example_path:
            return ""
        example_file = self.project_root / example_path
        if not example_file.exists():
            return ""

        max_length = narrator.get('example_dialogue_max_length', 4000)

        with open(example_file, 'r', encoding='utf-8') as f:
            content = f.read()

        lines = content.split('\n')
        cleaned_lines = [line.strip() for line in lines if line.strip()]
        return '\n'.join(cleaned_lines)[:max_length]

    def parse_scenario_file(self, file_path: Path) -> str:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        parts = re.split(r'^---\s*$', content, maxsplit=2, flags=re.MULTILINE)
        if len(parts) < 3:
            return content.strip()

        frontmatter = parts[1]
        body = parts[2].strip()

        variable_lines = []
        in_variables = False

        for line in frontmatter.split('\n'):
            line = line.strip()
            if line.startswith('variables:'):
                in_variables = True
                continue
            if in_variables and line and not line.startswith('#'):
                match = re.search(r'^([^:]+):\s*\{(.*)\}', line)
                if match:
                    char_name = match.group(1).strip()
                    vars_str = match.group(2)

                    for dim in self.dimensions:
                        dim_name = dim['name']
                        short_dim_name = dim_name.replace(char_name, '').strip()

                        dim_pattern = rf"{re.escape(short_dim_name)}[\s:]*(\d+)"
                        dim_match = re.search(dim_pattern, vars_str)
                        if dim_match:
                            var_value = dim_match.group(1)
                            variable_lines.append(
                                f'_.set("{char_name}.{short_dim_name}", 0, {var_value});'
                            )

        if not variable_lines:
            return body

        init_block = "\n<details>\n<summary>角色状态初始化</summary>\n<character_states_init>\n"
        init_block += "\n".join(variable_lines)
        init_block += "\n</character_states_init>\n</details>"

        return body + "\n" + init_block

    def load_scenarios(self) -> List[str]:
        if not self.scenarios_dir.exists():
            return []
        scenarios = []
        for file_path in sorted(self.scenarios_dir.glob("*.md")):
            greeting = self.parse_scenario_file(file_path)
            if greeting:
                scenarios.append(greeting)

        return scenarios

    def _build_dimension_summary(self) -> str:
        lines = []
        for i, dim in enumerate(self.dimensions, 1):
            name = dim['name']
            ranges = dim.get('ranges', [0, 100])
            stages = dim.get('stages', [])
            n = len(stages)
            parts = []
            for j in range(n - 1, -1, -1):
                lo = ranges[n - 1 - j]
                hi = ranges[n - j]
                parts.append(f"{stages[j]}{lo}-{hi}")
            lines.append(f"{name}: {'/'.join(parts)}")
        return '\n'.join(lines)

    def generate_narrator_card(self) -> Dict[str, Any]:
        project = self.config.get('project', {})
        narrator = self.config.get('narrator', {})
        defaults = self.silly_defaults.get('narrator', {})

        scenarios = self.load_scenarios()
        first_mes = scenarios[0] if scenarios else ""
        alternate_greetings = scenarios[1:] if len(scenarios) > 1 else []

        dim_names = [d['name'] for d in self.dimensions]

        state_instructions = narrator.get('state_instructions', '')
        post_history = state_instructions.strip() if state_instructions else ""

        data = {
            "name": narrator.get('name', '叙事者'),
            "description": narrator.get('description', ''),
            "personality": narrator.get('personality', ''),
            "scenario": narrator.get('world_scenario', ''),
            "first_mes": first_mes,
            "alternate_greetings": alternate_greetings,
            "mes_example": self.extract_example_dialogue(),
            "creator_notes": narrator.get('creator_notes', f"状态维度：{', '.join(dim_names)}"),
            "system_prompt": narrator.get('persona', ''),
            "post_history_instructions": post_history,
            "tags": project.get('tags', []),
            "creator": narrator.get('creator', ''),
            "character_version": project.get('version', '1.0.0'),
            "extensions": {
                "created_at": datetime.now().isoformat(),
                "world_book": f"{project.get('name', '作品')}世界书"
            }
        }

        return {
            "spec": defaults.get('spec', 'chara_card_v2'),
            "spec_version": defaults.get('spec_version', '2.0'),
            "data": data
        }

    def generate_lorebook(self) -> Dict[str, Any]:
        entries = []
        current_id = 0

        print("扫描角色文件...")
        characters = self.discover_characters()
        print(f"发现 {len(characters)} 个角色")

        print("\n生成角色条目...")
        for char_name in characters:
            entries.append(self.create_character_entry(char_name, current_id, "protagonist"))
            current_id += 1
            print(f"  [OK] {char_name}")

        print("\n生成视角条目...")
        pov_entries = self.extract_pov_entries(current_id)
        entries.extend(pov_entries)
        current_id += len(pov_entries)
        for e in pov_entries:
            tag = "[默认]" if e["constant"] else "[可选]"
            print(f"  {tag} {e['comment']} (group={e['group']}, sticky={e['sticky']})")

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
            json.dump(self.generate_narrator_card(), f, ensure_ascii=False, indent=2)
        print(f"[OK] 角色卡: {narrator_file}")

        guide_file = self.output_dir / "使用指南.md"
        with open(guide_file, 'w', encoding='utf-8') as f:
            f.write(f"# {project_name} 使用指南\n\n## 文件\n- {project_name}世界书.json\n- {project_name}叙事者.json\n")
        print(f"[OK] 使用指南: {guide_file}")

        print(f"\n{'='*60}")
        print("[OK] 所有文件生成完成！")
        print(f"{'='*60}")


def main():
    script_dir = Path(__file__).parent
    project_root = script_dir.parent

    try:
        generator = SillyTavernGenerator(str(project_root))
        generator.save_files()
    except Exception as e:
        print(f"[Error] {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
