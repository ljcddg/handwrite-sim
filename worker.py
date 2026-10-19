"""Background generation worker built on top of handright.

The worker builds the template and renders pages in a separate thread so
the UI stays responsive during generation. Two modes are supported:

- ``preview``: render only the first page, exploiting the fact that
  ``handright.handwrite`` returns a lazy generator.
- ``export``: render all pages and save them as PNG files.

Notes
-----
- Results and errors are reported to the UI thread via Qt signals.

"""

import os

from PySide6.QtCore import QThread, Signal
from PIL import Image, ImageFont
from handright import Template, handwrite


class GenerationWorker(QThread):
    """Worker thread that renders handwriting images via handright."""

    #: Emitted with a human-readable progress message.
    progress = Signal(str)
    #: Emitted in preview mode with the rendered first page (PIL image).
    preview_ready = Signal(object)
    #: Emitted in export mode with the list of saved file paths.
    export_done = Signal(list)
    #: Emitted with an error message when generation fails.
    failed = Signal(str)

    def __init__(self, mode, text, params, output_dir=None, parent=None):
        """Initialize the worker.

        Parameters
        ----------
        mode : str
            Either ``"preview"`` or ``"export"``.
        text : str
            Text to render.
        params : dict
            Generation parameters, see :func:`build_template`.
        output_dir : str, optional
            Destination directory used in export mode.
        parent : QtCore.QObject, optional
            Owner of the worker object.
        """
        QThread.__init__(self, parent)
        self.mode = mode
        self.text = text
        self.params = params
        self.output_dir = output_dir

    def run(self):
        """Execute the generation task inside the worker thread."""
        try:
            template = build_template(self.params)
            images = handwrite(self.text, template)
            if self.mode == "preview":
                self.preview_ready.emit(next(iter(images)))
            else:
                os.makedirs(self.output_dir, exist_ok=True)
                paths = []
                for index, image in enumerate(images):
                    path = os.path.join(self.output_dir, "%d.png" % (index + 1))
                    image.save(path)
                    paths.append(path)
                    self.progress.emit("正在生成第 %d 页…" % (index + 1))
                self.export_done.emit(paths)
        except Exception as exc:
            message = str(exc).strip()
            self.failed.emit(message or exc.__class__.__name__)


def build_template(params):
    """Build a ``handright.Template`` from a parameter dictionary.

    Parameters
    ----------
    params : dict
        Must contain every key of ``presets.PARAM_KEYS``.

    Returns
    -------
    Template
        Configured template instance describing margins, spacing, font,
        perturbation parameters, and background image.
    """
    background = Image.open(params["background"])
    font = ImageFont.truetype(params["font"], size=int(params["font_size"]))
    return Template(
        background=background,
        font=font,
        line_spacing=int(params["line_spacing"]) + int(params["font_size"]),
        fill=(int(params["red"]), int(params["green"]), int(params["blue"])),
        left_margin=int(params["left_margin"]),
        top_margin=int(params["top_margin"]),
        right_margin=int(params["right_margin"]),
        bottom_margin=int(params["bottom_margin"]),
        word_spacing=int(params["word_spacing"]),
        line_spacing_sigma=int(params["line_spacing_sigma"]),
        font_size_sigma=int(params["font_size_sigma"]),
        word_spacing_sigma=int(params["word_spacing_sigma"]),
        start_chars="“（[<",
        end_chars="，。",
        perturb_x_sigma=int(params["perturb_x_sigma"]),
        perturb_y_sigma=int(params["perturb_y_sigma"]),
        perturb_theta_sigma=float(params["perturb_theta_sigma"]),
    )
