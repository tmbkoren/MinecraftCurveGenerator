"""
Canvas widget for drawing and interacting with the Bézier curve.
"""
import math
from PySide6.QtWidgets import QWidget, QSizePolicy
from PySide6.QtGui import QPainter, QPen, QColor, QMouseEvent, QBrush
from PySide6.QtCore import Qt, QPoint, QPointF, QRect, QLineF, Signal
from typing import Optional

from ..curve_model import CurveModel
from ..control_point import ControlPoint


class Canvas(QWidget):
    """
    The main drawing area for the curve editor.
    Handles all rendering and user interaction with the curve.
    """
    blockCountChanged = Signal(int)
    zoomChanged = Signal(int)
    mouseMoved = Signal(QPoint)
    highlightCountChanged = Signal(int)

    def __init__(self, model: CurveModel, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self.model = model
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)

        # --- View Settings ---
        self.view_offset = QPointF(500, 500)
        self.zoom = 10
        self.min_zoom, self.max_zoom = 2, 40
        self.panning = False
        self.last_pan_pos = QPointF()

        # --- Display Settings ---
        self.grid_blocks = set()
        self.highlighted_blocks = set()
        self.curve_width = 3
        self.handle_radius = 6
        self.show_tangents = True
        self.dragging_object = None
        self.is_locked = False

        # --- Drag State ---
        self.drag_start_in_tangent_abs = None
        self.drag_start_out_tangent_abs = None

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.fillRect(self.rect(), QColor("#282c34"))
            self._draw_track_blocks(painter)
            self._draw_highlighted_blocks(painter)
            self._draw_grid_lines(painter)
            self._draw_curve(painter)
            self._draw_control_points(painter)
        finally:
            painter.end()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.RightButton:
            self.panning = True
            self.last_pan_pos = event.pos()
            return

        if self.is_locked:
            if event.button() == Qt.MouseButton.LeftButton:
                self._toggle_highlight(event.pos())
            return

        if event.button() == Qt.MouseButton.MiddleButton:
            self._delete_point_at(event.pos())
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return

        for i, pt in reversed(list(enumerate(self.model.control_points))):
            screen_center = self.grid_to_screen(pt.pos)
            in_handle_pos = screen_center + pt.in_tangent * self.zoom
            out_handle_pos = screen_center + pt.out_tangent * self.zoom

            if self.show_tangents and (in_handle_pos - event.pos()).manhattanLength() < self.handle_radius * 2:
                self.dragging_object = ('in_handle', i)
                self._start_drag(i)
                return
            if self.show_tangents and (out_handle_pos - event.pos()).manhattanLength() < self.handle_radius * 2:
                self.dragging_object = ('out_handle', i)
                self._start_drag(i)
                return
            if (screen_center - event.pos()).manhattanLength() < self.handle_radius * 2:
                self.dragging_object = ('point', i)
                self._start_drag(i)
                return

        dist, segment_idx, t = self._find_closest_segment(event.pos())
        click_on_curve_threshold = self.curve_width * self.zoom / 2 + 5

        if segment_idx is not None and dist < click_on_curve_threshold:
            self._split_curve_segment(segment_idx, t)
        else:
            self._add_point(event.pos())

        self.update_grid_with_curve()
        self.update()
        self.model._save_state_for_undo()

    def _start_drag(self, point_index):
        if self.is_locked:
            return
        self.model.selected_point_index = point_index
        point = self.model.control_points[point_index]
        self.drag_start_in_tangent_abs = point.pos + point.in_tangent
        self.drag_start_out_tangent_abs = point.pos + point.out_tangent
        self.model._save_state_for_undo()
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent):
        grid_pos_float = self.screen_to_grid(event.pos())
        grid_pos_int = QPoint(int(grid_pos_float.x()), int(grid_pos_float.y()))
        self.mouseMoved.emit(grid_pos_int)

        if self.panning:
            delta = QPointF(event.pos()) - self.last_pan_pos
            self.view_offset -= delta * (1.0 / self.zoom)
            self.last_pan_pos = event.pos()
            self.update()
            return

        if self.is_locked or not self.dragging_object:
            return

        drag_type, index = self.dragging_object
        pt = self.model.control_points[index]
        grid_pos = self.screen_to_grid(event.pos())
        shift_pressed = event.modifiers() & Qt.KeyboardModifier.ShiftModifier

        if drag_type == 'point':
            pt.pos = grid_pos
            if shift_pressed and self.drag_start_in_tangent_abs and self.drag_start_out_tangent_abs:
                pt.in_tangent = self.drag_start_in_tangent_abs - grid_pos
                pt.out_tangent = self.drag_start_out_tangent_abs - grid_pos
        else:
            screen_center = self.grid_to_screen(pt.pos)
            tangent_vec = (QPointF(event.pos()) - screen_center) * (1.0 / self.zoom)
            if drag_type == 'in_handle':
                pt.in_tangent = tangent_vec
                if pt.mirrored:
                    pt.out_tangent = -tangent_vec
            elif drag_type == 'out_handle':
                pt.out_tangent = tangent_vec
                if pt.mirrored:
                    pt.in_tangent = -tangent_vec

        self.update_grid_with_curve()
        self.update()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.RightButton:
            self.panning = False
        elif event.button() == Qt.MouseButton.LeftButton:
            if self.is_locked:
                return
            self.dragging_object = None

    def wheelEvent(self, event):
        steps = event.angleDelta().y() / 120
        self.set_zoom(self.zoom + steps)

    def _draw_grid_lines(self, painter):
        if self.zoom <= 3:
            return
        painter.setPen(QPen(QColor(60, 60, 60), 1))
        w, h = self.width(), self.height()
        start_x, start_y = -self.view_offset.x() * self.zoom, -self.view_offset.y() * self.zoom
        x_offset, y_offset = start_x % self.zoom, start_y % self.zoom
        for x in range(int(x_offset), w, int(self.zoom)):
            painter.drawLine(x, 0, x, h)
        for y in range(int(y_offset), h, int(self.zoom)):
            painter.drawLine(0, y, w, y)

    def _draw_track_blocks(self, painter):
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#a0e8ff"))
        for pos_tuple in self.grid_blocks:
            rect = self.grid_to_screen_rect(QPointF(*pos_tuple))
            if self.rect().intersects(rect):
                painter.drawRect(rect)

    def _draw_highlighted_blocks(self, painter):
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(255, 0, 0, 100))  # Semi-transparent red
        for pos_tuple in self.highlighted_blocks:
            rect = self.grid_to_screen_rect(QPointF(*pos_tuple))
            if self.rect().intersects(rect):
                painter.drawRect(rect)

    def _draw_curve(self, painter):
        if len(self.model.control_points) < 2:
            return
        painter.setPen(QPen(QColor(255, 255, 255, 150), 2))
        for i in range(len(self.model.control_points) - 1):
            p0, p3 = self.model.control_points[i], self.model.control_points[i+1]
            p1_abs, p2_abs = p0.pos + p0.out_tangent, p3.pos + p3.in_tangent
            steps = self.model._adaptive_steps(p0.pos, p1_abs, p2_abs, p3.pos)
            path_points = [self.grid_to_screen(self.model._cubic_bezier(
                p0.pos, p1_abs, p2_abs, p3.pos, t/steps)) for t in range(steps + 1)]
            for j in range(len(path_points) - 1):
                painter.drawLine(path_points[j], path_points[j + 1])

    def _draw_control_points(self, painter):
        for i, pt in enumerate(self.model.control_points):
            screen_pos = self.grid_to_screen(pt.pos)
            if self.show_tangents:
                in_pt, out_pt = screen_pos + pt.in_tangent * self.zoom, screen_pos + pt.out_tangent * self.zoom
                in_color, out_color = (QColor("#ff5555"), QColor("#ff5555")) if pt.mirrored else (QColor("#55ff55"), QColor("#5555ff"))
                painter.setPen(QPen(in_color, 2))
                painter.setBrush(in_color)
                painter.drawLine(screen_pos, in_pt)
                painter.drawEllipse(in_pt, self.handle_radius, self.handle_radius)
                painter.setPen(QPen(out_color, 2))
                painter.setBrush(out_color)
                painter.drawLine(screen_pos, out_pt)
                painter.drawEllipse(out_pt, self.handle_radius, self.handle_radius)
            is_selected = (i == self.model.selected_point_index)
            painter.setBrush(QColor("yellow") if is_selected else QColor("red"))
            painter.setPen(QPen(QColor("white") if is_selected else QColor("black"), 2))
            painter.drawEllipse(screen_pos, 8 if is_selected else 6, 8 if is_selected else 6)

    def update_grid_with_curve(self):
        self.grid_blocks.clear()
        if len(self.model.control_points) < 2:
            self.blockCountChanged.emit(0)
            self.update()
            return
        points_to_draw = set()
        radius = self.curve_width / 2.0
        for i in range(len(self.model.control_points) - 1):
            p0, p3 = self.model.control_points[i], self.model.control_points[i+1]
            p1_abs, p2_abs = p0.pos + p0.out_tangent, p3.pos + p3.in_tangent
            steps = self.model._adaptive_steps(p0.pos, p1_abs, p2_abs, p3.pos)
            for t_step in range(steps + 1):
                pt = self.model._cubic_bezier(
                    p0.pos, p1_abs, p2_abs, p3.pos, t_step / steps)
                min_x, max_x = math.floor(pt.x() - radius), math.ceil(pt.x() + radius)
                min_y, max_y = math.floor(pt.y() - radius), math.ceil(pt.y() + radius)
                for y in range(min_y, max_y):
                    for x in range(min_x, max_x):
                        center_pt = QPointF(x + 0.5, y + 0.5)
                        if QLineF(pt, center_pt).length() <= radius:
                            points_to_draw.add((x, y))
        self.grid_blocks = points_to_draw
        self.blockCountChanged.emit(len(self.grid_blocks))
        self.update()

    def _find_closest_segment(self, screen_pos):
        if len(self.model.control_points) < 2:
            return float('inf'), None, None
        min_dist = float('inf')
        closest_segment_idx = None
        closest_t = None
        for i in range(len(self.model.control_points) - 1):
            p0, p3 = self.model.control_points[i], self.model.control_points[i+1]
            p1_abs, p2_abs = p0.pos + p0.out_tangent, p3.pos + p3.in_tangent
            steps = self.model._adaptive_steps(p0.pos, p1_abs, p2_abs, p3.pos)
            for j in range(steps + 1):
                t = j / steps
                curve_point_grid = self.model._cubic_bezier(
                    p0.pos, p1_abs, p2_abs, p3.pos, t)
                dist = QLineF(self.grid_to_screen(
                    curve_point_grid), QPointF(screen_pos)).length()
                if dist < min_dist:
                    min_dist = dist
                    closest_segment_idx = i
                    closest_t = t
        return min_dist, closest_segment_idx, closest_t

    def _split_curve_segment(self, segment_idx, t):
        if self.is_locked:
            return
        p0, p1 = self.model.control_points[segment_idx], self.model.control_points[segment_idx + 1]
        p0_abs, p3_abs = p0.pos, p1.pos
        p1_abs, p2_abs = p0_abs + p0.out_tangent, p3_abs + p1.in_tangent

        new_pos = self.model._cubic_bezier(p0_abs, p1_abs, p2_abs, p3_abs, t)
        new_cp = ControlPoint(new_pos)

        u = 1.0 - t
        deriv = 3*u*u*(p1_abs-p0_abs) + 6*u*t*(p2_abs-p1_abs) + 3*t*t*(p3_abs-p2_abs)
        length = QLineF(QPointF(0, 0), deriv).length()
        if length > 0.001:
            deriv = deriv / length

        new_cp.out_tangent = deriv * QLineF(p0.pos, p1.pos).length() * t * 0.5
        new_cp.in_tangent = -deriv * QLineF(p0.pos, p1.pos).length() * u * 0.5

        p0.out_tangent *= t
        p1.in_tangent *= u

        self.model.control_points.insert(segment_idx + 1, new_cp)
        self.model.selected_point_index = segment_idx + 1

    def _add_point(self, screen_pos):
        if self.is_locked:
            return
        grid_pos = self.screen_to_grid(screen_pos)
        new_cp = ControlPoint(grid_pos)

        if not self.model.control_points:
            self.model.control_points.append(new_cp)
            self.model.selected_point_index = 0
            return

        dist_to_start = QLineF(grid_pos, self.model.control_points[0].pos).length()
        dist_to_end = QLineF(grid_pos, self.model.control_points[-1].pos).length()

        if dist_to_start < dist_to_end:
            self.model.control_points.insert(0, new_cp)
            self.model.selected_point_index = 0
        else:
            self.model.control_points.append(new_cp)
            self.model.selected_point_index = len(self.model.control_points) - 1

    def _delete_point_at(self, screen_pos):
        if self.is_locked:
            return
        for i, pt in reversed(list(enumerate(self.model.control_points))):
            if QLineF(self.grid_to_screen(pt.pos), QPointF(screen_pos)).length() < self.handle_radius * 2:
                del self.model.control_points[i]
                self.model.selected_point_index = None
                self.update_grid_with_curve()
                self.model._save_state_for_undo()
                return

    def _toggle_highlight(self, screen_pos):
        grid_pos_float = self.screen_to_grid(screen_pos)
        grid_pos_tuple = (int(grid_pos_float.x()), int(grid_pos_float.y()))

        if grid_pos_tuple in self.grid_blocks:
            if grid_pos_tuple in self.highlighted_blocks:
                self.highlighted_blocks.remove(grid_pos_tuple)
            else:
                self.highlighted_blocks.add(grid_pos_tuple)
            
            self.highlightCountChanged.emit(len(self.highlighted_blocks))
            self.update()

    def clear_highlights(self):
        self.highlighted_blocks.clear()
        self.highlightCountChanged.emit(0)
        self.update()

    def set_zoom(self, value):
        self.zoom = max(self.min_zoom, min(int(value), self.max_zoom))
        self.zoomChanged.emit(self.zoom)
        self.update()

    def screen_to_grid(self, screen_pos):
        return QPointF(screen_pos.x() / self.zoom + self.view_offset.x(),
                       screen_pos.y() / self.zoom + self.view_offset.y())

    def grid_to_screen(self, grid_pos):
        return QPointF((grid_pos.x() - self.view_offset.x()) * self.zoom,
                       (grid_pos.y() - self.view_offset.y()) * self.zoom)

    def grid_to_screen_rect(self, grid_pos):
        top_left = self.grid_to_screen(grid_pos)
        return QRect(int(top_left.x()), int(top_left.y()), int(self.zoom), int(self.zoom))