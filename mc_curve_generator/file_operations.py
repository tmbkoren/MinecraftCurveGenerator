"""
Handles the import and export of track data.
"""
import json
from typing import List
from PySide6.QtWidgets import QFileDialog, QMessageBox
from PySide6.QtCore import QPointF

from .control_point import ControlPoint


def export_track(parent, control_points: List[ControlPoint]):
    """
    Exports the current track data to a file.

    Args:
        parent: The parent widget for dialogs.
        control_points: The list of control points to export.
    """
    if not control_points:
        QMessageBox.warning(parent, "Export Error", "There is nothing to export.")
        return

    path, _ = QFileDialog.getSaveFileName(parent, "Save Track", "", "Minecraft Track (*.mtrack);;All Files (*)")
    if not path:
        return

    data = {
        'control_points': [
            {
                'pos': [p.pos.x(), p.pos.y()],
                'in_tangent': [p.in_tangent.x(), p.in_tangent.y()],
                'out_tangent': [p.out_tangent.x(), p.out_tangent.y()],
                'mirrored': p.mirrored
            } for p in control_points
        ]
    }

    try:
        with open(path, 'w') as f:
            json.dump(data, f, indent=4)
        QMessageBox.information(parent, "Export Successful", f"Track saved to {path}")
    except Exception as e:
        QMessageBox.critical(parent, "Export Error", f"Could not save track: {e}")


def import_track(parent) -> List[ControlPoint]:
    """
    Imports track data from a file.

    Args:
        parent: The parent widget for dialogs.

    Returns:
        A list of ControlPoint objects loaded from the file.
    """
    path, _ = QFileDialog.getOpenFileName(parent, "Open Track", "", "Minecraft Track (*.mtrack);;All Files (*)")
    if not path:
        return []

    try:
        with open(path, 'r') as f:
            data = json.load(f)

        control_points = []
        for p_data in data['control_points']:
            pos = QPointF(*p_data['pos'])
            cp = ControlPoint(pos)
            cp.in_tangent = QPointF(*p_data['in_tangent'])
            cp.out_tangent = QPointF(*p_data['out_tangent'])
            cp.mirrored = p_data['mirrored']
            control_points.append(cp)

        QMessageBox.information(parent, "Import Successful", f"Track loaded from {path}")
        return control_points
    except Exception as e:
        QMessageBox.critical(parent, "Import Error", f"Could not load track: {e}")
        return []
