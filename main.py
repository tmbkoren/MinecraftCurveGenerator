import sys
import math
from PySide6.QtWidgets import (
    QApplication, QWidget, QSlider, QLabel, QVBoxLayout, QHBoxLayout, QFrame,
    QSizePolicy, QPushButton, QMessageBox
)
from PySide6.QtGui import QPainter, QPen, QColor, QMouseEvent, QPixmap, QBrush, QKeySequence
from PySide6.QtCore import Qt, QPointF, QRect, QLineF


class ControlPoint:
    """
    Represents a single control point for a Bézier curve, including its
    position and tangent handles for controlling the curve's shape.
    Uses QPointF for floating-point precision.
    """

    def __init__(self, pos):
        self.pos = QPointF(pos)
        self.in_tangent = QPointF(-20, 0)
        self.out_tangent = QPointF(20, 0)
        self.mirrored = True

    def clone(self):
        """Creates a deep copy of this control point."""
        new_point = ControlPoint(QPointF(self.pos))
        new_point.in_tangent = QPointF(self.in_tangent)
        new_point.out_tangent = QPointF(self.out_tangent)
        new_point.mirrored = self.mirrored
        return new_point


class CurveGridEditor(QWidget):
    """
    An advanced planner for designing Minecraft tracks using Bézier curves.
    Features include direct tangent manipulation, per-point tangent mirroring,
    and a full undo/redo history.
    """

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Minecraft Ice Road Planner")
        self.setGeometry(100, 100, 1400, 900)

        # --- Core Settings ---
        self.grid_size = 1000
        self.zoom = 10
        self.min_zoom, self.max_zoom = 2, 40
        self.panning = False
        self.last_pan_pos = QPointF()
        self.view_offset = QPointF(self.grid_size / 2, self.grid_size / 2)

        # --- Curve & State Data ---
        self.grid_blocks = set()
        self.control_points = []
        self.selected_point_index = None
        self.curve_width = 3
        self.handle_radius = 6
        self.show_tangents = True
        self.dragging_object = None

        # --- Drag State for Shift-Drag ---
        self.drag_start_in_tangent_abs = None
        self.drag_start_out_tangent_abs = None

        # --- Undo/Redo History ---
        self.undo_stack = []
        self.redo_stack = []

        self._init_ui()
        self._save_state_for_undo()

    def _init_ui(self):
        """Initializes the user interface, layout, and widgets."""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        control_panel = QFrame(self)
        control_panel.setStyleSheet(
            "background-color: #333; color: white; padding: 5px;")
        control_panel.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        panel_layout = QHBoxLayout(control_panel)

        self.width_label = QLabel(f"Width: {self.curve_width} blocks")
        self.width_slider = QSlider(Qt.Orientation.Horizontal)
        self.width_slider.setRange(1, 25)
        self.width_slider.setValue(self.curve_width)
        self.width_slider.valueChanged.connect(self.set_curve_width)
        self.width_slider.setFixedWidth(150)

        self.zoom_label = QLabel(f"Zoom: {self.zoom}x")
        self.zoom_slider = QSlider(Qt.Orientation.Horizontal)
        self.zoom_slider.setRange(self.min_zoom, self.max_zoom)
        self.zoom_slider.setValue(self.zoom)
        self.zoom_slider.valueChanged.connect(self.set_zoom)
        self.zoom_slider.setFixedWidth(150)

        self.tangent_button = QPushButton("Hide Tangents")
        self.tangent_button.setCheckable(True)
        self.tangent_button.clicked.connect(self.toggle_tangents)
        self.tangent_button.setFixedWidth(120)

        instructions = QLabel(
            "Click empty space to extend path, Click on curve to insert point | Drag to move | Shift-Drag to fix tangents\n"
            "Shortcuts: S=Save | C=Clear | M=Toggle Mirror | Mid-Click=Delete | Ctrl+Z=Undo | Ctrl+Y=Redo"
        )
        instructions.setAlignment(Qt.AlignmentFlag.AlignCenter)

        panel_layout.addWidget(self.width_label)
        panel_layout.addWidget(self.width_slider)
        panel_layout.addSpacing(20)
        panel_layout.addWidget(self.zoom_label)
        panel_layout.addWidget(self.zoom_slider)
        panel_layout.addSpacing(20)
        panel_layout.addWidget(self.tangent_button)
        panel_layout.addStretch()
        panel_layout.addWidget(instructions)
        panel_layout.addStretch()

        self.canvas = QWidget()
        self.canvas.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.canvas.paintEvent = self.paint_canvas
        self.canvas.mousePressEvent = self.canvas_mouse_press
        self.canvas.mouseMoveEvent = self.canvas_mouse_move
        self.canvas.mouseReleaseEvent = self.canvas_mouse_release
        self.canvas.wheelEvent = self.canvas_wheel_event
        self.canvas.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        main_layout.addWidget(control_panel)
        main_layout.addWidget(self.canvas)

    def paint_canvas(self, event):
        painter = QPainter(self.canvas)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.fillRect(self.canvas.rect(), QColor("#282c34"))
            self.draw_track_blocks(painter)
            self.draw_grid_lines(painter)
            self.draw_curve(painter)
            self.draw_control_points(painter)
        finally:
            painter.end()

    def canvas_mouse_press(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.RightButton:
            self.panning = True
            self.last_pan_pos = event.pos()
            return
        if event.button() == Qt.MouseButton.MiddleButton:
            self._delete_point_at(event.pos())
            return
        if event.button() != Qt.MouseButton.LeftButton:
            return

        for i, pt in reversed(list(enumerate(self.control_points))):
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
            self._add_point_at_end(event.pos())

        self.update_grid_with_curve()
        self.canvas.update()
        self._save_state_for_undo()

    def _start_drag(self, point_index):
        self.selected_point_index = point_index
        point = self.control_points[point_index]
        self.drag_start_in_tangent_abs = point.pos + point.in_tangent
        self.drag_start_out_tangent_abs = point.pos + point.out_tangent
        self._save_state_for_undo()
        self.canvas.update()

    def canvas_mouse_move(self, event: QMouseEvent):
        if self.panning:
            delta = QPointF(event.pos()) - self.last_pan_pos
            self.view_offset -= delta / self.zoom
            self.last_pan_pos = event.pos()
            self.canvas.update()
            return

        if not self.dragging_object:
            return

        drag_type, index = self.dragging_object
        pt = self.control_points[index]
        grid_pos = self.screen_to_grid(event.pos())
        shift_pressed = event.modifiers() & Qt.KeyboardModifier.ShiftModifier

        if drag_type == 'point':
            pt.pos = grid_pos
            if shift_pressed:
                pt.in_tangent = self.drag_start_in_tangent_abs - grid_pos
                pt.out_tangent = self.drag_start_out_tangent_abs - grid_pos
        else:
            screen_center = self.grid_to_screen(pt.pos)
            tangent_vec = (QPointF(event.pos()) - screen_center) / self.zoom
            if drag_type == 'in_handle':
                pt.in_tangent = tangent_vec
                if pt.mirrored:
                    pt.out_tangent = -tangent_vec
            elif drag_type == 'out_handle':
                pt.out_tangent = tangent_vec
                if pt.mirrored:
                    pt.in_tangent = -tangent_vec

        self.update_grid_with_curve()
        self.canvas.update()

    def canvas_mouse_release(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.RightButton:
            self.panning = False
        elif event.button() == Qt.MouseButton.LeftButton:
            self.dragging_object = None

    def canvas_wheel_event(self, event):
        steps = event.angleDelta().y() / 120
        self.set_zoom(self.zoom + steps)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_S:
            self.export_image()
        elif event.key() == Qt.Key.Key_C:
            self.clear_points()
        elif event.key() == Qt.Key.Key_T:
            self.tangent_button.click()
        elif event.key() == Qt.Key.Key_M and self.selected_point_index is not None:
            self._toggle_mirror()
        elif event.matches(QKeySequence.StandardKey.Undo):
            self.undo()
        elif event.matches(QKeySequence.StandardKey.Redo):
            self.redo()

    def draw_grid_lines(self, painter):
        if self.zoom <= 3:
            return
        painter.setPen(QPen(QColor(60, 60, 60), 1))
        w, h = self.canvas.width(), self.canvas.height()
        start_x, start_y = -self.view_offset.x() * self.zoom, -self.view_offset.y() * self.zoom
        x_offset, y_offset = start_x % self.zoom, start_y % self.zoom
        for x in range(int(x_offset), w, self.zoom):
            painter.drawLine(x, 0, x, h)
        for y in range(int(y_offset), h, self.zoom):
            painter.drawLine(0, y, w, y)

    def draw_track_blocks(self, painter):
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#a0e8ff"))
        for pos_tuple in self.grid_blocks:
            rect = self.grid_to_screen_rect(QPointF(*pos_tuple))
            if self.canvas.rect().intersects(rect):
                painter.drawRect(rect)

    def draw_curve(self, painter):
        if len(self.control_points) < 2:
            return
        painter.setPen(QPen(QColor(255, 255, 255, 150), 2))
        for i in range(len(self.control_points) - 1):
            p0, p3 = self.control_points[i], self.control_points[i+1]
            p1_abs, p2_abs = p0.pos + p0.out_tangent, p3.pos + p3.in_tangent
            steps = self._adaptive_steps(p0.pos, p1_abs, p2_abs, p3.pos)
            path_points = [self.grid_to_screen(self._cubic_bezier(
                p0.pos, p1_abs, p2_abs, p3.pos, t/steps)) for t in range(steps + 1)]
            for j in range(len(path_points) - 1):
                painter.drawLine(path_points[j], path_points[j + 1])

    def draw_control_points(self, painter):
        for i, pt in enumerate(self.control_points):
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
            is_selected = (i == self.selected_point_index)
            painter.setBrush(QColor("yellow") if is_selected else QColor("red"))
            painter.setPen(QPen(QColor("white") if is_selected else QColor("black"), 2))
            painter.drawEllipse(screen_pos, 8 if is_selected else 6, 8 if is_selected else 6)

    def update_grid_with_curve(self):
        self.grid_blocks.clear()
        if len(self.control_points) < 2:
            self.canvas.update()
            return
        points_to_draw = set()
        radius = self.curve_width / 2.0
        for i in range(len(self.control_points) - 1):
            p0, p3 = self.control_points[i], self.control_points[i+1]
            p1_abs, p2_abs = p0.pos + p0.out_tangent, p3.pos + p3.in_tangent
            steps = self._adaptive_steps(p0.pos, p1_abs, p2_abs, p3.pos)
            for t_step in range(steps + 1):
                pt = self._cubic_bezier(
                    p0.pos, p1_abs, p2_abs, p3.pos, t_step / steps)
                min_x, max_x = math.floor(pt.x() - radius), math.ceil(pt.x() + radius)
                min_y, max_y = math.floor(pt.y() - radius), math.ceil(pt.y() + radius)
                for y in range(min_y, max_y):
                    for x in range(min_x, max_x):
                        center_pt = QPointF(x + 0.5, y + 0.5)
                        if QLineF(pt, center_pt).length() <= radius:
                            points_to_draw.add((x, y))
        self.grid_blocks = points_to_draw
        self.canvas.update()

    def _cubic_bezier(self, p0, p1, p2, p3, t):
        u = 1 - t
        return u**3 * p0 + 3 * u**2 * t * p1 + 3 * u * t**2 * p2 + t**3 * p3

    def _adaptive_steps(self, p0, p1, p2, p3):
        length = QLineF(p0, p1).length() + QLineF(p1, p2).length() + QLineF(p2, p3).length()
        return max(20, int(length / 2))

    def _save_state_for_undo(self):
        self.undo_stack.append([pt.clone() for pt in self.control_points])
        self.redo_stack.clear()
        if len(self.undo_stack) > 50:
            self.undo_stack.pop(0)

    def undo(self):
        if len(self.undo_stack) > 1:
            self.redo_stack.append(self.undo_stack.pop())
            self._restore_state(self.undo_stack[-1])

    def redo(self):
        if self.redo_stack:
            state = self.redo_stack.pop()
            self.undo_stack.append(state)
            self._restore_state(state)

    def _restore_state(self, state):
        self.control_points = [pt.clone() for pt in state]
        self.selected_point_index = None
        self.update_grid_with_curve()

    def _find_closest_segment(self, screen_pos):
        if len(self.control_points) < 2:
            return float('inf'), None, None
        min_dist = float('inf')
        closest_segment_idx = None
        closest_t = None
        for i in range(len(self.control_points) - 1):
            p0, p3 = self.control_points[i], self.control_points[i+1]
            p1_abs, p2_abs = p0.pos + p0.out_tangent, p3.pos + p3.in_tangent
            steps = self._adaptive_steps(p0.pos, p1_abs, p2_abs, p3.pos)
            for j in range(steps + 1):
                t = j / steps
                curve_point_grid = self._cubic_bezier(
                    p0.pos, p1_abs, p2_abs, p3.pos, t)
                dist = QLineF(self.grid_to_screen(
                    curve_point_grid), QPointF(screen_pos)).length()
                if dist < min_dist:
                    min_dist = dist
                    closest_segment_idx = i
                    closest_t = t
        return min_dist, closest_segment_idx, closest_t

    def _split_curve_segment(self, segment_idx, t):
        p0, p1 = self.control_points[segment_idx], self.control_points[segment_idx + 1]
        p0_abs, p3_abs = p0.pos, p1.pos
        p1_abs, p2_abs = p0_abs + p0.out_tangent, p3_abs + p1.in_tangent

        new_pos = self._cubic_bezier(p0_abs, p1_abs, p2_abs, p3_abs, t)
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

        self.control_points.insert(segment_idx + 1, new_cp)
        self.selected_point_index = segment_idx + 1

    def _add_point_at_end(self, screen_pos):
        grid_pos = self.screen_to_grid(screen_pos)
        if not self.control_points:
            self.control_points.append(ControlPoint(grid_pos))
            self.selected_point_index = 0
            return

        dist_to_start = QLineF(grid_pos, self.control_points[0].pos).length()
        dist_to_end = QLineF(grid_pos, self.control_points[-1].pos).length()

        if dist_to_start < dist_to_end:
            self.control_points.insert(0, ControlPoint(grid_pos))
            self.selected_point_index = 0
        else:
            self.control_points.append(ControlPoint(grid_pos))
            self.selected_point_index = len(self.control_points) - 1

    def _delete_point_at(self, screen_pos):
        for i, pt in reversed(list(enumerate(self.control_points))):
            if QLineF(self.grid_to_screen(pt.pos), QPointF(screen_pos)).length() < self.handle_radius * 2:
                del self.control_points[i]
                self.selected_point_index = None
                self.update_grid_with_curve()
                self._save_state_for_undo()
                return

    def _toggle_mirror(self):
        pt = self.control_points[self.selected_point_index]
        pt.mirrored = not pt.mirrored
        self.canvas.update()
        self._save_state_for_undo()

    def set_curve_width(self, value):
        self.curve_width = value
        self.width_label.setText(f"Width: {value} blocks")
        self.update_grid_with_curve()

    def set_zoom(self, value):
        self.zoom = max(self.min_zoom, min(int(value), self.max_zoom))
        self.zoom_slider.setValue(self.zoom)
        self.zoom_label.setText(f"Zoom: {self.zoom}x")
        self.canvas.update()

    def toggle_tangents(self):
        self.show_tangents = not self.show_tangents
        self.tangent_button.setText(
            "Hide Tangents" if self.show_tangents else "Show Tangents")
        self.canvas.update()

    def clear_points(self):
        self.control_points.clear()
        self.selected_point_index = None
        self.update_grid_with_curve()
        self._save_state_for_undo()

    def export_image(self):
        pixmap = self.canvas.grab()
        filename = "minecraft_track_design.png"
        pixmap.save(filename)
        QMessageBox.information(self, "Image Saved",
                                f"Track image saved as '{filename}'")

    def screen_to_grid(self, screen_pos):
        return QPointF(screen_pos.x() / self.zoom + self.view_offset.x(),
                       screen_pos.y() / self.zoom + self.view_offset.y())

    def grid_to_screen(self, grid_pos):
        return QPointF((grid_pos.x() - self.view_offset.x()) * self.zoom,
                       (grid_pos.y() - self.view_offset.y()) * self.zoom)

    def grid_to_screen_rect(self, grid_pos):
        top_left = self.grid_to_screen(grid_pos)
        return QRect(int(top_left.x()), int(top_left.y()), self.zoom, self.zoom)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    editor = CurveGridEditor()
    editor.show()
    sys.exit(app.exec())