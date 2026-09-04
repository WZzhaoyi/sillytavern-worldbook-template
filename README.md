# SillyTavern 同人小说世界书模板

基于 MVU（Message Variable Update）生命周期，自动生成支持“开局创建 → 正文前检查 → 正文后更新 → 状态栏实时订阅”的 SillyTavern 世界书和叙事者角色卡。预设状态集合包含世界、人物、物品、地点和事件。

## 快速开始

### 前置条件

- Python 3.7+
- PyYAML

```bash
pip install -r requirements.txt
```

### 初始化项目（四选一）

1. **Use this template**（推荐）——GitHub仓库主页点击「Use this template」→「Create a new repository」，基于当前主分支生成**全新独立仓库**。
2. **Release 源码归档**——在 [Releases](../../releases) 页下载对应版本的 `Source code (zip/tar.gz)`，解压即得。
3. **`degit`**（CLI 用户）：
   ```bash
   npx degit WZzhaoyi/sillytavern-worldbook-template my-project
   ```
   一行命令拉取最新主分支快照，无 git 历史。
4. **`git clone`**（持续开发）：
   ```bash
   git clone https://github.com/WZzhaoyi/sillytavern-worldbook-template.git my-project
   ```

### 使用步骤

1. 用上述任一方式建立项目，开启 AGENTS 对话
2. 新作品先按 [初始策划指南](docs/initial-planning-guide.md) 完成 `literature/策划蓝图.md`
3. 编辑 `AGENTS.md` 第 2 节配置区，填入你的作品信息
4. 在 `literature/` 下创建角色档案、场景剧本等素材文件
5. 运行生成脚本：
   ```bash
   python scripts/generate_sillytavern.py
   ```
6. 将 `output/` 下生成的 JSON 文件导入 SillyTavern

作品存在互斥时代、地域或成长层时，在 `entry_types.setting.layers` 分别配置各层，并用 `active_layer` 选择本次构建内容；生成器只输出公共设定和当前层，避免矛盾内容包同时注入。

叙事视角不是 MVU 状态。Step 0 会提示创作者在第一人称、第三人称限制或全知等方案中选择一个固定视角，最终只写入 `narrator.style_instructions`；模板不默认生成视角切换器。

### 转换角色阶段数据格式

角色阶段数据可在 JSON/YAML 之间批量转换，脚本会同步更新 `AGENTS.md` 中的 `character_generation.stages_format`：

```bash
python scripts/convert_stages_format.py yaml
python scripts/convert_stages_format.py json
```

默认转换 `literature/characters/*_stages.{json|yaml|yml}`，成功后删除源格式文件。可加 `--keep-source` 保留源文件，或用 `--dry-run` 预览操作。

如需修复阶段文件的 JSON/YAML 语法（例如列表缩进、单引号、尾随逗号或未转义双引号），可运行：

```bash
python scripts/convert_stages_format.py yaml --repair
python scripts/convert_stages_format.py json --repair
```

`--repair` 只修复序列化语法，不迁移旧阶段 Schema；阶段内容仍须符合 `metrics → id → 阶段名 → 行为描述`。

### 启用 MVU 运行时

生成的角色卡已经携带以下内容：

- MVU 运行时导入脚本
- 按 `state_model` 自动生成的 ZOD Schema
- 隐藏 `<StateCheck>` 与 `<UpdateVariable>` 的显示/历史正则
- 直接读取 `stat_data` 的无 iframe 五集合悬浮面板

只需安装基础脚本宿主：

1. **安装 JS-Slash-Runner 扩展**
   - 在 SillyTavern「扩展」→「安装扩展」中填入：
     ```
     https://github.com/n0vi028/JS-Slash-Runner
     ```
   - 安装后启用扩展。

2. 导入生成的世界书和角色卡。随卡脚本会由酒馆助手自动加载，无需再创建外置“角色状态管理”脚本。

运行时状态位于 `stat_data.{世界,人物,物品,地点,事件}`。场景首条消息或自定义开局负责创建快照；每轮 `<StateCheck>`、正文与 `<UpdateVariable>` 在同一次 LLM 调用中生成；MVU、ZOD 校验和悬浮面板刷新均在本地完成。

`_stages.json` / `_stages.yaml` 继续作为作者素材保留，但只按 `character_metrics.id → 阶段名 → 行为描述` 保存人物表现。数值边界只在 `state_model.character_metrics` 定义，不再由阶段文件重复声明。

## 项目结构

```
project/
├── CLAUDE.md                 # Claude Code 项目入口
├── AGENTS.md                 # 配置中心与完整文档
├── docs/
│   └── initial-planning-guide.md # Step 0 初始策划方法
├── literature/
│   ├── 策划蓝图.md           # Step 0 输出，不参与生成器扫描
│   ├── characters/           # 角色档案（.md + _stages.{json|yaml}）
│   ├── scenarios/            # 场景剧本（含 YAML Frontmatter）
│   ├── fanfic/               # 原始素材（【标题】(关键词) 格式）
│   ├── original/             # 原著文本（可选）
│   └── vocab/                # 参考词库（可选）
├── scripts/
│   ├── generate_sillytavern.py # 世界书/角色卡/MVU 生成器
│   └── convert_stages_format.py
├── templates/mvu/
│   └── floating_panel.js       # 无 iframe 悬浮面板模板
├── tests/
│   └── test_generate_sillytavern.py
└── output/                   # 生成的世界书和角色卡
```

## 详细文档

完整的配置说明、角色生成工作流、文件格式规范等，请参阅 [AGENTS.md](AGENTS.md)。

## 许可证

[MIT](LICENSE)
