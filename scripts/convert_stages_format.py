#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
角色阶段数据格式转换工具。

在 `_stages.json` 与 `_stages.yaml` 之间批量转换，并同步更新
AGENTS.md 配置区中的 character_generation.stages_format。
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import yaml


SUPPORTED_FORMATS = ("json", "yaml")


class ConversionError(Exception):
    """用户可修复的转换错误。"""


def detect_project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert literature/characters/*_stages files between JSON and YAML."
    )
    parser.add_argument(
        "target_format",
        choices=SUPPORTED_FORMATS,
        help="目标格式：json 或 yaml",
    )
    parser.add_argument(
        "--characters-dir",
        default=None,
        help="角色目录，默认从 AGENTS.md 的 character_generation.output_dir 读取，读取失败则使用 literature/characters",
    )
    parser.add_argument(
        "--agents-file",
        default=None,
        help="AGENTS.md 路径，默认使用项目根目录下的 AGENTS.md",
    )
    parser.add_argument(
        "--keep-source",
        action="store_true",
        help="保留源格式文件。默认转换成功后删除源文件，避免脚本扫描格式不一致。",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="目标文件已存在时覆盖。默认遇到同名目标文件会报错。",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只展示将执行的操作，不写入或删除文件。",
    )
    parser.add_argument(
        "--no-config-update",
        action="store_true",
        help="不更新 AGENTS.md 中的 character_generation.stages_format。",
    )
    return parser.parse_args()


def extract_config_yaml(agents_file: Path) -> Tuple[str, int, int]:
    if not agents_file.exists():
        raise ConversionError(f"Cannot find AGENTS.md: {agents_file}")

    content = agents_file.read_text(encoding="utf-8")
    pattern = r"##\s*2\.\s*配置区.*?^```yaml\s*\n(.*?)^```\s*(?:---\s*)?##\s*3\."
    match = re.search(pattern, content, re.DOTALL | re.IGNORECASE | re.MULTILINE)
    if not match:
        raise ConversionError("Cannot extract YAML config block from AGENTS.md")
    return content, match.start(1), match.end(1)


def load_config(agents_file: Path) -> Dict[str, Any]:
    content, start, end = extract_config_yaml(agents_file)
    yaml_text = content[start:end]
    try:
        return yaml.safe_load(yaml_text) or {}
    except yaml.YAMLError as exc:
        raise ConversionError(f"Invalid YAML config in AGENTS.md: {exc}") from exc


def resolve_characters_dir(project_root: Path, agents_file: Path, cli_value: Optional[str]) -> Path:
    if cli_value:
        path = Path(cli_value)
        return path if path.is_absolute() else project_root / path

    try:
        config = load_config(agents_file)
    except ConversionError:
        return project_root / "literature/characters"

    char_gen = config.get("character_generation", {})
    configured = char_gen.get("output_dir", "literature/characters")
    path = Path(configured)
    return path if path.is_absolute() else project_root / path


def source_format_for(path: Path) -> Optional[str]:
    if not path.name.endswith(("_stages.json", "_stages.yaml", "_stages.yml")):
        return None
    if path.suffix == ".json":
        return "json"
    if path.suffix in (".yaml", ".yml"):
        return "yaml"
    return None


def iter_stage_files(characters_dir: Path, target_format: str) -> Iterable[Tuple[Path, str]]:
    if not characters_dir.exists():
        return []

    files: List[Tuple[Path, str]] = []
    for path in sorted(characters_dir.glob("*_stages.*")):
        source_format = source_format_for(path)
        if source_format and (source_format != target_format or path.suffix == ".yml"):
            files.append((path, source_format))
    return files


def load_stage_data(path: Path, source_format: str) -> Any:
    raw = path.read_text(encoding="utf-8")
    try:
        if source_format == "json":
            return json.loads(raw) if raw.strip() else {}
        return yaml.safe_load(raw) or {}
    except json.JSONDecodeError as exc:
        raise ConversionError(f"Invalid JSON in {path}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ConversionError(f"Invalid YAML in {path}: {exc}") from exc


def dump_stage_data(data: Any, target_format: str) -> str:
    if target_format == "json":
        return json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)


def target_path_for(source_path: Path, target_format: str) -> Path:
    suffix = ".json" if target_format == "json" else ".yaml"
    return source_path.with_suffix(suffix)


def convert_file(
    source_path: Path,
    source_format: str,
    target_format: str,
    keep_source: bool,
    overwrite: bool,
    dry_run: bool,
) -> str:
    target_path = target_path_for(source_path, target_format)

    if target_path.exists() and target_path != source_path and not overwrite:
        raise ConversionError(
            f"Target file already exists: {target_path}. Use --overwrite to replace it."
        )

    if dry_run:
        action = f"{source_path} -> {target_path}"
        if not keep_source:
            action += " (remove source)"
        return action

    data = load_stage_data(source_path, source_format)
    target_path.write_text(dump_stage_data(data, target_format), encoding="utf-8")

    if not keep_source and source_path != target_path:
        source_path.unlink()

    return f"{source_path} -> {target_path}"


def update_agents_format(agents_file: Path, target_format: str, dry_run: bool) -> bool:
    content, start, end = extract_config_yaml(agents_file)
    yaml_text = content[start:end]
    line_pattern = re.compile(
        r'^(\s*stages_format:\s*)(["\']?)(json|yaml)(["\']?)(\s*(?:#.*)?)$',
        re.MULTILINE,
    )

    match = line_pattern.search(yaml_text)
    if not match:
        raise ConversionError("Cannot find character_generation.stages_format in AGENTS.md config")

    quote = match.group(2) or match.group(4) or '"'
    replacement = f"{match.group(1)}{quote}{target_format}{quote}{match.group(5)}"
    updated_yaml = line_pattern.sub(replacement, yaml_text, count=1)

    if updated_yaml == yaml_text:
        return False

    if not dry_run:
        agents_file.write_text(content[:start] + updated_yaml + content[end:], encoding="utf-8")

    return True


def main() -> int:
    args = parse_args()
    project_root = detect_project_root()
    agents_file = Path(args.agents_file) if args.agents_file else project_root / "AGENTS.md"
    if not agents_file.is_absolute():
        agents_file = project_root / agents_file

    characters_dir = resolve_characters_dir(project_root, agents_file, args.characters_dir)
    stage_files = list(iter_stage_files(characters_dir, args.target_format))

    try:
        if not stage_files:
            print(f"No *_stages files need conversion in {characters_dir}")
        else:
            for source_path, source_format in stage_files:
                result = convert_file(
                    source_path=source_path,
                    source_format=source_format,
                    target_format=args.target_format,
                    keep_source=args.keep_source,
                    overwrite=args.overwrite,
                    dry_run=args.dry_run,
                )
                print(result)

        if not args.no_config_update:
            changed = update_agents_format(agents_file, args.target_format, args.dry_run)
            if changed:
                suffix = " (dry run)" if args.dry_run else ""
                print(f"Updated {agents_file}: stages_format -> {args.target_format}{suffix}")
            else:
                print(f"{agents_file}: stages_format already {args.target_format}")

        return 0
    except ConversionError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
