"""Font library management for the handwrite simulation.

This module scans the project ``Fonts`` directory, imports external TTF/OTF
fonts into it, and reads the real family name of each font file via PIL so
the UI can display meaningful labels instead of raw file names.

Notes
-----
- Only files inside the fonts directory can be deleted, which protects
  arbitrary paths from being removed through the UI.

"""

import os
import shutil

from PIL import ImageFont

#: Supported font file extensions (lower case).
SUPPORTED_EXTENSIONS = (".ttf", ".otf", ".ttc")


def scan_fonts(fonts_dir):
    """Scan a directory for font files.

    Parameters
    ----------
    fonts_dir : str
        Directory to scan.

    Returns
    -------
    list of dict
        One entry per font file with keys ``path`` (absolute path),
        ``file`` (file name) and ``family`` (font family name, falling back
        to the file name when unreadable).
    """
    fonts = []
    if not os.path.isdir(fonts_dir):
        return fonts
    for name in sorted(os.listdir(fonts_dir)):
        path = os.path.join(fonts_dir, name)
        if not os.path.isfile(path):
            continue
        if os.path.splitext(name)[1].lower() not in SUPPORTED_EXTENSIONS:
            continue
        family = read_family(path)
        fonts.append({
            "path": path,
            "file": name,
            "family": family or os.path.splitext(name)[0],
        })
    return fonts


def read_family(path):
    """Read the family name of a font file.

    Parameters
    ----------
    path : str
        Font file path.

    Returns
    -------
    str or None
        Family name, or ``None`` if the file cannot be parsed.
    """
    try:
        font = ImageFont.truetype(path, size=20)
        return font.getname()[0]
    except Exception:
        return None


def import_fonts(paths, fonts_dir):
    """Copy font files into the fonts directory.

    Parameters
    ----------
    paths : iterable of str
        Source font file paths.
    fonts_dir : str
        Destination directory (created if missing).

    Returns
    -------
    list of str
        Destination paths of the imported fonts, in input order.
    """
    os.makedirs(fonts_dir, exist_ok=True)
    imported = []
    for src in paths:
        dst = _unique_path(os.path.join(fonts_dir, os.path.basename(src)))
        shutil.copy2(src, dst)
        imported.append(dst)
    return imported


def delete_font(path, fonts_dir):
    """Delete a font file located inside the fonts directory.

    Parameters
    ----------
    path : str
        Font file to delete.
    fonts_dir : str
        Fonts directory; the file must live inside it.

    Raises
    ------
    ValueError
        If ``path`` is outside ``fonts_dir``.
    """
    real = os.path.realpath(path)
    base = os.path.realpath(fonts_dir)
    if os.path.commonpath([real, base]) != base:
        raise ValueError("只能删除字体目录（%s）内的字体" % fonts_dir)
    if os.path.isfile(real):
        os.remove(real)


def is_inside(path, directory):
    """Check whether a path is located inside a directory.

    Parameters
    ----------
    path : str
        Path to check.
    directory : str
        Base directory.

    Returns
    -------
    bool
        ``True`` when ``path`` is inside ``directory``.
    """
    real = os.path.realpath(path)
    base = os.path.realpath(directory)
    try:
        return os.path.commonpath([real, base]) == base
    except ValueError:
        # 不同盘符（Windows）等情况
        return False


def _unique_path(dst):
    """Return ``dst``, or a suffixed variant when it already exists."""
    if not os.path.exists(dst):
        return dst
    base, ext = os.path.splitext(dst)
    index = 1
    while os.path.exists("%s_%d%s" % (base, index, ext)):
        index += 1
    return "%s_%d%s" % (base, index, ext)
