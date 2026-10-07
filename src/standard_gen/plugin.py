from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from .generate import DEFAULT_BUILD_DIR, DEFAULT_STANDARDS_FILE, generate, load_standards

logger = logging.getLogger(__name__)

_CONFIG_KEYS = ('standards-file', 'build-dir', 'only', 'extra-registers')


class SpecgenBuildPlugin:
    """bblocks-postprocess build (lifecycle-hook) plugin wrapper around
    standard_gen.generate.generate().

    Declare in the consumer repo's bblocks-config.yaml (all config keys are
    optional; the values shown are the defaults):

        plugins:
          build:
            - classes: [standard_gen.plugin.SpecgenBuildPlugin]
              pip: [bblocks-specgen @ git+https://github.com/opengeospatial/bblocks-specgen]
              config:
                standards-file: standards.yaml   # relative to the repo root
                build-dir: standards             # relative to the repo root, or absolute
                only: []                         # standard ids to generate (default: all)
                extra-registers: []              # register.json URLs/paths to import

    Needs a bblocks-postprocess release that passes a build plugin entry's
    `config` to the constructor (v1.1.8 or later).

    Runs at after_run - once, only on a successful postprocess run, after
    uplift (and the optional SPARQL push) - with the final register.json
    content and the run's context. The standards definitions are read from
    standards-file (see generate.load_standards()), not from the register.
    Each standard is written to <build-dir>/<id>/, with an index of all of
    them at <build-dir>/index.html.
    """

    def __init__(self, config: Optional[dict] = None):
        config = config or {}
        if not isinstance(config, dict):
            raise TypeError(f"SpecgenBuildPlugin config must be a mapping, got {type(config).__name__}")
        unknown = sorted(set(config) - set(_CONFIG_KEYS))
        if unknown:
            raise ValueError(
                f"Unknown SpecgenBuildPlugin config key(s): {unknown} (valid: {list(_CONFIG_KEYS)})"
            )
        self._standards_file = self._str(config, 'standards-file', DEFAULT_STANDARDS_FILE)
        self._build_dir = self._str(config, 'build-dir', DEFAULT_BUILD_DIR)
        self._only = self._str_list(config, 'only')
        self._extra_registers = self._str_list(config, 'extra-registers')

    @staticmethod
    def _str(config: dict, key: str, default: str) -> str:
        value = config.get(key, default)
        if not isinstance(value, str) or not value:
            raise TypeError(f"SpecgenBuildPlugin config '{key}' must be a non-empty string")
        return value

    @staticmethod
    def _str_list(config: dict, key: str) -> list[str]:
        value = config.get(key) or []
        if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
            raise TypeError(f"SpecgenBuildPlugin config '{key}' must be a list of strings")
        return value

    def after_run(self, register: dict, context: dict) -> None:
        root_dir = Path(context['rootDir'])

        standards = load_standards(root_dir / self._standards_file)
        extra_registers = [self._load_extra_register(ref, root_dir) for ref in self._extra_registers]

        out = generate(
            register,
            standards,
            source_dir=root_dir,
            build_dir=root_dir / self._build_dir,  # an absolute build-dir wins
            only=self._only,
            extra_registers=extra_registers,
        )
        logger.info("Generated standards index: %s", out)

    @staticmethod
    def _load_extra_register(ref: str, root_dir: Path) -> dict:
        if ref.startswith('http://') or ref.startswith('https://'):
            import requests
            resp = requests.get(ref, timeout=30)
            resp.raise_for_status()
            return resp.json()
        path = Path(ref)
        if not path.is_absolute():
            path = root_dir / path
        return json.loads(path.read_text(encoding='utf-8'))
