"""
Represents a single control point for a Bézier curve.
"""
from PySide6.QtCore import QPointF


class ControlPoint:
    """
    Represents a single control point for a Bézier curve, including its
    position and tangent handles for controlling the curve's shape.
    Uses QPointF for floating-point precision.
    """

    def __init__(self, pos: QPointF):
        """
        Initializes a new ControlPoint.

        Args:
            pos: The position of the control point.
        """
        self.pos = QPointF(pos)
        self.in_tangent = QPointF(-20, 0)
        self.out_tangent = QPointF(20, 0)
        self.mirrored = True

    def clone(self) -> 'ControlPoint':
        """Creates a deep copy of this control point."""
        new_point = ControlPoint(QPointF(self.pos))
        new_point.in_tangent = QPointF(self.in_tangent)
        new_point.out_tangent = QPointF(self.out_tangent)
        new_point.mirrored = self.mirrored
        return new_point
