"""
Main application window that brings all UI components together.
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QMessageBox
from PySide6.QtGui import QKeySequence
from PySide6.QtCore import Qt, QTimer, QThread

from .. import __version__
from ..curve_model import CurveModel
from ..file_operations import import_track, export_track
from ..updater import UpdateWorker, show_update_dialog
from .canvas import Canvas
from .control_panel import ControlPanel


class MainWindow(QWidget):
    """
    The main window of the application, which orchestrates the interactions
    between the control panel, the canvas, and the data model.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"Minecraft Ice Road Planner - v{__version__}")
        self.setGeometry(100, 100, 1400, 900)

        self.model = CurveModel()

        self._init_ui()
        self._connect_signals()

        QTimer.singleShot(500, self.check_for_updates)

    def _init_ui(self):
        """Initializes the user interface and layout."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.control_panel = ControlPanel()
        self.canvas = Canvas(self.model)

        main_layout.addWidget(self.control_panel)
        main_layout.addWidget(self.canvas)

    def check_for_updates(self):
        """Checks for updates using a background thread."""
        self.update_thread = QThread()
        self.update_worker = UpdateWorker(__version__)
        self.update_worker.moveToThread(self.update_thread)

        self.update_worker.update_found.connect(self.on_update_found)
        self.update_worker.error_occurred.connect(self.on_update_error)
        self.update_thread.started.connect(self.update_worker.run)
        self.update_thread.finished.connect(self.update_thread.deleteLater)

        self.update_thread.start()

    def on_update_found(self, release_info):
        """Handles the update found signal from the worker thread."""
        show_update_dialog(release_info, self)
        self.update_thread.quit()

    def on_update_error(self, error_message):
        """Handles errors from the worker thread."""
        print(error_message)
        self.update_thread.quit()

    def _connect_signals(self):
        """Connects widget signals to their corresponding slots."""
        self.control_panel.width_slider.valueChanged.connect(self.set_curve_width)
        self.control_panel.zoom_slider.valueChanged.connect(self.set_canvas_zoom)
        self.canvas.zoomChanged.connect(self.control_panel.zoom_slider.setValue)
        self.canvas.blockCountChanged.connect(
            lambda count: self.control_panel.block_count_label.setText(f"Blocks: {count}")
        )

        self.control_panel.tangent_button.clicked.connect(self.toggle_tangents)
        self.control_panel.import_button.clicked.connect(self.import_track)
        self.control_panel.export_button.clicked.connect(self.export_track)
        self.control_panel.lock_checkbox.stateChanged.connect(self.toggle_lock)

    def keyPressEvent(self, event):
        """Handles global keyboard shortcuts."""
        if self.canvas.is_locked:
            return

        if event.key() == Qt.Key.Key_S:
            self.export_track()
        elif event.key() == Qt.Key.Key_O:
            self.import_track()
        elif event.key() == Qt.Key.Key_C:
            self.clear_points()
        elif event.key() == Qt.Key.Key_T:
            self.control_panel.tangent_button.click()
        elif event.key() == Qt.Key.Key_M and self.model.selected_point_index is not None:
            self._toggle_mirror()
        elif event.matches(QKeySequence.StandardKey.Undo):
            self.model.undo()
            self.canvas.update_grid_with_curve()
        elif event.matches(QKeySequence.StandardKey.Redo):
            self.model.redo()
            self.canvas.update_grid_with_curve()

    def set_curve_width(self, value):
        """Sets the width of the curve."""
        if self.canvas.is_locked:
            self.control_panel.width_slider.setValue(self.canvas.curve_width)
            return
        self.canvas.curve_width = value
        self.control_panel.width_label.setText(f"Width: {value} blocks")
        self.canvas.update_grid_with_curve()

    def set_canvas_zoom(self, value):
        """Sets the zoom level of the canvas."""
        self.canvas.set_zoom(value)
        self.control_panel.zoom_label.setText(f"Zoom: {value}x")

    def toggle_tangents(self):
        """Toggles the visibility of tangent handles."""
        self.canvas.show_tangents = not self.canvas.show_tangents
        self.control_panel.tangent_button.setText(
            "Hide Tangents" if self.canvas.show_tangents else "Show Tangents")
        self.canvas.update()

    def clear_points(self):
        """Clears all control points from the curve."""
        if self.canvas.is_locked:
            return
        self.model.clear_points()
        self.canvas.update_grid_with_curve()

    def import_track(self):
        """Imports a track from a file."""
        if self.canvas.is_locked:
            return
        imported_points = import_track(self)
        if imported_points:
            self.model.control_points = imported_points
            self.model._save_state_for_undo()
            self.canvas.update_grid_with_curve()

    def export_track(self):
        """Exports the current track to a file."""
        export_track(self, self.model.control_points)

    def _toggle_mirror(self):
        """Toggles tangent mirroring for the selected point."""
        if self.canvas.is_locked or self.model.selected_point_index is None:
            return
        pt = self.model.control_points[self.model.selected_point_index]
        pt.mirrored = not pt.mirrored
        self.canvas.update()
        self.model._save_state_for_undo()

    def toggle_lock(self, state):
        """Locks or unlocks the canvas."""
        self.canvas.is_locked = state == Qt.CheckState.Checked.value
