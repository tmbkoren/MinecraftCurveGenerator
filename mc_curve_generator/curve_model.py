"""
Manages the state of the Bézier curve, including control points and history.
"""
from typing import List, Optional
from PySide6.QtCore import QLineF

from .control_point import ControlPoint


class CurveModel:
    """
    Manages the data and state of the curve, including control points,
    undo/redo history, and geometric calculations.
    """

    def __init__(self):
        self.control_points: List[ControlPoint] = []
        self.selected_point_index: Optional[int] = None
        self.undo_stack: List[List[ControlPoint]] = []
        self.redo_stack: List[List[ControlPoint]] = []
        self._save_state_for_undo()

    def _save_state_for_undo(self):
        """Saves the current state of control points for undo functionality."""
        self.undo_stack.append([pt.clone() for pt in self.control_points])
        self.redo_stack.clear()
        if len(self.undo_stack) > 50:
            self.undo_stack.pop(0)

    def undo(self):
        """Reverts to the previous state in the undo stack."""
        if len(self.undo_stack) > 1:
            self.redo_stack.append(self.undo_stack.pop())
            self._restore_state(self.undo_stack[-1])

    def redo(self):
        """Re-applies a state from the redo stack."""
        if self.redo_stack:
            state = self.redo_stack.pop()
            self.undo_stack.append(state)
            self._restore_state(state)

    def _restore_state(self, state: List[ControlPoint]):
        """Restores the control points to a given state."""
        self.control_points = [pt.clone() for pt in state]
        self.selected_point_index = None

    def clear_points(self):
        """Removes all control points."""
        self.control_points.clear()
        self.selected_point_index = None
        self._save_state_for_undo()

    def _cubic_bezier(self, p0, p1, p2, p3, t):
        u = 1 - t
        return u**3 * p0 + 3 * u**2 * t * p1 + 3 * u * t**2 * p2 + t**3 * p3

    def _adaptive_steps(self, p0, p1, p2, p3):
        length = QLineF(p0, p1).length() + QLineF(p1, p2).length() + QLineF(p2, p3).length()
        return max(20, int(length / 2))
