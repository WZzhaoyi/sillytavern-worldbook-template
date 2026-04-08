# SillyTavern 同人小说世界书模板

基于角色状态系统，自动生成 SillyTavern 兼容的世界书（Lorebook）和叙事者角色卡。

## 快速开始

### 前置条件

- Python 3.7+
- PyYAML

```bash
pip install -r requirements.txt
```

### 使用步骤

1. 克隆本仓库
2. 编辑 `AGENTS.md` 第 2 节配置区，填入你的作品信息
3. 在 `literature/` 下创建角色档案、场景剧本等素材文件
4. 运行生成脚本：
   ```bash
   python scripts/generate_sillytavern.py
   ```
5. 将 `output/` 下生成的 JSON 文件导入 SillyTavern

## 项目结构

```
project/
├── CLAUDE.md                 # Claude Code 项目入口
├── AGENTS.md                 # 配置中心与完整文档
├── literature/
│   ├── characters/           # 角色档案（.md + _stages.json）
│   ├── scenarios/            # 场景剧本（含 YAML Frontmatter）
│   ├── fanfic/               # 原始素材（【标题】(关键词) 格式）
│   ├── original/             # 原著文本（可选）
│   └── vocab/                # 参考词库（可选）
├── scripts/
│   └── generate_sillytavern.py
└── output/                   # 生成的世界书和角色卡
```

## 详细文档

完整的配置说明、角色生成工作流、文件格式规范等，请参阅 [AGENTS.md](AGENTS.md)。

## 许可证

[MIT](LICENSE)
