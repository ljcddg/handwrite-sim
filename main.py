"""Handwrite Simulation GUI Application.

This module provides a PySide6-based GUI that collects parameters and uses
the ``handright`` library to generate handwriting-simulated images.

The rendering runs in a background thread so the UI stays responsive, and a
one-page preview is rendered first: only after the user confirms the effect
is the full document exported to a timestamped directory under ``output/``.

Notes
-----
- This module follows NumPy-style docstrings for functions and methods.
- Resource paths (fonts, output, icon) are resolved relative to the script
  location, with special handling for PyInstaller frozen builds so the
  output directory always lives next to the executable.
- Presets are stored as JSON (see :mod:`presets`) inside the project
  ``presets`` directory; the legacy 18-line text format is still readable.
- The working session (parameters and draft text) is auto-saved to
  ``presets/.last_session.json`` and restored on the next launch.

"""

import math
import os
import shutil
import sys
from datetime import datetime

import fontlib
import presets
from PIL import ImageQt
from PySide6.QtCore import QSettings, Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QColorDialog,
    QDialog,
    QFileDialog,
    QInputDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QScrollArea,
    QVBoxLayout,
)

from ui import Ui_Form
from worker import GenerationWorker

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ORG_NAME = "handwrite"
APP_NAME = "handwrite-sim"


def _ensure_user_dir(name):
    """Return the ``name`` directory next to the executable, seeding it once.

    When frozen with ``--onefile`` the bundled data lives in a temporary
    extraction directory (``sys._MEIPASS``) that disappears on exit. Anything
    the user creates there would be lost, so the first launch copies the
    bundled directory next to the executable and that copy is used from then
    on.

    Parameters
    ----------
    name : str
        Directory name, for example ``"Fonts"`` or ``"presets"``.

    Returns
    -------
    str
        A writable directory path.
    """
    target = os.path.join(os.path.dirname(os.path.abspath(sys.executable)), name)
    if os.path.isdir(target):
        return target
    bundled = os.path.join(getattr(sys, "_MEIPASS", BASE_DIR), name)
    try:
        if os.path.isdir(bundled):
            shutil.copytree(bundled, target)
        else:
            os.makedirs(target, exist_ok=True)
    except OSError:
        # 可执行文件目录不可写（如安装在 Program Files），退回随包目录
        return bundled if os.path.isdir(bundled) else target
    return target


def _resolve_fonts_dir():
    """Resolve the fonts directory for dev and frozen runs.

    Returns
    -------
    str
        Preferred fonts directory; a missing one is returned anyway so the
        import action can create it.
    """
    if getattr(sys, "frozen", False):
        # 打包后使用可执行文件同级的 Fonts，用户导入的字体可持久化
        return _ensure_user_dir("Fonts")
    return os.path.join(BASE_DIR, "Fonts")


def _resolve_output_dir():
    """Resolve the output directory for dev and frozen runs."""
    if getattr(sys, "frozen", False):
        return os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "output")
    return os.path.join(BASE_DIR, "output")


def _resolve_presets_dir():
    """Resolve the project presets directory for dev and frozen runs."""
    if getattr(sys, "frozen", False):
        return _ensure_user_dir("presets")
    return os.path.join(BASE_DIR, "presets")


FONTS_DIR = _resolve_fonts_dir()
OUTPUT_DIR = _resolve_output_dir()
PRESETS_DIR = _resolve_presets_dir()
SESSION_PATH = os.path.join(PRESETS_DIR, ".last_session.json")
ICON_PATH = os.path.join(getattr(sys, "_MEIPASS", BASE_DIR), "assets", "ui", "3d.ico")


class mainwindow(QMainWindow, Ui_Form):
    """Main application window.

    This class wires the UI widgets to font management, the two-step
    preview/export workflow, preset I/O and background generation.

    Attributes
    ----------
    font_color : QColor
        Current ink color.
    """

    def __init__(self):
        """Initialize the main window, wire signals and restore state."""
        QMainWindow.__init__(self)
        self.setupUi(self)
        self.setWindowIcon(QIcon(ICON_PATH))

        self.font_color = QColor(0, 0, 0)
        self._worker = None
        self._previewed = None
        self._preview_pixmap = None
        self._background_pixmap = None
        self._bg_pixmap_cache = {}
        self._last_output_dir = None
        self.settings = QSettings(ORG_NAME, APP_NAME)

        # 参数变更后防抖自动保存会话（参数 + 草稿文本）
        self._autosave_timer = QTimer(self)
        self._autosave_timer.setSingleShot(True)
        self._autosave_timer.setInterval(2000)
        self._autosave_timer.timeout.connect(self._autosave)

        # 参数变更后防抖自动重新预览（左侧实时跟随右侧参数）
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.setInterval(400)
        self._preview_timer.timeout.connect(self._auto_preview)
        self._preview_pending = False
        self._last_render_auto = False

        self._connect_signals()
        self._restore_settings()
        self.refresh_presets()
        self.refresh_fonts()
        self._restore_session()
        self._update_color_button()
        self.update_text_stats()
        self.status_bar.showMessage("就绪")

    # ------------------------------------------------------------------ 初始化
    def _connect_signals(self):
        """Connect UI widgets to their handlers."""
        self.save_preset_button.clicked.connect(self.save_preset_to_project)
        self.delete_preset_button.clicked.connect(self.delete_project_preset)
        self.import_preset_button.clicked.connect(self.import_preset)
        self.export_preset_button.clicked.connect(self.export_preset)
        self.preset_combo.currentIndexChanged.connect(self.on_preset_selected)
        self.about_button.clicked.connect(self.about)
        self.font_import_button.clicked.connect(self.import_fonts)
        self.font_delete_button.clicked.connect(self.delete_font)
        self.background_browse_button.clicked.connect(self.browse_background)
        self.color_button.clicked.connect(self.pick_color)
        self.preview_button.clicked.connect(self.preview)
        self.export_button.clicked.connect(self.export)
        self.open_output_button.clicked.connect(self.open_output)
        self.preview_area.clicked.connect(self.show_large_preview)

        self.pending_text.textChanged.connect(self.update_text_stats)
        self.auto_preview_checkbox.toggled.connect(self._on_auto_preview_toggled)
        self.font_combo.currentIndexChanged.connect(self._update_font_info)
        self.background.textChanged.connect(self._on_background_changed)
        for spin in (
            self.word_spacing, self.word_spacing_sigma,
            self.line_spacing, self.line_spacing_sigma,
            self.font_size, self.font_size_sigma,
            self.perturb_x_sigma, self.perturb_y_sigma, self.perturb_theta_sigma,
            self.top_margin, self.left_margin, self.right_margin, self.bottom_margin,
        ):
            spin.valueChanged.connect(self.on_params_changed)
        self.font_combo.currentIndexChanged.connect(self.on_params_changed)

    def _restore_settings(self):
        """Restore window geometry, splitter state and auto-preview flag."""
        geometry = self.settings.value("geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        state = self.settings.value("splitterState")
        if state is not None:
            self.splitter.restoreState(state)
        self.auto_preview_checkbox.setChecked(
            self.settings.value("autoPreview", True) in (True, "true", "True", 1, "1")
        )

    def _on_auto_preview_toggled(self, checked):
        """Enable or disable automatic re-preview on parameter changes."""
        self.settings.setValue("autoPreview", bool(checked))
        if checked:
            # 打开自动预览时按当前参数立即渲染一次
            self._preview_timer.start()
        else:
            self._preview_timer.stop()
            self._preview_pending = False
            if self._previewed is not None and self._previewed != self.current_params():
                self.page_hint_label.setStyleSheet("color: #b9770e;")
                self.page_hint_label.setText("已关闭自动预览，参数变更后请点击「预览」")

    def _restore_session(self):
        """Restore parameters and draft text from the last session."""
        session_params, session_text = presets.load_session(SESSION_PATH)
        if session_params is not None:
            self._apply_params(session_params)
        if session_text:
            self.pending_text.setPlainText(session_text)

    def closeEvent(self, event):
        """Persist window state and session, then wait for a running worker."""
        self.settings.setValue("geometry", self.saveGeometry())
        self.settings.setValue("splitterState", self.splitter.saveState())
        if self._autosave_timer.isActive():
            self._autosave_timer.stop()
        self._preview_timer.stop()
        self._autosave()
        # 关闭前必须等后台线程真正结束，且不再持有引用，
        # 否则窗口销毁时仍在运行的 QThread 会触发
        # “Destroyed while thread is still running”
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait(10000)
        self._worker = None
        super().closeEvent(event)

    def resizeEvent(self, event):
        """Keep the preview image fitted to the preview area on resize."""
        super().resizeEvent(event)
        self._update_preview_pixmap()

    # ------------------------------------------------------------------ 字体管理
    def refresh_fonts(self, select_path=None):
        """Repopulate the font combo from the fonts directory.

        Parameters
        ----------
        select_path : str, optional
            Font path to select after the refresh.
        """
        self.font_combo.blockSignals(True)
        self.font_combo.clear()
        for entry in fontlib.scan_fonts(FONTS_DIR):
            self.font_combo.addItem(
                "%s（%s）" % (entry["family"], entry["file"]), entry["path"]
            )
        if self.font_combo.count() == 0:
            self.font_combo.addItem("（Fonts 目录为空，请导入 TTF）", "")
        if select_path:
            index = self.font_combo.findData(select_path)
            if index >= 0:
                self.font_combo.setCurrentIndex(index)
        self.font_combo.blockSignals(False)
        self._update_font_info()

    def _update_font_info(self):
        """Show the current font file and enable/disable deletion."""
        path = self.font_combo.currentData(Qt.ItemDataRole.UserRole) or ""
        if not path:
            self.font_info_label.setText("Fonts 目录为空，请点击「导入 TTF」添加字体")
            self.font_delete_button.setEnabled(False)
            return
        self.font_info_label.setText("当前字体文件：%s" % path)
        self.font_delete_button.setEnabled(fontlib.is_inside(path, FONTS_DIR))

    def import_fonts(self):
        """Import local TTF/OTF files into the fonts directory."""
        paths, _ = QFileDialog.getOpenFileNames(
            self, "导入 TTF 字体", "",
            "字体文件 (*.ttf *.TTF *.otf *.OTF *.ttc);;所有文件 (*)"
        )
        if not paths:
            return
        try:
            imported = fontlib.import_fonts(paths, FONTS_DIR)
        except Exception as exc:
            QMessageBox.critical(self, "导入失败", str(exc))
            return
        self.refresh_fonts(select_path=imported[-1])
        self.status_bar.showMessage("已导入 %d 个字体" % len(imported))

    def delete_font(self):
        """Delete the currently selected font from the fonts directory."""
        path = self.font_combo.currentData(Qt.ItemDataRole.UserRole) or ""
        if not path:
            return
        reply = QMessageBox.question(
            self, "删除字体",
            "确定从 Fonts 目录删除字体文件 %s 吗？" % os.path.basename(path),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            fontlib.delete_font(path, FONTS_DIR)
        except Exception as exc:
            QMessageBox.critical(self, "删除失败", str(exc))
            return
        self.refresh_fonts()
        self.on_params_changed()

    # ------------------------------------------------------------------ 参数收集
    def browse_background(self):
        """Pick a background image via a file dialog."""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择背景图片", "",
            "图片文件 (*.png *.jpg *.jpeg *.bmp);;所有文件 (*)"
        )
        if path:
            self.background.setText(path)

    def _on_background_changed(self):
        """Render the newly selected background immediately."""
        self._show_background_preview()
        self.on_params_changed()

    def _show_background_preview(self):
        """Show the selected background image in the preview area."""
        path = self.background.text().strip()
        pixmap = self._load_background_pixmap(path)
        if pixmap is None:
            self._background_pixmap = None
            if self._preview_pixmap is None:
                self.preview_area.clear()
                self.preview_area.setText("点击「预览」渲染第一页查看效果")
            return
        self._background_pixmap = pixmap
        # 显示新背景意味着此前的文字预览已过期
        self._preview_pixmap = None
        self._previewed = None
        self._update_preview_pixmap()
        self.page_hint_label.setStyleSheet("")
        self.page_hint_label.setText("已加载背景：%s · 点击「预览」渲染文字效果" % os.path.basename(path))

    def _load_background_pixmap(self, path):
        """Load a background image as a QPixmap, cached by path."""
        if not path or not os.path.isfile(path):
            return None
        if path not in self._bg_pixmap_cache:
            pixmap = QPixmap(path)
            self._bg_pixmap_cache[path] = None if pixmap.isNull() else pixmap
        return self._bg_pixmap_cache[path]

    def pick_color(self):
        """Pick the ink color via a color dialog."""
        color = QColorDialog.getColor(self.font_color, self, "选择文字颜色")
        if color.isValid():
            self.font_color = color
            self._update_color_button()
            self.on_params_changed()

    def _update_color_button(self):
        """Render the current color on the color button."""
        color = self.font_color
        luminance = 0.299 * color.red() + 0.587 * color.green() + 0.114 * color.blue()
        text_color = "#ffffff" if luminance < 128 else "#1b2631"
        self.color_button.setStyleSheet(
            "background-color: %s; color: %s; border: 1px solid #aab4bc;"
            " border-radius: 6px; padding: 5px 14px; font-weight: bold;"
            % (color.name(), text_color)
        )
        self.color_button.setText("文字颜色  %s" % color.name().upper())
        self.color_label.setText("R: %d  G: %d  B: %d" % (color.red(), color.green(), color.blue()))

    def current_params(self):
        """Collect current UI values into a parameter dictionary.

        Returns
        -------
        dict
            Parameter dictionary with every key of ``presets.PARAM_KEYS``.
        """
        return {
            "red": self.font_color.red(),
            "green": self.font_color.green(),
            "blue": self.font_color.blue(),
            "font": self.font_combo.currentData(Qt.ItemDataRole.UserRole) or "",
            "background": self.background.text().strip(),
            "word_spacing": self.word_spacing.value(),
            "word_spacing_sigma": self.word_spacing_sigma.value(),
            "line_spacing": self.line_spacing.value(),
            "line_spacing_sigma": self.line_spacing_sigma.value(),
            "font_size": self.font_size.value(),
            "font_size_sigma": self.font_size_sigma.value(),
            "perturb_x_sigma": self.perturb_x_sigma.value(),
            "perturb_y_sigma": self.perturb_y_sigma.value(),
            "perturb_theta_sigma": self.perturb_theta_sigma.value(),
            "top_margin": self.top_margin.value(),
            "left_margin": self.left_margin.value(),
            "right_margin": self.right_margin.value(),
            "bottom_margin": self.bottom_margin.value(),
        }

    def check(self):
        """Validate parameters before generation.

        Returns
        -------
        str or None
            An error message when invalid, otherwise ``None``.
        """
        if not self.pending_text.toPlainText().strip():
            return "请先输入要处理的文字"
        params = self.current_params()
        if not params["font"]:
            return "请选择字体，可点击「导入 TTF」添加本地字体"
        if not os.path.isfile(params["font"]):
            return "字体文件不存在：%s" % params["font"]
        if not params["background"]:
            return "请选择背景图片"
        if not os.path.isfile(params["background"]):
            return "背景图片不存在：%s" % params["background"]
        return None

    # ------------------------------------------------------------------ 统计与提示
    def _background_size(self):
        """Return the background image size, cached by path."""
        pixmap = self._load_background_pixmap(self.background.text().strip())
        if pixmap is None:
            return None
        return pixmap.width(), pixmap.height()

    def estimate_pages(self):
        """Estimate the total page count from text length and layout.

        Returns
        -------
        int or None
            Estimated page count, or ``None`` when it cannot be computed.
        """
        text = self.pending_text.toPlainText().strip()
        size = self._background_size()
        if not text or size is None:
            return None
        params = self.current_params()
        width, height = size
        usable_w = width - params["left_margin"] - params["right_margin"]
        usable_h = height - params["top_margin"] - params["bottom_margin"]
        font_size = params["font_size"]
        if usable_w <= 0 or usable_h <= 0 or font_size <= 0:
            return None
        chars_per_line = max(1, usable_w // (font_size + params["word_spacing"]))
        line_height = font_size + params["line_spacing"]
        lines_per_page = max(1, usable_h // line_height)
        per_page = chars_per_line * lines_per_page
        return max(1, math.ceil(len(text) / per_page))

    def update_text_stats(self):
        """Refresh the character count and page estimate label."""
        text = self.pending_text.toPlainText().strip()
        pages = self.estimate_pages()
        if pages is None:
            self.text_count_label.setText("当前 %d 字" % len(text))
        else:
            self.text_count_label.setText("当前 %d 字 · 约 %d 页" % (len(text), pages))
        self._autosave_timer.start()
        if self.auto_preview_checkbox.isChecked():
            self._preview_timer.start()

    def on_params_changed(self):
        """React to parameter edits and schedule an automatic re-preview."""
        changed = self._previewed is not None and self._previewed != self.current_params()
        self.update_text_stats()
        if changed:
            self.page_hint_label.setStyleSheet("color: #b9770e;")
            if self.auto_preview_checkbox.isChecked():
                self.page_hint_label.setText("参数已变更，正在自动重新预览…")
            else:
                self.page_hint_label.setText("参数已变更，请点击「预览」")
        if self.auto_preview_checkbox.isChecked():
            self._preview_timer.start()

    def _auto_preview(self):
        """Re-render the preview automatically when parameters are valid."""
        if self._is_busy():
            # 当前有任务在跑，完成后补一次自动预览
            self._preview_pending = True
            return
        if self.check() is not None:
            return
        self._start_worker("preview", auto=True)

    # ------------------------------------------------------------------ 生成流程
    def preview(self):
        """Render the first page in the background and show it."""
        if self._is_busy():
            return
        self._preview_timer.stop()
        self._preview_pending = False
        error = self.check()
        if error is not None:
            QMessageBox.information(self, "请检查参数", error)
            return
        self._start_worker("preview")

    def export(self):
        """Confirm the effect, then export all pages in the background."""
        if self._is_busy():
            return
        error = self.check()
        if error is not None:
            QMessageBox.information(self, "请检查参数", error)
            return
        if self._previewed is None or self._previewed != self.current_params():
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Icon.Question)
            box.setWindowTitle("确认导出")
            box.setText("尚未预览或参数已变更。\n建议先「预览」一页确认效果，再导出全部页面。")
            preview_button = box.addButton("去预览", QMessageBox.ButtonRole.AcceptRole)
            export_button = box.addButton("仍要导出", QMessageBox.ButtonRole.DestructiveRole)
            box.exec()
            if box.clickedButton() is preview_button:
                self.preview()
                return
            if box.clickedButton() is not export_button:
                return
        output_dir = os.path.join(OUTPUT_DIR, datetime.now().strftime("%Y%m%d-%H%M%S"))
        self._last_output_dir = output_dir
        # 导出前取消挂起的自动预览，避免导出后多跑一次
        self._preview_timer.stop()
        self._preview_pending = False
        self._start_worker("export", output_dir=output_dir)

    def _start_worker(self, mode, output_dir=None, auto=False):
        """Create and start a generation worker.

        Parameters
        ----------
        mode : str
            Either ``"preview"`` or ``"export"``.
        output_dir : str, optional
            Destination directory used in export mode.
        auto : bool, optional
            ``True`` when the render was triggered automatically by a
            parameter change (used for status messages and hints).
        """
        self._last_render_auto = auto
        self._worker = GenerationWorker(
            mode, self.pending_text.toPlainText(), self.current_params(),
            output_dir=output_dir,
        )
        self._worker.preview_ready.connect(self._on_preview_ready)
        self._worker.export_done.connect(self._on_export_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.progress.connect(self.status_bar.showMessage)
        self._worker.finished.connect(self._on_worker_finished)
        self._set_busy(True, auto=auto and mode == "preview")
        self._worker.start()

    def _is_busy(self):
        """Check whether a generation worker is currently running."""
        return self._worker is not None and self._worker.isRunning()

    def _set_busy(self, busy, auto=False):
        """Enable/disable action buttons during generation."""
        self.preview_button.setEnabled(not busy)
        self.export_button.setEnabled(not busy)
        self.export_button.setText("正在生成…" if busy else "确认效果并导出")
        if busy:
            self.status_bar.showMessage("正在自动预览…" if auto else "正在处理，请稍候…")

    def _on_preview_ready(self, image):
        """Display the rendered preview page."""
        self._preview_pixmap = ImageQt.toqpixmap(image.convert("RGBA"))
        self._previewed = self.current_params()
        self._update_preview_pixmap()

        if self._last_render_auto:
            hint = "参数已变更，已自动重新渲染 · 随机效果每次不同，可点击「预览」更换"
        else:
            hint = "已渲染第 1 页预览 · 随机效果每次不同，可再次点击「预览」更换"
        pages = self.estimate_pages()
        if pages is not None:
            hint += " · 全文约 %d 页" % pages
        hint += " · 满意后点「确认效果并导出」"
        self.page_hint_label.setStyleSheet("color: #1e8449;")
        self.page_hint_label.setText(hint)
        self.status_bar.showMessage("预览完成")

    def _update_preview_pixmap(self):
        """Fit the active image (rendered preview or background) into the area."""
        pixmap = self._preview_pixmap or self._background_pixmap
        if pixmap is None:
            return
        width = max(self.preview_area.width() - 16, 50)
        height = max(self.preview_area.height() - 16, 50)
        scaled = pixmap.scaled(
            width, height,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.preview_area.setPixmap(scaled)

    def show_large_preview(self):
        """Open the rendered preview (or background) at full size in a dialog."""
        pixmap = self._preview_pixmap or self._background_pixmap
        if pixmap is None:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("预览大图" if self._preview_pixmap is not None else "背景大图")
        dialog.resize(
            min(pixmap.width() + 40, 1100),
            min(pixmap.height() + 40, 900),
        )
        layout = QVBoxLayout(dialog)
        scroll = QScrollArea(dialog)
        scroll.setWidgetResizable(True)
        label = QLabel()
        label.setPixmap(pixmap)
        scroll.setWidget(label)
        layout.addWidget(scroll)
        dialog.exec()

    def _on_export_done(self, paths):
        """Report export completion and offer to open the output folder."""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Information)
        box.setWindowTitle("导出完成")
        box.setText("已导出 %d 页到：\n%s" % (len(paths), self._last_output_dir or ""))
        open_button = box.addButton("打开输出目录", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("关闭", QMessageBox.ButtonRole.RejectRole)
        box.exec()
        if box.clickedButton() is open_button:
            self.open_output()

    def _on_failed(self, message):
        """Report a generation failure to the user."""
        QMessageBox.critical(self, "生成失败", message)

    def _on_worker_finished(self):
        """Restore the UI state after the worker finishes."""
        self._set_busy(False)
        self.status_bar.showMessage("就绪")
        worker = self._worker
        self._worker = None
        if worker is not None:
            worker.deleteLater()
        self._autosave_timer.start()
        if self._preview_pending:
            # 渲染期间参数又变了，补一次自动预览
            self._preview_pending = False
            self._auto_preview()

    # ------------------------------------------------------------------ 项目预设
    def refresh_presets(self, select_name=None):
        """Repopulate the project preset combo from the presets directory.

        Parameters
        ----------
        select_name : str, optional
            Preset name to select after the refresh.
        """
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        for entry in presets.list_presets(PRESETS_DIR, exclude=(os.path.basename(SESSION_PATH),)):
            self.preset_combo.addItem(entry["name"], entry["path"])
        if self.preset_combo.count() == 0:
            self.preset_combo.addItem("（无预设）", "")
        self.preset_combo.setEnabled(self.preset_combo.count() > 0)
        if select_name:
            index = self.preset_combo.findText(select_name)
            if index >= 0:
                self.preset_combo.setCurrentIndex(index)
        self.preset_combo.blockSignals(False)
        self._update_preset_buttons()

    def _update_preset_buttons(self):
        """Enable deletion only when a real project preset is selected."""
        path = self.preset_combo.currentData(Qt.ItemDataRole.UserRole) or ""
        self.delete_preset_button.setEnabled(bool(path))

    def on_preset_selected(self):
        """Load the project preset currently selected in the combo."""
        path = self.preset_combo.currentData(Qt.ItemDataRole.UserRole) or ""
        if not path:
            return
        try:
            params = presets.load_preset(path)
        except Exception as exc:
            QMessageBox.critical(self, "载入失败", str(exc))
            return
        self._apply_params(params)
        self.status_bar.showMessage("已载入预设：%s" % os.path.basename(path))

    def save_preset_to_project(self):
        """Save the current parameters into the project presets directory."""
        name, ok = QInputDialog.getText(
            self, "保存预设", "预设名称：", text=self.preset_combo.currentText()
        )
        if not ok or not name.strip():
            return
        name = name.strip()
        for bad in '/\\:*?"<>|':
            name = name.replace(bad, "_")
        if not name.lower().endswith(".json"):
            name += ".json"
        try:
            presets.save_preset(os.path.join(PRESETS_DIR, name), self.current_params())
        except Exception as exc:
            QMessageBox.critical(self, "保存失败", str(exc))
            return
        self.refresh_presets(select_name=os.path.splitext(name)[0])
        self.status_bar.showMessage("预设已保存到项目 presets 目录")

    def delete_project_preset(self):
        """Delete the project preset currently selected in the combo."""
        path = self.preset_combo.currentData(Qt.ItemDataRole.UserRole) or ""
        if not path:
            return
        reply = QMessageBox.question(
            self, "删除预设",
            "确定删除项目预设 %s 吗？" % os.path.basename(path),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        try:
            os.remove(path)
        except OSError as exc:
            QMessageBox.critical(self, "删除失败", str(exc))
            return
        self.refresh_presets()
        self.status_bar.showMessage("预设已删除")

    def import_preset(self):
        """Import an external preset file into the project presets directory."""
        path, _ = QFileDialog.getOpenFileName(
            self, "导入预设", "", "预设文件 (*.json *.txt);;所有文件 (*)"
        )
        if not path:
            return
        try:
            params = presets.load_preset(path)
        except Exception as exc:
            QMessageBox.critical(self, "导入失败", str(exc))
            return
        name = os.path.splitext(os.path.basename(path))[0] + ".json"
        dst = os.path.join(PRESETS_DIR, name)
        if os.path.exists(dst):
            reply = QMessageBox.question(
                self, "覆盖确认", "presets 目录已存在 %s，覆盖吗？" % name,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        try:
            presets.save_preset(dst, params)
        except Exception as exc:
            QMessageBox.critical(self, "导入失败", str(exc))
            return
        self.refresh_presets(select_name=os.path.splitext(name)[0])
        self.status_bar.showMessage("预设已导入：%s" % name)

    def export_preset(self):
        """Export the current parameters to an external JSON file."""
        path, _ = QFileDialog.getSaveFileName(self, "导出预设", "", "预设文件 (*.json)")
        if not path:
            return
        if not path.lower().endswith(".json"):
            path += ".json"
        try:
            presets.save_preset(path, self.current_params())
        except Exception as exc:
            QMessageBox.critical(self, "导出失败", str(exc))
            return
        self.status_bar.showMessage("预设已导出：%s" % path)

    def _autosave(self):
        """Persist the working session (parameters and draft text)."""
        try:
            presets.save_session(
                SESSION_PATH, self.current_params(), self.pending_text.toPlainText()
            )
        except Exception:
            pass  # 自动保存失败不影响正常使用

    def _apply_params(self, params):
        """Apply a parameter dictionary to the UI."""
        self.word_spacing.setValue(int(params["word_spacing"]))
        self.word_spacing_sigma.setValue(int(params["word_spacing_sigma"]))
        self.line_spacing.setValue(int(params["line_spacing"]))
        self.line_spacing_sigma.setValue(int(params["line_spacing_sigma"]))
        self.font_size.setValue(int(params["font_size"]))
        self.font_size_sigma.setValue(int(params["font_size_sigma"]))
        self.perturb_x_sigma.setValue(int(params["perturb_x_sigma"]))
        self.perturb_y_sigma.setValue(int(params["perturb_y_sigma"]))
        self.perturb_theta_sigma.setValue(float(params["perturb_theta_sigma"]))
        self.top_margin.setValue(int(params["top_margin"]))
        self.left_margin.setValue(int(params["left_margin"]))
        self.right_margin.setValue(int(params["right_margin"]))
        self.bottom_margin.setValue(int(params["bottom_margin"]))

        self.font_color = QColor(int(params["red"]), int(params["green"]), int(params["blue"]))
        self._update_color_button()

        font_path = self._normalize_path(params["font"])
        index = self.font_combo.findData(font_path)
        if index < 0 and font_path:
            self.font_combo.addItem("%s（外部路径）" % os.path.basename(font_path), font_path)
            index = self.font_combo.findData(font_path)
        if index >= 0:
            self.font_combo.setCurrentIndex(index)

        # 载入后旧预览失效，重置预览状态
        self._previewed = None
        self._preview_pixmap = None
        self.page_hint_label.setStyleSheet("")
        self.page_hint_label.setText("参数已载入，点击「预览」查看效果")
        # 最后设置背景：路径变化时会自动触发背景即时预览渲染
        self.background.setText(self._normalize_path(params["background"]))
        # 路径未变化时不会触发 textChanged，这里显式刷新一次预览区
        if self._background_pixmap is None and self._preview_pixmap is None:
            self.preview_area.clear()
            self.preview_area.setText("点击「预览」渲染第一页查看效果")
        else:
            self._update_preview_pixmap()

    @staticmethod
    def _normalize_path(path):
        """Resolve a preset path against the project directory."""
        path = str(path)
        if path and not os.path.isabs(path):
            candidate = os.path.join(BASE_DIR, path)
            if os.path.exists(candidate):
                return candidate
        return path

    # ------------------------------------------------------------------ 其他
    def open_output(self):
        """Open the output directory in the system file manager."""
        target = self._last_output_dir or OUTPUT_DIR
        os.makedirs(target, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(target))

    def about(self):
        """Show the about dialog."""
        QMessageBox.about(
            self, "关于",
            "<b>手写模拟</b><br><br>"
            "基于 handright 与 PySide6 开发，仅供学习交流。<br>"
            "作者：人走茶凉le（B 站）<br><br>"
            "渲染核心：<a href=\"https://github.com/Gsllchb/Handright\">Handright</a><br>"
            "界面框架：PySide6 (Qt for Python)<br>"
            "许可证：MIT License",
        )


if __name__ == '__main__':
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    ui = mainwindow()  # 创建自定义ui界面
    ui.show()
    sys.exit(app.exec())
