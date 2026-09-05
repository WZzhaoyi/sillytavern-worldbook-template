"""Build a generic browser QA work: python tests/build_ui_fixture.py /tmp/panel-qa."""
import json
import sys
from pathlib import Path

import yaml
from test_features import feature_config
from scripts.generate_sillytavern import SillyTavernGenerator

root = Path(sys.argv[1])
root.mkdir(parents=True, exist_ok=False)
(root / 'config.yaml').write_text(yaml.safe_dump(feature_config(), allow_unicode=True), encoding='utf-8')
generator = SillyTavernGenerator(str(root))
generator.save_files()
(root / 'initial.json').write_text(json.dumps(generator._build_initial_state(), ensure_ascii=False), encoding='utf-8')
