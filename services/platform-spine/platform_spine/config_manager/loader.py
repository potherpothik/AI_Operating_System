import os
from pathlib import Path
import yaml


class ConfigLoader:
    """
    Layered resolution, lowest to highest precedence:
      1. defaults (YAML files in this directory, one per service)
      2. environment variables, PLATFORM_{SERVICE}_{KEY} format
      3. runtime overrides passed explicitly to resolve()

    Persisted runtime overrides (via the API, stored in ConfigOverride)
    are applied by the caller (config_manager/api.py) on top of this,
    since only the API layer knows which overrides are approved vs.
    still pending.
    """

    def __init__(self, config_dir: str = None):
        self.config_dir = Path(config_dir or Path(__file__).parent / "files")
        self._defaults: dict = {}
        self._load_defaults()

    def _load_defaults(self):
        self._defaults = {}
        for f in sorted(self.config_dir.glob("*.yaml")):
            data = yaml.safe_load(f.read_text()) or {}
            service = f.stem
            self._defaults[service] = data

    def resolve(self, service: str, overrides: dict = None) -> dict:
        result = dict(self._defaults.get(service, {}))

        prefix = f"PLATFORM_{service.upper()}_"
        for env_key, env_val in os.environ.items():
            if env_key.startswith(prefix):
                config_key = env_key[len(prefix):].lower()
                result[config_key] = env_val

        if overrides:
            result.update(overrides)

        return result

    def reload(self):
        self._load_defaults()
