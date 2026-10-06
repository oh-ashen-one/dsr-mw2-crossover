"""Machine-specific inputs, never account data; no writes or launches on import."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(root=ROOT):
    file = root / 'local-config.json'
    if not file.exists():
        return {}
    if file.is_symlink():
        raise ValueError('Local configuration must be a physical file')
    result = json.loads(file.read_text())
    if not isinstance(result, dict) or result.get('version') != 1:
        raise ValueError('Unsupported local configuration')
    return result


def path(key, default):
    value = read().get(key, str(default))
    if not isinstance(value, str) or not value:
        raise ValueError('Invalid configured path: ' + key)
    result = Path(value).expanduser()
    if not result.is_absolute():
        result = ROOT / result
    return result.resolve()


def require_permission(name):
    # These are local setup decisions, never inherited from the author.
    if read().get(name) is not True:
        raise RuntimeError('Local authorization missing: ' + name + '; see SKILL.md')
