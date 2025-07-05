# Top control panel widget with sliders, buttons, and labels.

from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QSlider, QPushButton, QCheckBox, QSizePolicy
)
from PySide6.QtCore import Qt


class ControlPanel(QFrame):
    """
    The top control panel containing all the interactive widgets
    for controlling the curve and application settings.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background-color: #333; color: white; padding: 5px;")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        layout = QHBoxLayout(self)

        self.width_label = QLabel("Width: 3 blocks")
        self.width_slider = QSlider(Qt.Orientation.Horizontal)
        self.width_slider.setRange(1, 25)
        self.width_slider.setValue(3)
        self.width_slider.setFixedWidth(150)

        self.zoom_label = QLabel("Zoom: 10x")
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(2, 40)
        self.zoom_slider.setValue(10)
        self.zoom_slider.setFixedWidth(150)

        self.tangent_button = QPushButton("Hide Tangents")
        self.tangent_button.setCheckable(True)
        self.tangent_button.setFixedWidth(120)

        self.import_button = QPushButton("Import")
        self.import_button.setFixedWidth(120)

        self.export_button = QPushButton("Export")
        self.export_button.setFixedWidth(120)

        self.lock_checkbox = QCheckBox("Lock Track")

        self.block_count_label = QLabel("Blocks: 0")

        instructions = QLabel(
            "Click empty space to extend path, Click on curve to insert point | Drag to move | Shift-Drag to fix tangents\n"
            "Shortcuts: S=Save | C=Clear | M=Toggle Mirror | Mid-Click=Delete | Ctrl+Z=Undo | Ctrl+Y=Redo"
        )
        instructions.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(self.width_label)
        layout.addWidget(self.width_slider)
        layout.addSpacing(20)
        layout.addWidget(self.zoom_label)
        layout.addWidget(self.zoom_slider)
        layout.addSpacing(20)
        layout.addWidget(self.tangent_button)
        layout.addSpacing(20)
        layout.addWidget(self.import_button)
        layout.addWidget(self.export_button)
        layout.addSpacing(20)
        layout.addWidget(self.lock_checkbox)
        layout.addSpacing(20)
        layout.addWidget(self.block_count_label)
        layout.addStretch()
        layout.addWidget(instructions)
        layout.addStretch()