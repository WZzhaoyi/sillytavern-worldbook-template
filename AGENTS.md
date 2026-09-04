# SillyTavern 同人小说世生成系统

> **Version**: 3.0.0
> **Purpose**: 基于 MVU 生命周期和多实体状态模型，生成 SillyTavern 世界书与叙事者角色卡

---

## 1. 系统概述

### 1.1 工作流

所有项目遵循同一条串行流水线。新作品先执行 Step 0；有原著文本时 Step 0 可简化后从 Step 2 开始提取；无原著时从 Step 3 开始直接创作；有旧版世界书/角色卡导出时从 Step R 开始逆向恢复。

```
Step 0  初始策划蓝图        ← 新作品推荐，先设计规则、循环、事件与状态
  ↓
Step 1  准备与配置
  ↓
Step R  逆向恢复            ← 有旧版世界书/角色卡导出（JSON）时执行
  ↓
Step 2  章节概述            ← 有原著文本时执行
  ↓
Step 3  设定总集
  ↓
Step 4  风格样本            ← 可选，推荐
  ↓
Step 5  角色档案
  ↓
Step 6  关系网               ← 可选
  ↓
Step 7  场景剧本
  ↓
Step 8  运行脚本 → 世界书.json + 角色卡.json
  ↓
Step 9  导入 SillyTavern
```

### 1.2 目录结构约定

```
project/
├── CLAUDE.md                 # Claude Code项目入口
├── AGENTS.md                 # 本指南与配置中心
├── docs/
│   └── initial-planning-guide.md # Step 0 初始策划方法
├── literature/
│   ├── 策划蓝图.md           # Step 0 输出，不参与生成器扫描
│   ├── characters/           # 角色资产目录
│   │   ├── {角色A}.md
│   │   ├── {角色A}_stages.{json|yaml} # 阶段表现规则，不保存运行时值
│   │   ├── {角色B}.md
│   │   └── {角色B}_stages.{json|yaml}
│   ├── scenarios/            # 场景剧本目录
│   │   └── {场景}.md         # 含YAML Frontmatter变量配置
│   ├── fanfic/               # 原始素材目录
│   │   └── {设定文件}.txt    # 【标题】(关键词) 格式
│   ├── original/             # 原著文本（可选）
│   │   ├── 章节概述.md       # Step 2 生成
│   │   └── {旧版导出}.json   # Step R 逆向恢复（世界书/角色卡导出）
│   └── vocab/                # 参考词库（可选）
├── scripts/
│   └── generate_sillytavern.py  # 主生成脚本
└── output/                   # 输出目录
    ├── 世界书.json
    ├── 角色卡.json
    └── 使用指南.md
```

### 1.3 文件命名规范

| 文件类型 | 命名格式 | 示例 |
|---------|---------|------|
| 策划蓝图 | `策划蓝图.md` | `策划蓝图.md` |
| 章节概述 | `章节概述.md` | `章节概述.md` |
| 角色基础档案 | `{角色名}.md` | `张三.md` |
| 角色阶段数据 | `{角色名}_stages.{json\|yaml}` | `张三_stages.json` 或 `张三_stages.yaml` |
| 场景剧本 | `{序号}_{场景名}.md` 或 `{场景名}.md` | `01_initial.md` |
| 设定文件 | 任意 `.txt` | `设定总集.txt` |

---

## 2. 配置区

> ⚠️ **重要**：本区域的YAML格式必须严格正确，否则脚本将报错提示。
> 
> 以下为**模板配置**，请根据你的作品替换所有 `{占位符}` 内容。

### 🔒 LLM 修改守则（必读）

改动本节时严格遵守，否则 `python scripts/generate_sillytavern.py` 会直接解析失败：

1. **保留配置骨架，扩展指定位置**：不得重命名 `project`、`state_model`、`mvu` 等顶层键，也不得改变世界/人物/物品/地点/事件五个核心集合的 `path` 与 `kind`。允许按策划蓝图增删完整的 `character_metrics` 块和集合 `fields`；新增内容必须照抄同类块的层级与缩进。生成器要求的生命周期字段不可删除。
2. **缩进统一用 2 空格**：绝不用 Tab，绝不混合 2/4 空格；同一层级对齐必须完全一致。
3. **冒号后必须有空格**：`name: "值"` ✓；`name:"值"` ✗。
4. **`stages` 数量 = `ranges` 长度 − 1**：`ranges: [0, 25, 50, 75, 100]`（5 个边界）→ `stages` 必须正好 4 条。区间统一为左闭右开，只有最后一段包含最大值；`stages` 按从高到低排列。
5. **多行字符串用 `|` 或 `>`，且正文缩进必须比键多 2 格**：
   ```yaml
   persona: >
     这里是正文第一行。   # 正文整体相对 persona 多缩进 2 格
     第二行保持同样缩进。
   ```
   正文中间空行用于分段，但**不要**出现只含空格的"伪空行"。
6. **占位符 `{...}` 可以改成任意中/英文内容**，但必须保留包裹的引号（如果模板本来有）。
7. **不要删掉注释分隔线**（`# ===== ...`）；脚本不读它们，但它们是 LLM 自己定位配置块的路标。
8. **修改后立即运行** `python scripts/generate_sillytavern.py`；若失败会报出具体行号与上下文，按提示修复后再改下一处。

```yaml
# =============================================================================
# 作品元数据
# =============================================================================
project:
  name: "{作品名}"
  version: "1.0.0"
  description: "{一句话描述你的作品}"

# =============================================================================
# MVU 状态模型（唯一事实源）
# 世界为单例；人物、物品、地点、事件为按名称索引的实体集合。
# 不要在两个集合里重复保存同一事实：人物位置写在人物，物品归属写在物品。
# =============================================================================
state_model:
  character_metrics:
    - id: "affection"
      name: "好感"
      description: "人物对主角的信任与亲近程度"
      initial: 0
      change:
        minor: [1, 2]
        major: [3, 5]
      ranges: [0, 25, 50, 75, 100]
      stages:
        - "生死相托"
        - "主动亲近"
        - "初步信任"
        - "陌生戒备"

    - id: "corruption"
      name: "异化"
      description: "角色受超自然力量或负面影响改变的程度"
      initial: 0
      change:
        minor: [1, 2]
        major: [3, 5]
      ranges: [0, 30, 60, 100]
      stages:
        - "彻底失控"
        - "显著异化"
        - "稳定"

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
        描述: {type: "string", default: ""}
        备注: {type: "string", default: ""}

    locations:
      path: "地点"
      label: "地点"
      kind: "collection"
      fields:
        已发现: {type: "boolean", default: false}
        状态: {type: "string", default: "正常"}
        描述: {type: "string", default: ""}
        备注: {type: "string", default: ""}

    events:
      path: "事件"
      label: "事件"
      kind: "collection"
      fields:
        状态: {type: "enum", default: "未触发", values: ["未触发", "进行中", "已完成", "已失败", "已搁置"]}
        阶段: {type: "enum", default: "起", values: ["起", "承", "转", "合"]}
        地点: {type: "string", default: ""}
        参与者: {type: "string_list", default: []}
        摘要: {type: "string", default: ""}
        结果: {type: "string", default: ""}
        备注: {type: "string", default: ""}

# =============================================================================
# MVU 运行时配置
# 生成的角色卡会自动携带 MVU、ZOD Schema、隐藏变量块正则和无 iframe 悬浮面板。
# 运行时状态统一保存于 stat_data，不再依赖 _.set 或外置角色状态管理脚本。
# =============================================================================
mvu:
  runtime_url: "https://testingcf.jsdelivr.net/gh/NLKASHEI/MVU-offline@v1.0.2/mvu_bundle_full.js"
  schema_helper_url: "https://testingcf.jsdelivr.net/gh/StageDog/tavern_resource/dist/util/mvu_zod.js"
  max_characters_per_turn: 3
  max_entities_per_turn: 6
  max_active_events: 3
  preflight_max_words: 100
  update_analysis_max_words: 120
  panel:
    enabled: true
    title: "{作品名} · 世界状态"
    width: 840

# =============================================================================
# 路径配置
# =============================================================================
paths:
  scenarios_dir: "literature/scenarios"
  output_dir: "output"

# =============================================================================
# 角色生成配置（Agent使用）
# =============================================================================
character_generation:
  # 角色档案输出目录（脚本从此目录扫描 .md 和 _stages.{format}）
  output_dir: "literature/characters"
  
  # 阶段数据文件格式："json" 或 "yaml"（选定后统一使用，不可混用）
  stages_format: "json"
  
  # Agent提取参考（正则表达式，仅供Agent生成角色档案时参考，脚本不使用）
  extract_patterns:
    aliases: '【名称】\s*{name}[\(（]([^\)）]+)[\)）]'
    appearance: '(?:容貌|外貌|相貌|容颜)[：:](.*?)(?=\n\n|\n【|$)'
    personality: '(?:性格|性情)[：:](.*?)(?=\n\n|\n【|$)'
    relationships: '(?:与.+?的关系|情感)[：:](.*?)(?=\n\n|\n【|$)'

# =============================================================================
# 输出配置
# =============================================================================
entry_types:
  # 角色类型判定规则：
  # - 存在同名 {角色名}_stages.json / .yaml / .yml → 主角组 protagonist
  # - 不存在同名阶段数据文件 → 配角组 supporting
  # 主角组
  protagonist:
    prefix: ""
    order_start: 100
    order_step: 1
    depth: 4
    position: 0
    constant: false
    ignore_budget: true
  
  # 配角组
  supporting:
    prefix: "配角_"
    order_start: 200
    order_step: 1
    depth: 5
    position: 0
    constant: false
    ignore_budget: false
  
  # 设定条目（世界观、剧情指导等）
  # source_files: 设定文件扫描路径（glob模式），文件内必须为【标题】(关键词) 格式
  # active_layer/layers: 可选的构建时互斥内容层。公共设定始终扫描，只额外扫描当前层。
  # 例：active_layer: "前期"，layers: {前期: ["literature/fanfic/layers/early/*.txt"], 后期: [...]}
  # 标题前加 ★（如 ★【世界观】）表示常驻上下文，忽略关键词强制注入；否则走关键词触发
  # 不要包含原著正文路径（会被当作设定条目错误解析）
  setting:
    prefix: ""
    order_start: 50
    order_step: 1
    depth: 2
    position: 0
    constant: false
    ignore_budget: false
    source_files:
      - "literature/fanfic/*.txt"
    active_layer: ""
    layers: {}

  # 关系网
  relationship:
    prefix: "关系_"
    order_start: 300
    order_step: 1
    depth: 6
    position: 0
    constant: false
    ignore_budget: false
    source_file: "literature/fanfic/关系网.txt"

# =============================================================================
# SillyTavern字段默认值
# =============================================================================
sillytavern_defaults:
  entry:
    probability: 100
    use_probability: true
    delay: 0
    cooldown: 0
    sticky: 0
    vectorized: false
    exclude_recursion: true
    prevent_recursion: false
    add_memo: true
    scan_depth: 2
    selective_logic: 0        # AND ANY；关系条目要求主关键词 + 任一可选过滤键
  
  narrator:
    spec: "chara_card_v3"
    spec_version: "3.0"
    depth: 4

# =============================================================================
# 叙事者配置（用于生成角色卡）
# 以下为模板，请根据作品替换内容
#
# 【字段与 SillyTavern 卡片的映射及用途】
#   description + example_dialogue_file → data.description
#     风格锚点主阵地：永驻上下文，放原作风格样本段落
#   persona → data.system_prompt
#     只放叙事者身份、作品范围与叙事原则。不重复具体文风执行规则。
#   style_instructions → data.post_history_instructions
#     简明风格执行指令：将风格翻译为具体可执行的写作约束
#   state_model + mvu → 世界书生命周期条目、ZOD Schema、开局快照与悬浮面板
#
# 【职责分工】（避免重复注入）
#   世界观/机制/角色事实 → 世界书设定条目（Step 3 设定总集）
#   场景前提与开场     → 场景剧本 first_mes（Step 7）
#   叙事身份与原则     → persona
#   具体文风执行规则   → style_instructions（保持简短）
# =============================================================================
narrator:
  name: "{作品名}"
  description: "《{作品名}》的叙事者。"
  personality: "{叙事者的性格特征，如：擅长角色言行和场景刻画}"
  creator: "{创作者名称}"
  example_dialogue_file: "literature/fanfic/示例对话.txt"
  example_dialogue_max_length: 4000
  style_instructions: |
    模仿上文提供的风格参考段落：
    - {固定叙事视角，如：使用第三人称限制视角，只写当前角色可感知的内容}
    - {具体特征2，如：短句为主，动作描写干练不加修饰}
    - {具体特征3，如：对话不加"他说/她说"，直接用破折号引出}
    避免：解释性叙述、否定性词组、总结性段落。
  persona: >
    你是《{作品名}》的叙事者。本作是{一句话作品类型与基调，如：古典武侠悲剧 / 末世废土生存 / 现代都市悬疑}。

    【叙事原则】
    - {主线与暗线的安排}
    - {节奏把控原则}
    - {伏笔与悬念的处理}

```

---

## 3. 工作流步骤

> 按顺序执行以下步骤。每步提供 Agent 指令模板，替换 `{占位符}` 后发送即可。

### Step 0: 初始策划蓝图

> 新作品推荐执行；有完整原著或旧版导出时可简化为“明确改编边界、状态字段和开局方案”。详细方法见 [`docs/initial-planning-guide.md`](docs/initial-planning-guide.md)。

**目标**：先确定叙事系统如何持续运行，再创作具体百科。区分三类信息：

- 作者固定：世界不变量、已有实体事实、内容层边界。
- LLM 生成：受约束的 NPC、地点、机遇、遭遇和世界事件实例。
- MVU 保存：本次开局已经发生的事实与跨回合变化。

**输出**：`literature/策划蓝图.md`。蓝图至少回答：

1. 玩家身份、固定叙事视角、世界回应方式和典型十轮体验是什么；
2. 哪些规则永远成立，资源与成长如何形成闭环；
3. 是否存在按地域、时代或成长阶段启停的内容层；
4. 人物、物品、地点和事件各自需要追踪哪些会影响后续叙事的字段；
5. 世界事件如何触发、分阶段推进、收束，并限制同时活跃数量；
6. 哪些内容需要程序化生成，其输入、硬约束、持久化和去重规则是什么；
7. 不同开局各自完整快照和第一个互动钩子是什么；
8. 哪些变量高频、中频、低频更新，哪些内容根本不应进入状态。

**约束**：

- 不要把“可能发生的剧情”写成已发生事实；不要预写唯一主线结局。
- 自定义开局只写 MVU 快照，不动态创建常驻世界书条目，避免多次开局互相污染。
- 正文前检查只输出可观察的叙事约束，不要求展示模型隐藏思维过程。
- 正文后仅更新本轮真实变化，不为刷新面板而强制改写未变化集合。

**指令模板**：

```markdown
请先阅读 docs/initial-planning-guide.md，与我共同完成 Step 0。

作品构想：{一句话构想或已有素材}

请先区分：
1. 必须由作者固定的世界规则与事实；
2. 可以由 LLM 当场生成、但需要约束的内容；
3. 必须由 MVU 跨回合保存的状态。

按指南中的 `literature/策划蓝图.md` 模板提出最少必要问题；确认后写入文件。
不要创作尚未确认的具体人物、势力或剧情结局。
```

### Step 1: 准备与配置

1. 复制 `CLAUDE.md`、`AGENTS.md`、`scripts/generate_sillytavern.py` 到新项目目录
2. 读取 `literature/策划蓝图.md`（如有），据此确认以下创作倾向：
   - 作品类型与基调（如：古典武侠悲剧 / 末世废土 / 现代都市悬疑）
   - 固定叙事视角（如：第一人称、第三人称限制、第三人称全知）
   - 描写风格偏好（文风、场景、对话）
   - 叙事原则（主线/暗线安排、节奏、伏笔）
   - 人物数值的语义、初始值和轻微/重大变化幅度
   - 人物/物品/地点/事件面板需要追踪哪些字段
   - **阶段数据文件格式**：JSON 或 YAML（选定后统一使用，不可混用）
3. 编辑 AGENTS.md 第2节配置区：
   - `project.name` → 作品名
   - `state_model.character_metrics` → 人物数值定义
   - `state_model.collections` → 世界/人物/物品/地点/事件字段定义
   - `narrator` → 叙事者信息（persona 首行作品类型必填；固定视角写入 `style_instructions`）
   - 其他配置项按需调整

### Step R: 逆向恢复（从世界书/角色卡恢复设定）

> 如有sillytavern世界书/角色卡导出文件（JSON），可直接恢复到当前模板的设定文件结构。

**输入**：世界书.json + 叙事者.json（放入 `literature/original/`）

**SillyTavern JSON 格式规则**：

世界书整体 JSON 结构：
```json
{
  "entries": [
    {
      "uid": 0,
      "key": ["关键词1", "关键词2"],
      "keysecondary": [],
      "comment": "条目名称",
      "content": "正文内容",
      "constant": false,
      "selective": true,
      "order": 100,
      "position": 0,
      "disable": false,
      "group": "",
      "probability": 100,
      "depth": 4,
      "sticky": 0,
      "ignoreBudget": true
    },
    {
      "uid": 1,
      "key": ["关键词3"],
      "comment": "另一个条目",
      "content": "正文内容",
      "constant": false,
      "selective": true,
      "order": 101,
      "position": 0,
      "depth": 4
    }
  ]
}
```

角色卡整体 JSON 结构：
```json
{
  "spec": "chara_card_v2",
  "spec_version": "2.0",
  "data": {
    "name": "叙事者",
    "description": "描述 + 风格样本",
    "personality": "性格特征",
    "scenario": "",
    "first_mes": "第一个场景",
    "alternate_greetings": ["备选场景1", "备选场景2"],
    "system_prompt": "persona 配置",
    "post_history_instructions": "style_instructions",
    "creator_notes": "状态维度：维度1,维度2",
    "tags": [],
    "creator": "创作者"
  }
}
```

**事实确认原则**：
- Agent 解析 JSON 后，必须先将识别结果列出供用户确认
- 不确定的条目分类，必须询问用户
- 任何从 JSON 推断的信息（如维度 id、阶段名称），必须标注为「推断」并请用户确认
- **用户确认后**才能生成文件，避免错误写入

**流程**：

```
Step R1: 文件放置
  - JSON 文件放入 literature/original/
  - 同原著文本处理方式
         ↓
Step R2: 解析 JSON + 分类确认
  - 读取世界书.json，分析条目特征
  - 给出分类建议（角色/设定/POV/关系）
  - 列出所有条目分类结果，标记不确定项
  - 用户确认/修正分类
         ↓
Step R3: 重建 AGENTS.md 配置
  - 优先从 MVU Schema / initvar / 更新协议恢复 state_model.character_metrics
  - 从角色条目的 content 中提取各阶段行为数据
  - 从角色卡提取 narrator 配置
  - 用户确认/补充
         ↓
Step R4: 生成设定文件（用户确认配置后）
  - 调用对应 Step 的生成方法（见指令模板）
         ↓
Step R5: 运行脚本生成
```

**指令模板**：

```markdown
请解析以下 JSON 文件，恢复设定文件。

**输入文件**：
- literature/original/{作品名}世界书.json
- literature/original/{作品名}叙事者.json

**Step R2: 分类确认**

读取世界书.json，遍历所有条目，根据以下特征进行分类：

| 信号 | 类型 |
|------|------|
| group=="pov" 或 comment 以「身份_」开头 | 旧版视角候选（不直接入库） |
| comment 以「关系_」开头 | 关系 |
| content 含 `<character` / `<mvu_stage_contract>` XML 标签 | 角色 |
| content 含「性别」「性格」「外貌」键值对 | 角色 |
| content 含世界观/设定关键词 | 设定 |
| key 含 2+ 个可能是人名的词 | 关系 |
| 其他 | 未知 |

输出分类结果表格，列出：
- 条目 uid、comment、key、content 摘要
- 分类结果（确定/不确定）
- 不确定项的建议类型及原因

请用户确认或修正分类后，再继续。

**Step R3: 重建 AGENTS.md 配置**

人物数值配置重建：
1. 优先从角色卡 MVU Schema、`[initvar]` 和更新协议恢复维度 id、ranges、stages
2. 收集角色条目，从 `<mvu_stage_contract>/<stage_rules>` 提取对应阶段的行为内容
3. 若旧卡只保留人物阶段内容而没有数值边界，将 ranges 标记为推断并请用户确认
4. 生成 state_model.character_metrics 配置建议

叙事者配置重建：
- 从角色卡 system_prompt 提取 persona
- 从 post_history_instructions 提取 style_instructions
- 如旧世界书含多个 POV/身份条目，将它们列为候选，由用户选定一个固定叙事视角后并入 style_instructions；不恢复运行时切换器
- 从世界书 `[mvu_protocol]`、`[initvar]` 与角色卡 Tavern Helper 扩展恢复 MVU 配置
- 从角色卡 description 提取描述和风格样本
- 用户确认/补充

生成 AGENTS.md 配置区建议，用户确认后写入。

**Step R4: 生成设定文件**（用户确认配置后执行）

根据分类结果，调用对应 Step 的生成方法：

| 条目类型 | 调用 Step |
|---------|----------|
| 角色 | Step 5 |
| 设定 | Step 3 |
| 旧版视角候选 | 用户选定后并入 `style_instructions` |
| 关系 | Step 6 |
| 场景 | Step 7 |

Agent 应参考对应 Step 的指令模板执行生成，确保格式一致。

**注意**：必须原样提取内容，不能简化或概括。如遇不确定内容，必须询问用户。
```

**信息丢失处理**：

| 丢失信息 | 恢复方案 |
|---------|---------|
| 维度 id | Agent 根据 name 推断 |
| 维度 description | Agent 推断或留空 |
| 阶段名称（stages） | 用户补充 |
| 场景 state | 从开场消息 `<UpdateVariable>` 的 `/世界`、`/人物`、`/物品`、`/地点`、`/事件` 快照反推 |
| narrator.example_dialogue | 从 description 提取或留空 |
| entry_types 配置 | 使用默认值 |

---

### Step 2: 章节概述

> 有原著全文时执行。无原著时跳至 Step 3，由 Agent 根据用户提供的设定直接创作。

**目标**：逐章生成事实性概述，作为后续所有提取步骤的索引。

**输出**：`literature/original/章节概述.md`

**指令模板**：

```markdown
请阅读 literature/original/ 下的原著文本，生成章节概述。

**输出文件**：literature/original/章节概述.md

**格式**：
## 第X章 {章节标题}
{角色}在{地点}{做了什么}，{结果/后果}。

**要求**：
- 每章1-2句，只陈述事实
- 记录：出场角色、地点、关键事件、关系变化、重要对话的结论
- 禁止使用"暗示""似乎""可能""隐含"等模糊表达
- 多条主线交织时分条列出
```

### Step 3: 设定总集

**目标**：整理世界观、机制、角色总览等事实。有原著时从概述+原文提取，无原著时根据用户设定创作。

**输出**：`literature/fanfic/设定总集.txt`

**格式要求**：使用 `【标题】（关键词1,关键词2）` 格式，每个条目被脚本解析为独立的世界书条目。

**指令模板**：

```markdown
请生成设定总集。

**参考**：
- 章节概述：literature/original/章节概述.md（如有）
- 原著文本：literature/original/（如有）
- 用户补充：{额外设定}

**输出文件**：literature/fanfic/设定总集.txt

**常驻条目**（标题前加 ★ 表示常驻上下文，脚本忽略关键词强制注入）：
★【世界公理】（背景,历史）
★【核心机制】（机制,规则）

常驻条目只保留缺失后会破坏世界逻辑的短规则。角色总览、历史细节和氛围说明不要常驻。

**按需条目**（关键词触发，关键词必须是叙述文本中可能出现的具体词）：
【{势力名}】（{势力名},{代称}）
【{地点名}】（{地点名},{别称}）
【{物品/概念}】（{名称},{相关词}）

**程序化生成条目**（仅当策划蓝图定义了对应生成器）：
【生成规则·{对象类型}】（{正文中会出现的对象类型词},{相关场景词}）
输入：{当前地点、内容层、主角能力、已有实体}
组合轴：{身份、目标、资源、危险、规模}
硬约束：{地理可达、能力匹配、知识边界、风险与收益对称}
持久化：{生成后写入人物/物品/地点/事件的哪些字段}
去重与失效：{如何避免重名，何时移除}

程序化生成规则描述“如何产生受约束实例”，不预写实例结果。只有缺少现成实体且当前场景确实需要时才使用；不得为了展示生成器而强行插入遭遇。

**互斥内容层**：公共条目继续放在 `setting.source_files`；各层放入独立子目录并配置到 `setting.layers`，`active_layer` 只能选择一个。切换层后重新运行生成器并重新导入世界书。生成器不会把未选层写入产物，因此无需再用相反的提示词要求 LLM 自行判断当前层。

> 角色个人档案由 Step 5 独立生成（`literature/characters/{角色名}.md`），脚本自动扫描入库，请勿在此重复写角色条目。本文件专注于势力、地点、物品、专有概念等世界观事实。

**格式**：`【标题】（关键词）` 后跟内容。★ 前缀 = 常驻注入；否则走关键词触发，关键词必须具体（地名/势力名等正文真实出现的词），元词如「世界观/机制」不会被触发。
```

### Step 4: 风格样本（可选，推荐）

**目标**：从原著选取2-3段代表性段落作为续写风格锚点。脚本将其注入角色卡 Description 字段。

**输出**：`example_dialogue_file` 配置的路径（默认 `literature/fanfic/示例对话.txt`）

**指令模板**：

```markdown
请从原著文本中提取风格样本。

**原著文件**：literature/original/{文件名}
**章节概述**：literature/original/章节概述.md（定位代表性段落）

**选段维度**（每维度选1段）：
1. 叙事节奏（句式长短、段落节奏）
2. 对话风格（对话与叙述的比例、引出方式）
3. 描写手法（环境/心理/动作描写特征）

**输出要求**：
- 直接摘录原文，段落间用空行分隔
- 总长度控制在 1500 字以内
```

### Step 5: 角色档案

**目标**：为每个角色生成基础档案（.md）和阶段表现规则（_stages.{json|yaml}）。运行时数值由 MVU 保存，不写回阶段文件。

**输出**：
- `literature/characters/{角色名}.md`
- `literature/characters/{角色名}_stages.{json|yaml}`（格式由 `character_generation.stages_format` 配置决定）

有原著时，按以下流程提取：

1. **线索锚定**：在章节概述中定位角色出现的章节
2. **原文检索**：回到对应章节，提取直接描写（外貌、动作、心理）和间接描写（他人评价）
3. **信息整理**：

| 信息类型 | 提取目标 | 存储位置 | 提取方式 |
|---------|---------|---------|---------|
| 基础信息 | 姓名、年龄、身份 | .md 名称/背景 | 事实陈述 |
| 外貌特征 | 容貌、身材、衣着 | .md 外貌 | 摘录原文短语 |
| 性格特质 | 核心性格、矛盾点 | .md 性格 | 概括 + 原文佐证 |
| 台词风格 | 常用语、语气、口癖 | .md 台词风格 | 摘录典型台词 |
| 称呼习惯 | 自称、对他人的称呼 | .md 称呼习惯 | 摘录具体称呼 |
| 关系网络 | 对各角色的情感 | .md 情感 | 概括 + 关键事件原文 |

> **原文摘录原则**：外貌 / 台词风格 / 称呼习惯 等字段直接使用原作词句（以 「」 标示），不用抽象形容词替代。避免「冷淡疏离」式总结——改为 「"哼，不值一提"」 这样的实例。每字段 1-3 条代表性摘录即可，保持精准简练。

4. **逻辑推理**：根据行为模式判断MBTI、推导性格弱点和变化轨迹
5. **阶段化生成**：基于章节概述中的角色弧线，为每个维度撰写各阶段表现

**指令模板**：

```markdown
请为【{角色名}】生成角色档案。

**参考**：
- 章节概述：literature/original/章节概述.md（如有）
- 原著文本：literature/original/（如有）
- 设定总集：literature/fanfic/设定总集.txt
- 角色线索：{身份、性格、关键关系等补充}

**输出**：
1. literature/characters/{角色名}.md（格式参考附录A）
2. literature/characters/{角色名}_stages.json 或 .yaml（格式参考附录B，由配置决定）

**要求**：
- .md 使用极简键值对格式，不加粗、无列表符号
- **外貌 / 台词风格 / 称呼习惯**：优先以 「」 引用原文短语（短句/词组，单条不超过20字），保留原著用词与语气；禁止用抽象形容词直接替代原文（如「冷淡疏离」应替换为 「"哼，不值一提"」）
- _stages.json 使用标准JSON 或 _stages.yaml 使用标准YAML（按配置选定，不可混用）
- `_stages` 只使用 `character_metrics.id → 阶段名 → 行为描述`，不得重复声明 ranges、角色名或运行时数值
- 阶段名必须与 `state_model.character_metrics.stages` 完全一致；生成器会拒绝缺失或多余阶段
- 阶段内容基于角色在原著中的实际变化轨迹撰写，关键行为尽量原文引证
- 无法确定的信息标注为"未明确"
```

### Step 6: 关系网（可选）

**目标**：生成角色间的关系条目。叙事视角不生成世界书条目；创作者在 Step 0 选择一个固定视角，并在 Step 1 写入 `narrator.style_instructions`。

**输出**：`literature/fanfic/关系网.txt`

**指令模板**：

```markdown
请生成关系网条目。

**参考**：章节概述、设定总集、已生成的角色档案
**输出文件**：literature/fanfic/关系网.txt

**格式**：
【{角色A}与{角色B}的{关系主题}】（{角色A},{角色B},{角色B别名}）
{关系描述与动态表现}

括号内第一个词是主关键词，其余词是 AND ANY 可选过滤键。只有正文同时出现角色A与角色B（或角色B别名）时才注入关系条目，避免只提到一人便加载整段关系资料。
```
### Step 7: 场景剧本

**目标**：创建续写起点。脚本将第一个场景作为 first_mes，其余作为 alternate_greetings。

> ⚠️ 正文将作为 first_mes，LLM 视其为「作者示范」，决定后续回复的句式、长度、视角和场景基调。目标 **500-900字**，过短锚定不足，过长拖累节奏。正文必须与 Step 1 选定的固定叙事视角一致。

**输出**：`literature/scenarios/{序号}_{场景名}.md`

**指令模板**：

```markdown
请为【{场景名}】生成场景剧本。

**参考**：章节概述、原著文本、角色档案、设定总集
**输出文件**：literature/scenarios/{序号}_{场景名}.md

**正文要求**：
- 字数 500-900
- 有原著：摘录对应段落为主干（≥70%），轻度衔接改写
- 无原著：遵循 literature/fanfic/示例对话.txt 的风格
- 结构：前情提要（顶部简述必要的前置剧情背景） → 场景切入 → 角色动作/对话 → 收束于待回应的钩子
- 严格遵循 `narrator.style_instructions` 中选定的固定叙事视角

**state**：这是本开局的完整状态快照。必须同时列出世界、人物、物品、地点、事件五个集合；无数据的集合写 `{}`。人物 `数值` 中只能使用 `character_metrics.id`，不接受中文显示名。生成器会用该快照覆盖基础 `[initvar]`，因此不同开局不会相互污染。

**格式**：
---
name: 场景名称
description: 一句话描述
time: "第一日·黄昏"
location: "{开局地点}"
weather: "小雨"
state:
  世界:
    回合: 0
  人物:
    {角色A}:
      在场: true
      所在地点: "{开局地点}"
      状态: ["正常"]
      当前目标: "{当前目标}"
      关系: "{与主角的关系}"
      数值: {affection: 20, corruption: 0}
      备注: ""
  物品:
    {关键物品}:
      已知: true
      持有者: "{角色A}"
      所在地点: ""
      数量: 1
      状态: "完好"
      描述: "{简短描述}"
      备注: ""
  地点:
    {开局地点}:
      已发现: true
      状态: "正常"
      描述: "{地点描述}"
      备注: ""
  事件:
    {开局事件}:
      状态: "进行中"
      阶段: "起"
      地点: "{开局地点}"
      参与者: ["{角色A}"]
      摘要: "{当前冲突}"
      结果: ""
      备注: ""
---
[前情提要：简述进入本场景前的关键剧情节点，帮助 LLM 理解上下文，3-5 句即可]

[场景正文：场景切入 → 角色动作/对话 → 收束于待回应的钩子]
```

### 按需：修改现有角色

```markdown
请修改【{角色名}】的角色档案：

**修改内容**：{例如：调整某维度的阶段描述}

**操作**：
1. 读取 literature/characters/{角色名}.md
2. 读取 literature/characters/{角色名}_stages.{json|yaml}
3. 执行修改并保存
```

### 3.1 质量控制要点

生成后请检查：
- [ ] 角色设定是否符合原著/同人基调
- [ ] 各维度阶段描述是否呈现梯度变化
- [ ] 阶段内容是否体现角色个性（非通用模板）
- [ ] JSON/YAML格式是否正确（按配置选定，不可混用）
- [ ] XML标签是否正确闭合

---

## 4. 运行脚本与导入

### 4.1 环境准备

```bash
python --version   # Python 3.7+ 必需
pip install pyyaml
```

### 4.2 运行

```bash
cd /path/to/project
python scripts/generate_sillytavern.py
```

脚本自动从 `AGENTS.md` 第2节提取YAML配置。如格式错误将报错提示。

### 4.3 输出文件

| 文件 | 说明 |
|------|------|
| `output/{作品名}世界书.json` | 世界书，包含所有角色、设定、关系网 |
| `output/{作品名}叙事者.json` | 角色卡，叙事者配置 |
| `output/使用指南.md` | 导入说明（自动生成） |

### 4.4 导入 SillyTavern

1. 安装并启用 JS-Slash-Runner / 酒馆助手扩展。
2. World Info → Import World → 选择世界书.json。
3. Characters → Import Character → 选择叙事者.json。
4. 选中叙事者角色 → 设置 → Character Lore → 关联世界书。
5. 不要安装旧版外置“角色状态管理”脚本；角色卡已携带 MVU、ZOD 与悬浮面板。

### 4.5 MVU 数据流

```text
预设场景 state ──→ 首条消息 <UpdateVariable> 完整快照 ─┐
自定义开局 ────→ 首轮根据用户输入创建快照 ─────┘
                                                        ↓
stat_data.{世界,人物,物品,地点,事件}
  → 世界书注入 <status_current_variables>
  → LLM 输出 <StateCheck>（正文前，只读）
  → 正文
  → LLM 输出 <UpdateVariable>（正文后，JSON Patch）
  → MVU 本地解析 + ZOD 校验
  → 悬浮面板订阅最新楼层，分页展示五个集合
```

大块 UI 不在聊天楼层逐条渲染；三条轻量正则隐藏 `<StateCheck>` 和 `<UpdateVariable>`。检查、正文和变量更新共用一次 LLM 调用。

运行时系统条目固定收敛为三条：

| 条目 | 状态 | 职责 |
|---|---|---|
| `[mvu_protocol]生命周期协议` | 常驻 | 开局、前检、正文后更新和输出格式的唯一规则 |
| `[mvu_current]变量列表` | 常驻 | 只提供当前 `stat_data`，不包含行为指令 |
| `[initvar]` | 禁用 | 仅供 MVU 初始化读取，不进入普通提示词 |

叙事视角是创作策划决策，不是 MVU 运行时状态。模板不生成视角世界书条目；选定的固定视角只写入 `style_instructions`。

### 4.6 状态集合预设思路

| 集合 | 解决的问题 | 权威字段 | 不应保存 |
|------|-----------|-----------|-----------|
| 世界 | 当前叙事上下文 | 场景、时间、当前地点、天气、回合 | 所有历史剧情 |
| 人物 | 谁在哪里、正在做什么、以什么阶段表现 | 在场、所在地点、状态、目标、关系、数值 | 完整人设和长期传记 |
| 物品 | 物品是否已知、归谁、剩余多少 | 持有者、所在地点、数量、状态 | 持有者反向背包列表 |
| 地点 | 地点本身是否发现、是否受损或封锁 | 已发现、状态、描述 | 当前人物/物品列表 |
| 事件 | 剧情线是否触发、处于哪个叙事阶段 | 状态、阶段、参与者、摘要、结果 | 每轮正文摘要、与阶段重复的百分比进度 |

预设只追踪“后续回合会用到、且可能变化”的事实。世界书的静态设定和角色档案仍然保存完整资料，不复制到 `stat_data`。

---

## 5. 进阶配置

### 5.1 添加新人物数值

在 `state_model.character_metrics` 列表中添加：

```yaml
state_model:
  character_metrics:
    - id: "new_dim"
      name: "新数值名"
      description: "新数值描述"
      initial: 0
      change:
        minor: [1, 2]
        major: [3, 5]
      ranges: [0, 25, 50, 75, 100]
      stages:
        - "阶段4"    # 75 ≤ x ≤ 100
        - "阶段3"    # 50 ≤ x < 75
        - "阶段2"    # 25 ≤ x < 50
        - "阶段1"    # 0 ≤ x < 25
```

所有已生成的`_stages.{json|yaml}`需要更新以包含新维度。

### 5.2 调整阶段范围

修改`ranges`数组即可：

```yaml
# 三等分
ranges: [0, 33, 66, 100]

# 前期短、后期长
ranges: [0, 20, 50, 100]

# 四阶段
ranges: [0, 25, 50, 75, 100]
```

注意：`stages`数量必须等于`ranges长度-1`。

### 5.3 自定义条目类型

在`entry_types`中添加新类型：

```yaml
entry_types:
  my_custom_type:
    prefix: "自定义_"
    order_start: 400
    order_step: 1
    depth: 4
    position: 0
    constant: false
    ignore_budget: true
```

### 5.4 修改正则解析

更新`character_generation.extract_patterns`中的正则表达式：

| 目标 | 正则模板 |
|------|---------|
| 提取【标题】后内容 | `【标题】\s*(.*?)(?=\n【\|$)` |
| 提取（关键词） | `[（(]([^\)）]+)[）)]` |
| 提取角色段落 | `{name}[^。]*?[^。]*。` |
| 提取引号内台词 | `"([^"]+)"` |

---

## 附录

### A. 示例：角色档案（.md）

```markdown
名称: 示例角色（称号）
性别: 女
MBTI: INFJ（提倡者）
貌龄: 二十五
年龄: 未明确
背景: 某门派核心弟子
性格: 外冷内热 —— 「表面高傲」却「暗藏渴念」
外貌: 「肤若凝脂，眉目如画」，常「一袭素白长裙，腰束青玉带」
台词风格:
  口癖: 「哼，不值一提」
  反诘: 「你以为本座稀罕？」
  语气: 话少字冷，急怒时语速陡快
技能: 未明确
情感: 对主角「又爱又恨」——人前「冷眼相待」，人后「暗中护持」
称呼习惯:
  自称:
    常态: 「我」
    特殊: 「本座」
  对主角:
    私下: 「冤家」
    人前: 「大人」
备注: 未明确
```

### B. 示例：阶段数据（_stages.json 或 _stages.yaml）

**JSON 格式**（`stages_format: "json"`）：

```json
{
  "metrics": {
    "affection": {
      "生死相托": "主动维护主角的利益，愿意承担不可逆代价。",
      "主动亲近": "主动分享信息和寻求共同经历。",
      "初步信任": "愿意合作，但仍保留个人底线。",
      "陌生戒备": "保持距离，只根据可验证行为判断主角。"
    },
    "corruption": {
      "彻底失控": "行为被异化目标主导，难以维持原有底线。",
      "显著异化": "出现稳定异常倾向，但仍能进行有限自控。",
      "稳定": "维持原本人格和行为习惯。"
    }
  }
}
```

**YAML 格式**（`stages_format: "yaml"`）：

```yaml
metrics:
  affection:
    生死相托: "主动维护主角的利益，愿意承担不可逆代价。"
    主动亲近: "主动分享信息和寻求共同经历。"
    初步信任: "愿意合作，但仍保留个人底线。"
    陌生戒备: "保持距离，只根据可验证行为判断主角。"
  corruption:
    彻底失控: "行为被异化目标主导，难以维持原有底线。"
    显著异化: "出现稳定异常倾向，但仍能进行有限自控。"
    稳定: "维持原本人格和行为习惯。"
```

数值边界与阶段顺序只在 `state_model.character_metrics` 定义一次。阶段文件只补充“该角色在这个阶段如何表现”，文件名已经确定角色，不再重复角色名。

### C. 常见错误排查

| 错误 | 原因 | 解决 |
|------|------|------|
| YAML解析失败 | 配置区格式错误 | 检查缩进、冒号后空格、引号匹配 |
| 找不到角色文件 | 目录路径错误 | 检查`character_generation.output_dir` |
| JSON格式错误 | `_stages.json`语法问题 | 使用在线JSON校验器检查 |
| YAML格式错误 | `_stages.yaml`语法问题 | 检查缩进、冒号后空格 |
| 阶段规则不匹配 | `_stages` 重复定义边界或缺少阶段 | 只保留 `metrics → id → 阶段名 → 行为`，阶段名以 `character_metrics` 为准 |
| 世界书导入失败 | JSON结构错误 | 检查`entry_types`配置是否完整 |
| 角色卡无响应 | system_prompt格式问题 | 检查`narrator.persona`换行符 |

---

**提示**：修改配置后务必重新运行脚本，变更才会生效。
