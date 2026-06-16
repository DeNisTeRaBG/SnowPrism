import sys
import os
import winreg
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox
from gui import MainWindow
from back import get_resource_path, is_default_magnet_handler, fix_magnet_registry



def is_default_magnet_handler():
    """Checks if SnowPrism is currently set as the default in the registry."""
    try:
        # Open the specific registry key
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\magnet\shell\open\command")
        value, _ = winreg.QueryValueEx(key, "")
        winreg.CloseKey(key)

        # Check if our current executable path is inside the registry string
        if sys.executable in value:
            return True
        return False
    except FileNotFoundError:
        # If the key doesn't even exist, we definitely aren't the default!
        return False

def fix_magnet_registry():
    """Rewrites the registry to point to the current executable."""
    try:
        # Forcefully create or open the keys
        winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\magnet\shell\open\command")
        
        # Write the base protocol key
        key_base = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\magnet", 0, winreg.KEY_WRITE)
        winreg.SetValueEx(key_base, "", 0, winreg.REG_SZ, "URL:magnet protocol")
        winreg.SetValueEx(key_base, "URL Protocol", 0, winreg.REG_SZ, "")
        winreg.CloseKey(key_base)

        # Write the command key pointing to our .exe
        key_cmd = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\magnet\shell\open\command", 0, winreg.KEY_WRITE)
        command_string = f'"{sys.executable}" "%1"'
        winreg.SetValueEx(key_cmd, "", 0, winreg.REG_SZ, command_string)
        winreg.CloseKey(key_cmd)
        
        return True
    except Exception as e:
        print(f"Registry write failed: {e}")
        return False

def check_and_prompt_registry(parent_window):
    """Checks the registry and asks the user if they want to fix it."""
    if not is_default_magnet_handler():
        reply = QMessageBox.question(
            parent_window, 
            "Default App Check", 
            "SnowPrism is currently not your default application for magnet links.\n\nWould you like to set it as the default now?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            success = fix_magnet_registry()
            if success:
                QMessageBox.information(
                    parent_window, 
                    "Success", 
                    "Registry updated successfully!\n\n(Note: Windows 11 may still ask you to confirm this choice in the Settings menu the next time you click a link)."
                )
            else:
                QMessageBox.warning(
                    parent_window, 
                    "Error", 
                    "Could not update the registry. You may need to run SnowPrism as Administrator."
                )

if __name__ == '__main__':
    if getattr(sys, 'frozen', False):
        application_path = os.path.dirname(sys.executable)
    else:
        application_path = os.path.dirname(os.path.abspath(__file__))
        

    app = QApplication(sys.argv)

    app.setQuitOnLastWindowClosed(False)

    app.setApplicationName("SnowPrism")
    app.setOrganizationName("DenisteraBG")

    icon_path = get_resource_path("app_icon.ico")
    app.setWindowIcon(QIcon(icon_path))

    main_window = MainWindow()
    
    if len(sys.argv) > 1:
        passed_link = sys.argv[1].strip('"').strip("'")
        
        if passed_link.startswith("magnet:"):
            main_window.open_downloader_with_link(passed_link)

    main_window.show()

    check_and_prompt_registry(main_window)

    sys.exit(app.exec())

