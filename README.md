# SillyTavern 多作品世界书模板

共享一套指南、生成器和 MVU 面板，每部作品独立保存配置、素材与产物。

```bash
pip install -r requirements.txt
mkdir -p works/我的作品/literature/{characters,scenarios,fanfic,original,vocab}
cp works/示例作品/config.yaml works/我的作品/config.yaml
# 编辑本作配置并补齐素材后：
python scripts/generate_sillytavern.py --work works/我的作品
```

完整的策划、素材格式、旧卡恢复、配置迁移、导入说明和可选通用能力统一见 [AGENTS.md](AGENTS.md)。空白配置骨架见 [示例作品/config.yaml](works/示例作品/config.yaml)。

运行测试：`python -m unittest discover -s tests`。

[MIT License](LICENSE)
