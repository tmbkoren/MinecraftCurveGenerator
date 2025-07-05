import sys
import os
import requests
import subprocess
from PySide6.QtCore import QObject, Signal, QCoreApplication
from PySide6.QtWidgets import QMessageBox

# --- Configuration ---
GITHUB_REPO = "tmbkoren/MinecraftCurveGenerator"
API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"


class UpdateWorker(QObject):
    """Performs the update check in a background thread."""
    update_found = Signal(dict)
    error_occurred = Signal(str)

    def __init__(self, current_version):
        super().__init__()
        self.current_version = current_version

    def run(self):
        """Checks for a new release on GitHub."""
        try:
            response = requests.get(API_URL)
            response.raise_for_status()
            latest_release = response.json()
            latest_version = latest_release["tag_name"].lstrip('v')

            if latest_version > self.current_version:
                self.update_found.emit(latest_release)

        except requests.RequestException as e:
            self.error_occurred.emit(f"Update check failed: {e}")


def show_update_dialog(release_info, parent):
    """
    Displays a dialog asking the user if they want to download the new version.
    This function must be called from the main GUI thread.
    """
    latest_version = release_info["tag_name"]
    release_notes = release_info["body"]

    msg_box = QMessageBox(parent)
    msg_box.setIcon(QMessageBox.Icon.Information)
    msg_box.setWindowTitle("Update Available")
    msg_box.setText(
        f"A new version ({latest_version}) is available! Do you want to update?")
    msg_box.setInformativeText(f"\nRelease Notes:\n{release_notes}")
    msg_box.setStandardButtons(
        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    msg_box.setDefaultButton(QMessageBox.StandardButton.Yes)

    if msg_box.exec() == QMessageBox.StandardButton.Yes:
        download_and_apply_update(release_info, parent)


def download_and_apply_update(release_info, parent):
    assets = release_info.get("assets", [])
    if not assets:
        QMessageBox.critical(parent, "Update Error",
                             "No assets found for the latest release.")
        return

    asset_url = assets[0]["browser_download_url"]
    new_exe_name = assets[0]["name"]

    try:
        response = requests.get(asset_url, stream=True)
        response.raise_for_status()

        temp_exe_path = os.path.join(os.path.dirname(
            sys.executable), f"_new_{new_exe_name}")
        with open(temp_exe_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        old_exe = os.path.abspath(sys.executable)
        create_and_run_updater_script(temp_exe_path, sys.executable)
        QCoreApplication.quit()

    except requests.RequestException as e:
        QMessageBox.critical(parent, "Download Error",
                             f"Failed to download update: {e}")
    except IOError as e:
        QMessageBox.critical(parent, "File Error",
                             f"Failed to save update: {e}")


def create_and_run_updater_script(new_path, old_path):
    """
    Creates and executes a batch script to replace the old executable and
    notify the user to restart the application manually.
    """
    app_dir = os.path.dirname(old_path)
    app_basename = os.path.basename(old_path)

    script_content = f'''
    @echo off
    title Application Updated Successfully

    :: 1. Wait for the main application to close.
    timeout /t 4 /nobreak > nul

    :: 2. As a fallback, forcefully terminate the process if it's still locked.
    taskkill /f /im "{app_basename}" /t > nul 2>&1

    :: 3. Change to the application's directory.
    cd /d "{app_dir}"

    :: 4. Replace the old executable with the new one.
    move /y "{new_path}" "{old_path}"

    if errorlevel 1 (
        echo.
        echo ERROR: Failed to update the application file.
        echo Please close the application manually and try again.
        pause
        exit /b 1
    )

    :: 5. Notify the user that the update is complete.
    echo.
    echo Update Successful!
    echo.
    echo Please start the application again manually.
    echo.
    pause

    :: 6. Self-delete the updater script.
    (goto) 2>nul & del "%~f0"
    '''

    script_path = os.path.join(app_dir, "updater.bat")
    with open(script_path, 'w', encoding='utf-8') as f:
        f.write(script_content)

    # Launch the script in a new console window so the user sees the message.
    subprocess.Popen([script_path], creationflags=subprocess.CREATE_NEW_CONSOLE)
