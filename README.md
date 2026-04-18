# SillyTavern 同人小说世界书模板

基于角色状态系统，自动生成 SillyTavern 兼容的世界书（Lorebook）和叙事者角色卡。

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
2. 编辑 `AGENTS.md` 第 2 节配置区，填入你的作品信息
3. 在 `literature/` 下创建角色档案、场景剧本等素材文件
4. 运行生成脚本：
   ```bash
   python scripts/generate_sillytavern.py
   ```
5. 将 `output/` 下生成的 JSON 文件导入 SillyTavern

### 启用角色状态管理（推荐）

`_stages.json` 仅声明状态结构——要让变量**自动计算**与**阶段内容按区间裁剪**真正生效，需要在 SillyTavern 内安装运行时：

1. **安装 JS-Slash-Runner 扩展**
   - 在 SillyTavern「扩展」→「安装扩展」中填入：
     ```
     https://github.com/n0vi028/JS-Slash-Runner
     ```
   - 安装后启用扩展。

2. **导入角色状态管理脚本**
   - 打开 JS-Slash-Runner 扩展面板 →「脚本管理」→「新建脚本」
   - 脚本内容填入（仅此一行）：
     ```javascript
     import 'https://testingcf.jsdelivr.net/gh/WZzhaoyi/tavern_helper/dist/角色状态管理/index.js'
     ```
   - 保存并启用该脚本。

启用后，LLM 回复末尾输出的 `_.set(...)` 指令会被自动执行，`<character_states>` 块内的阶段内容会依据当前数值动态裁剪注入。未安装扩展时，世界书和角色卡仍可正常使用，但状态数值和阶段切换需手动维护。

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
