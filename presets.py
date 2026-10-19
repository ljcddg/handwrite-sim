"""Preset serialization for handwrite simulation parameters.

Presets are stored as JSON (version 2), where every parameter is stored
under its own name so that a malformed file can never silently shift values
into the wrong fields. For backward compatibility the legacy 18-line
plain-text format is still readable on load.

Notes
-----
- Legacy format: one value per line, in the order of ``PARAM_KEYS``.
- Presets can also be persisted inside the project ``presets`` directory
  (one JSON file per preset), plus a hidden session file that keeps the
  last-used parameters and draft text.

"""

import json
import os

#: Current preset format version.
PRESET_VERSION = 2

#: Parameter keys, in the legacy 18-line preset order.
PARAM_KEYS = [
    "red", "green", "blue",
    "font", "background",
    "word_spacing", "word_spacing_sigma",
    "line_spacing", "line_spacing_sigma",
    "font_size", "font_size_sigma",
    "perturb_x_sigma", "perturb_y_sigma", "perturb_theta_sigma",
    "top_margin", "left_margin", "right_margin", "bottom_margin",
]

#: Parameters stored as strings (file paths).
STR_KEYS = ("font", "background")

#: Parameters stored as floats.
FLOAT_KEYS = ("perturb_theta_sigma",)


def save_preset(path, params):
    """Save parameters to a JSON preset file.

    Parameters
    ----------
    path : str
        Destination file path (parent directories are created).
    params : dict
        Parameter dictionary; only keys of ``PARAM_KEYS`` are persisted.
    """
    data = {
        "version": PRESET_VERSION,
        "params": {key: params[key] for key in PARAM_KEYS},
    }
    _write_json(path, data)


def load_preset(path):
    """Load a preset file in either JSON or legacy 18-line format.

    Parameters
    ----------
    path : str
        Preset file path.

    Returns
    -------
    dict
        Parameter dictionary containing every key of ``PARAM_KEYS``.

    Raises
    ------
    ValueError
        If the file does not match any supported format.
    """
    with open(path, "r", encoding="utf-8") as file:
        content = file.read()
    if content.lstrip().startswith("{"):
        return _from_json(content)
    return _from_legacy(content)


def _from_json(content):
    """Parse a JSON preset."""
    try:
        data = json.loads(content)
    except ValueError as exc:
        raise ValueError("预设文件不是有效的 JSON：%s" % exc)
    if not isinstance(data, dict):
        raise ValueError("预设文件格式不正确（顶层应为对象）")
    params = data.get("params", data)
    if not isinstance(params, dict):
        raise ValueError("预设文件缺少 params 字段")
    return _coerce(params)


def _from_legacy(content):
    """Parse the legacy 18-line plain-text preset."""
    lines = [line.strip() for line in content.splitlines()]
    lines = [line for line in lines if line]
    if len(lines) < len(PARAM_KEYS):
        raise ValueError(
            "旧版预设需要 %d 行参数，当前只有 %d 行" % (len(PARAM_KEYS), len(lines))
        )
    return _coerce(dict(zip(PARAM_KEYS, lines)))


def _coerce(params):
    """Validate and type-coerce a raw parameter mapping."""
    result = {}
    for key in PARAM_KEYS:
        if key not in params:
            raise ValueError("预设缺少参数：%s" % key)
        value = params[key]
        try:
            if key in STR_KEYS:
                result[key] = str(value)
            elif key in FLOAT_KEYS:
                result[key] = float(value)
            else:
                result[key] = int(value)
        except (TypeError, ValueError):
            raise ValueError("参数 %s 的值无效：%r" % (key, value))
    return result


def list_presets(presets_dir, exclude=()):
    """List JSON preset files inside a directory.

    Parameters
    ----------
    presets_dir : str
        Directory holding preset files.
    exclude : iterable of str, optional
        File names to skip (for example the hidden session file).

    Returns
    -------
    list of dict
        One entry per preset with keys ``name`` (file name without the
        ``.json`` extension) and ``path``.
    """
    result = []
    if not os.path.isdir(presets_dir):
        return result
    for name in sorted(os.listdir(presets_dir)):
        if not name.lower().endswith(".json") or name in exclude:
            continue
        path = os.path.join(presets_dir, name)
        if os.path.isfile(path):
            result.append({"name": os.path.splitext(name)[0], "path": path})
    return result


def save_session(path, params, text):
    """Persist the working session (parameters and draft text).

    Parameters
    ----------
    path : str
        Session file path.
    params : dict
        Parameter dictionary, see ``PARAM_KEYS``.
    text : str
        Draft text of the pending text editor.
    """
    data = {
        "version": PRESET_VERSION,
        "params": {key: params[key] for key in PARAM_KEYS},
        "text": text,
    }
    _write_json(path, data)


def load_session(path):
    """Load a working session saved by :func:`save_session`.

    Parameters
    ----------
    path : str
        Session file path.

    Returns
    -------
    tuple
        ``(params, text)``; both are falsy (``None``/``""``) when the file
        is missing or unreadable.
    """
    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
        params = _coerce(data.get("params", {}))
        return params, str(data.get("text", ""))
    except (OSError, ValueError):
        return None, ""


def _write_json(path, data):
    """Write JSON data, creating parent directories when needed."""
    parent = os.path.dirname(os.path.abspath(path))
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
