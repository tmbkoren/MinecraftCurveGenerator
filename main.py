"""
Main entry point for the refactored Minecraft Curve Generator application.
"""
import sys
from PySide6.QtWidgets import QApplication

from mc_curve_generator.ui.main_window import MainWindow


if __name__ == "__main__":
    app = QApplication(sys.argv)
    editor = MainWindow()
    editor.show()
    sys.exit(app.exec())
