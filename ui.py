"""Qt UI Layout for Handwrite Simulation.

This module defines the form layout and widget properties for the application
main window using PySide6. The interface is built entirely with Qt layouts
(no absolute positioning), so the window can be resized freely.

Notes
-----
- Widget attribute names mirror the generation parameters they control
  (for example ``word_spacing``), which keeps ``main.py`` a thin mapping
  layer over the UI.
- The dark illustration background of the legacy version is no longer
  required at runtime; a global stylesheet provides the visual theme.

"""

from PySide6 import QtCore, QtWidgets

#: Global stylesheet: a clean modern light theme with a green accent.
STYLESHEET = """
QWidget {
    font-family: "Microsoft YaHei UI", "Segoe UI", "PingFang SC", sans-serif;
    font-size: 10pt;
    color: #2c3e50;
}
#centralwidget { background-color: #f4f6f8; }
#titleLabel { font-size: 15pt; font-weight: bold; }
QGroupBox {
    border: 1px solid #dce1e6;
    border-radius: 8px;
    margin-top: 8px;
    background-color: #ffffff;
    padding: 12px 10px 10px 10px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    padding: 2px 6px;
    color: #34495e;
    font-weight: bold;
}
QPushButton {
    border: 1px solid #c3ccd4;
    border-radius: 6px;
    padding: 5px 14px;
    background-color: #fbfcfd;
}
QPushButton:hover { background-color: #e9eef3; border-color: #a9b6c1; }
QPushButton:pressed { background-color: #dbe3ea; }
QPushButton:disabled { color: #a4aeb6; background-color: #f0f2f4; border-color: #dde2e7; }
#primaryButton { background-color: #27ae60; border-color: #1f8b4d; color: #ffffff; font-weight: bold; }
#primaryButton:hover { background-color: #2ec16c; border-color: #27ae60; }
#primaryButton:disabled { background-color: #a9dfbf; color: #f2fdf8; border-color: #a9dfbf; }
#accentButton { background-color: #2980b9; border-color: #1f618d; color: #ffffff; font-weight: bold; }
#accentButton:hover { background-color: #3498db; border-color: #2980b9; }
#accentButton:disabled { background-color: #aed6f0; color: #f6fbfe; border-color: #aed6f0; }
#previewArea {
    background-color: #eceff3;
    border: 1px solid #d5dbe1;
    border-radius: 8px;
    color: #8a97a3;
    font-size: 11pt;
}
#hintLabel { color: #7f8c9a; }
#infoLabel { color: #8a97a3; }
#advancedToggle { border: none; background: transparent; color: #2471a3; font-weight: bold; text-align: left; }
#advancedPanel { background-color: #ffffff; border: 1px solid #dce1e6; border-radius: 8px; }
QLineEdit, QTextEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    border: 1px solid #c3ccd4;
    border-radius: 6px;
    padding: 3px 6px;
    background-color: #ffffff;
    color: #1b2631;
    selection-background-color: #27ae60;
}
QLineEdit:focus, QTextEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border-color: #27ae60;
}
/* 隐藏上下箭头但保留按钮机制：直接设 NoButtons 会让 Qt 把编辑区算成 1px，数字不可见 */
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {
    width: 0px;
    border: none;
    background: transparent;
}
QComboBox { min-width: 120px; }
QComboBox::drop-down { border: none; width: 18px; }
QScrollArea { border: none; background: transparent; }
QStatusBar { color: #7f8c9a; }
QStatusBar::item { border: none; }
QToolTip { background-color: #ffffff; color: #2c3e50; border: 1px solid #c3ccd4; padding: 4px; }
"""


class ClickableLabel(QtWidgets.QLabel):
    """A QLabel that emits ``clicked`` when the user presses it."""

    #: Emitted on mouse press.
    clicked = QtCore.Signal()

    def mousePressEvent(self, event):
        """Emit ``clicked`` and forward the event to the base class."""
        self.clicked.emit()
        super().mousePressEvent(event)


class Ui_Form(object):
    """Layout builder for the main window.

    All widgets are attached to ``self`` inside :meth:`setupUi` and are
    consumed by :class:`main.mainwindow`.
    """

    def setupUi(self, Form):
        """Build and configure the main form UI.

        Parameters
        ----------
        Form : QtWidgets.QWidget
            The main window to populate with controls.
        """
        Form.setObjectName("Form")
        Form.setWindowTitle("手写模拟")
        Form.resize(1180, 780)
        Form.setMinimumSize(QtCore.QSize(960, 640))
        Form.setStyleSheet(STYLESHEET)

        self.centralwidget = QtWidgets.QWidget(Form)
        self.centralwidget.setObjectName("centralwidget")
        outer_layout = QtWidgets.QVBoxLayout(self.centralwidget)
        outer_layout.setContentsMargins(12, 12, 12, 12)
        outer_layout.setSpacing(8)

        self._build_top_bar(outer_layout)

        # 左右分栏：左侧为预览，右侧为参数
        self.splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        outer_layout.addWidget(self.splitter, 1)

        self._build_preview_panel()
        self._build_params_panel()
        self.splitter.setSizes([640, 500])

        Form.setCentralWidget(self.centralwidget)

        self.status_bar = QtWidgets.QStatusBar(Form)
        self.status_bar.setObjectName("statusBar")
        Form.setStatusBar(self.status_bar)

    # ------------------------------------------------------------------ 顶部工具栏
    def _build_top_bar(self, parent_layout):
        """Build the top toolbar with the title and global actions."""
        layout = QtWidgets.QHBoxLayout()
        self.title_label = QtWidgets.QLabel("手写模拟")
        self.title_label.setObjectName("titleLabel")
        layout.addWidget(self.title_label)
        layout.addStretch(1)

        self.open_output_button = QtWidgets.QPushButton("打开输出目录")
        self.open_output_button.setToolTip("打开最近一次导出的目录")
        self.about_button = QtWidgets.QPushButton("关于")
        layout.addWidget(self.open_output_button)
        layout.addWidget(self.about_button)
        parent_layout.addLayout(layout)

    # ------------------------------------------------------------------ 预览面板
    def _build_preview_panel(self):
        """Build the left preview panel."""
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.preview_area = ClickableLabel()
        self.preview_area.setObjectName("previewArea")
        self.preview_area.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        self.preview_area.setMinimumSize(QtCore.QSize(280, 240))
        self.preview_area.setWordWrap(True)
        self.preview_area.setText("点击「预览」查看渲染效果")
        self.preview_area.setToolTip("渲染后单击可查看大图")
        layout.addWidget(self.preview_area, 1)

        self.page_hint_label = QtWidgets.QLabel("建议先预览一页，确认效果后再导出全部页面")
        self.page_hint_label.setObjectName("hintLabel")
        self.page_hint_label.setWordWrap(True)
        layout.addWidget(self.page_hint_label)

        options = QtWidgets.QHBoxLayout()
        self.auto_preview_checkbox = QtWidgets.QCheckBox("参数变更自动预览")
        self.auto_preview_checkbox.setChecked(True)
        self.auto_preview_checkbox.setToolTip(
            "勾选：调整参数或文本后自动重新渲染（长文档可能卡顿）\n"
            "取消：仅手动点击「预览」时渲染，适合长文档"
        )
        options.addWidget(self.auto_preview_checkbox)
        options.addStretch(1)
        layout.addLayout(options)

        buttons = QtWidgets.QHBoxLayout()
        self.preview_button = QtWidgets.QPushButton("预览")
        self.preview_button.setObjectName("primaryButton")
        self.preview_button.setToolTip("渲染第一页，快速确认效果；随机效果每次不同，可重复点击更换")
        self.export_button = QtWidgets.QPushButton("确认效果并导出")
        self.export_button.setObjectName("accentButton")
        self.export_button.setToolTip("确认预览效果后，导出全部页面到 output 目录")
        buttons.addWidget(self.preview_button, 1)
        buttons.addWidget(self.export_button, 1)
        layout.addLayout(buttons)

        self.splitter.addWidget(panel)

    # ------------------------------------------------------------------ 参数面板
    def _build_params_panel(self):
        """Build the right parameter panel inside a scroll area."""
        panel = QtWidgets.QWidget()
        outer = QtWidgets.QVBoxLayout(panel)
        outer.setContentsMargins(0, 0, 0, 0)

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setMinimumWidth(392)
        content = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(content)
        layout.setContentsMargins(8, 8, 14, 8)
        layout.setSpacing(10)
        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        self._build_preset_group(layout)
        self._build_font_group(layout)
        self._build_background_group(layout)
        self._build_color_group(layout)
        self._build_basic_group(layout)
        self._build_text_group(layout)
        self._build_advanced_group(layout)
        layout.addStretch(1)

        self.splitter.addWidget(panel)

    def _build_preset_group(self, parent_layout):
        """Build the project preset management group."""
        self.preset_group = QtWidgets.QGroupBox("预设")
        layout = QtWidgets.QVBoxLayout(self.preset_group)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        row = QtWidgets.QHBoxLayout()
        self.preset_combo = QtWidgets.QComboBox()
        self.preset_combo.setToolTip("项目 presets 目录下保存的预设，选择即载入")
        row.addWidget(self.preset_combo, 1)
        self.save_preset_button = QtWidgets.QPushButton("保存")
        self.save_preset_button.setToolTip("将当前参数保存到项目 presets 目录")
        self.delete_preset_button = QtWidgets.QPushButton("删除")
        self.delete_preset_button.setEnabled(False)
        self.delete_preset_button.setToolTip("删除当前选中的项目预设")
        row.addWidget(self.save_preset_button)
        row.addWidget(self.delete_preset_button)
        layout.addLayout(row)

        row2 = QtWidgets.QHBoxLayout()
        self.import_preset_button = QtWidgets.QPushButton("导入…")
        self.import_preset_button.setToolTip("从外部文件导入预设到项目 presets 目录")
        self.export_preset_button = QtWidgets.QPushButton("导出…")
        self.export_preset_button.setToolTip("将当前参数导出为外部 JSON 文件")
        row2.addWidget(self.import_preset_button)
        row2.addWidget(self.export_preset_button)
        row2.addStretch(1)
        layout.addLayout(row2)

        parent_layout.addWidget(self.preset_group)

    def _build_font_group(self, parent_layout):
        """Build the font selection and import group."""
        self.font_group = QtWidgets.QGroupBox("字体")
        layout = QtWidgets.QVBoxLayout(self.font_group)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        row = QtWidgets.QHBoxLayout()
        self.font_combo = QtWidgets.QComboBox()
        self.font_combo.setToolTip("从 Fonts 目录选择字体，或导入本地 TTF 文件")
        row.addWidget(self.font_combo, 1)
        self.font_import_button = QtWidgets.QPushButton("导入 TTF")
        self.font_import_button.setToolTip("将本地 TTF/OTF 字体拷贝到 Fonts 目录")
        self.font_delete_button = QtWidgets.QPushButton("删除")
        self.font_delete_button.setEnabled(False)
        self.font_delete_button.setToolTip("从 Fonts 目录删除当前选中的字体")
        row.addWidget(self.font_import_button)
        row.addWidget(self.font_delete_button)
        layout.addLayout(row)

        self.font_info_label = QtWidgets.QLabel("")
        self.font_info_label.setObjectName("infoLabel")
        self.font_info_label.setWordWrap(True)
        layout.addWidget(self.font_info_label)

        parent_layout.addWidget(self.font_group)

    def _build_background_group(self, parent_layout):
        """Build the background image selection group."""
        self.background_group = QtWidgets.QGroupBox("背景")
        layout = QtWidgets.QHBoxLayout(self.background_group)
        layout.setContentsMargins(6, 6, 6, 6)
        self.background = QtWidgets.QLineEdit()
        self.background.setPlaceholderText("选择作为纸张背景的图片")
        self.background.setToolTip("渲染时作为纸张背景的图片（如 A4 扫描件）")
        self.background_browse_button = QtWidgets.QPushButton("浏览…")
        layout.addWidget(self.background, 1)
        layout.addWidget(self.background_browse_button)
        parent_layout.addWidget(self.background_group)

    def _build_color_group(self, parent_layout):
        """Build the ink color selection group."""
        self.color_group = QtWidgets.QGroupBox("文字颜色")
        layout = QtWidgets.QHBoxLayout(self.color_group)
        layout.setContentsMargins(6, 6, 6, 6)
        self.color_button = QtWidgets.QPushButton("选择颜色")
        self.color_button.setToolTip("点击选择墨水颜色")
        self.color_label = QtWidgets.QLabel("R: 0  G: 0  B: 0")
        self.color_label.setObjectName("infoLabel")
        layout.addWidget(self.color_button)
        layout.addWidget(self.color_label)
        layout.addStretch(1)
        parent_layout.addWidget(self.color_group)

    def _build_basic_group(self, parent_layout):
        """Build the basic typography group (one compact row)."""
        self.basic_group = QtWidgets.QGroupBox("基础排版")
        layout = QtWidgets.QHBoxLayout(self.basic_group)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(10)

        self.word_spacing = self._make_spin(
            0, 500, 15, " px", "相邻文字之间的水平间距（像素）", width=68
        )
        self.line_spacing = self._make_spin(
            0, 1000, 150, " px", "在字号之外额外增加的行距（像素）", width=68
        )
        self.font_size = self._make_spin(
            10, 600, 100, " px", "文字基准字号（像素）", width=68
        )

        for text, spin in (
            ("字间距", self.word_spacing),
            ("行距", self.line_spacing),
            ("字号", self.font_size),
        ):
            cell = QtWidgets.QHBoxLayout()
            cell.setSpacing(6)
            cell.addWidget(QtWidgets.QLabel(text))
            cell.addWidget(spin)
            layout.addLayout(cell)
        layout.addStretch(1)

        parent_layout.addWidget(self.basic_group)

    def _build_text_group(self, parent_layout):
        """Build the pending text editor group."""
        self.text_group = QtWidgets.QGroupBox("待处理文本")
        layout = QtWidgets.QVBoxLayout(self.text_group)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)
        self.pending_text = QtWidgets.QTextEdit()
        self.pending_text.setPlaceholderText("在此输入或粘贴要转换为手写效果的文字…")
        self.pending_text.setToolTip("支持任意长度的文字，导出时自动分页")
        self.pending_text.setMinimumHeight(150)
        layout.addWidget(self.pending_text, 1)

        self.text_count_label = QtWidgets.QLabel("当前 0 字")
        self.text_count_label.setObjectName("infoLabel")
        self.text_count_label.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        layout.addWidget(self.text_count_label)

        parent_layout.addWidget(self.text_group)

    def _build_advanced_group(self, parent_layout):
        """Build the collapsible advanced parameter section."""
        self.advanced_toggle = QtWidgets.QPushButton("▷ 展开高级参数（随机扰动 · 页边距）")
        self.advanced_toggle.setObjectName("advancedToggle")
        self.advanced_toggle.setCheckable(True)
        self.advanced_toggle.setToolTip("随机扰动让笔迹更自然，页边距控制版面")
        self.advanced_toggle.toggled.connect(self._on_advanced_toggled)
        parent_layout.addWidget(self.advanced_toggle)

        self.advanced_container = QtWidgets.QWidget()
        self.advanced_container.setObjectName("advancedPanel")
        self.advanced_container.setAttribute(
            QtCore.Qt.WidgetAttribute.WA_StyledBackground, True
        )
        layout = QtWidgets.QVBoxLayout(self.advanced_container)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        self.word_spacing_sigma = self._make_spin(0, 100, 3, " px", "字间距随机扰动幅度，越大越不整齐")
        self.line_spacing_sigma = self._make_spin(0, 100, 6, " px", "行距随机扰动幅度")
        self.font_size_sigma = self._make_spin(0, 100, 20, " px", "字号随机扰动幅度")
        self.perturb_x_sigma = self._make_spin(0, 100, 4, " px", "笔画横向偏移的随机幅度")
        self.perturb_y_sigma = self._make_spin(0, 100, 4, " px", "笔画纵向偏移的随机幅度")
        self.perturb_theta_sigma = self._make_double_spin(
            0.0, 2.0, 0.05, 0.01, " rad", "笔画旋转角度的随机幅度"
        )
        layout.addLayout(self._make_cell_grid((
            ("字间距扰动", self.word_spacing_sigma),
            ("行距扰动", self.line_spacing_sigma),
            ("字号扰动", self.font_size_sigma),
            ("横向偏移", self.perturb_x_sigma),
            ("纵向偏移", self.perturb_y_sigma),
            ("旋转扰动", self.perturb_theta_sigma),
        )))

        section_label = QtWidgets.QLabel("页边距")
        section_label.setObjectName("infoLabel")
        layout.addWidget(section_label)

        self.top_margin = self._make_spin(0, 2000, 100, " px", "纸张上边距（像素）")
        self.left_margin = self._make_spin(0, 2000, 100, " px", "纸张左边距（像素）")
        self.right_margin = self._make_spin(0, 2000, 100, " px", "纸张右边距（像素）")
        self.bottom_margin = self._make_spin(0, 2000, 100, " px", "纸张下边距（像素）")
        layout.addLayout(self._make_cell_grid((
            ("上边距", self.top_margin),
            ("左边距", self.left_margin),
            ("右边距", self.right_margin),
            ("下边距", self.bottom_margin),
        )))

        self.advanced_container.setVisible(False)
        parent_layout.addWidget(self.advanced_container)

    @staticmethod
    def _make_cell_grid(items):
        """Lay out ``(label, widget)`` pairs in a compact two-column grid."""
        grid = QtWidgets.QGridLayout()
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(8)
        for index, (text, widget) in enumerate(items):
            row, col = divmod(index, 2)
            label = QtWidgets.QLabel(text)
            label.setFixedWidth(72)
            label.setAlignment(
                QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter
            )
            cell = QtWidgets.QHBoxLayout()
            cell.setSpacing(6)
            cell.addWidget(label)
            cell.addWidget(widget)
            grid.addLayout(cell, row, col)
        grid.setColumnStretch(2, 1)
        return grid

    def _on_advanced_toggled(self, checked):
        """Toggle advanced parameter visibility."""
        self.advanced_container.setVisible(checked)
        if checked:
            self.advanced_toggle.setText("▽ 收起高级参数")
        else:
            self.advanced_toggle.setText("▷ 展开高级参数（随机扰动 · 页边距）")

    @staticmethod
    def _make_spin(minimum, maximum, value, suffix="", tooltip="", width=84):
        """Create a configured QSpinBox for an integer parameter."""
        spin = QtWidgets.QSpinBox()
        spin.setRange(minimum, maximum)
        spin.setValue(value)
        spin.setSuffix(suffix)
        spin.setAccelerated(True)
        spin.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        # 宽度用代码设置；上下按钮由样式表隐藏（见 STYLESHEET）
        spin.setFixedWidth(width)
        hint = "可直接输入 · 鼠标滚轮 / ↑↓ 键调整"
        spin.setToolTip((tooltip + "\n" + hint) if tooltip else hint)
        return spin

    @staticmethod
    def _make_double_spin(minimum, maximum, value, step, suffix="", tooltip=""):
        """Create a configured QDoubleSpinBox for a float parameter."""
        spin = QtWidgets.QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setValue(value)
        spin.setSingleStep(step)
        spin.setDecimals(2)
        spin.setAccelerated(True)
        spin.setAlignment(QtCore.Qt.AlignmentFlag.AlignCenter)
        spin.setFixedWidth(84)
        if suffix:
            spin.setSuffix(suffix)
        hint = "可直接输入 · 鼠标滚轮 / ↑↓ 键调整"
        spin.setToolTip((tooltip + "\n" + hint) if tooltip else hint)
        return spin
