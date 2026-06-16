import re
import os
import winreg
import platform
import subprocess
from urllib.parse import unquote
from PySide6.QtWidgets import (QLineEdit, QPushButton,
                               QVBoxLayout, QHBoxLayout, QDialog, QFileDialog, 
                               QMainWindow, QWidget, QTableWidget, QTableWidgetItem, QHeaderView,
                                 QMessageBox, QCheckBox, QMenu, QSystemTrayIcon)
from PySide6.QtCore import Qt, QThread, Signal, QSettings
from PySide6.QtGui import QAction, QIcon
from back import *

def get_display_name(url):
    if url.startswith("magnet:"):
        match = re.search(r'dn=([^&]+)', url)
        if match:
            return unquote(match.group(1).replace('+', ' '))
        return "Unknown Torrent"
    else:
        return url.split('/')[-1] or "Unknown File"


class DownloadWorker(QThread):
    progress_signal = Signal(int, str) 
    finished_signal = Signal(int, bool, str) 

    def __init__(self, row, url, folder_path):
        super().__init__()
        self.row = row
        self.url = url
        self.folder_path = folder_path

    def run(self):
        success, message = download_file(
            self.url, 
            self.folder_path, 
            progress_callback=lambda msg: self.progress_signal.emit(self.row, msg)
        )
        self.finished_signal.emit(self.row, success, message)


class DownloadDialog(QDialog):
    download_requested = Signal(str, str) 

    def __init__(self, parent=None):
        super(DownloadDialog, self).__init__(parent)
        self.setWindowTitle("New Download")
        self.setFixedSize(500, 150)

        self.url_edit = QLineEdit()
        self.url_edit.setPlaceholderText("Paste Download Link")

        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Choose where to save...")
        self.path_edit.setReadOnly(True)
        
        self.browse_button = QPushButton("Browse...")
        self.download_button = QPushButton("Start Download")

        path_layout = QHBoxLayout()
        path_layout.addWidget(self.path_edit)
        path_layout.addWidget(self.browse_button)
        path_layout.addWidget(self.download_button, alignment=Qt.AlignRight)

        main_layout = QVBoxLayout()
        main_layout.setSpacing(15)
        main_layout.setContentsMargins(25, 25, 25, 25)

        main_layout.addWidget(self.url_edit)
        main_layout.addLayout(path_layout) 
        main_layout.addStretch()

        self.setLayout(main_layout)

        self.browse_button.clicked.connect(self.choose_path)
        self.download_button.clicked.connect(self.send_download_request)

    def choose_path(self):
        folder_path = QFileDialog.getExistingDirectory(self, "Select Download Folder")
        if folder_path:
            self.path_edit.setText(folder_path)

    def send_download_request(self):
        url = self.url_edit.text()
        folder_path = self.path_edit.text()

        if not url or not folder_path:
            return

        self.download_requested.emit(url, folder_path)
        self.url_edit.clear() 

        self.close()


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SnowPrism Download Manager")
        self.resize(700, 500)

        self.settings = QSettings("SnowPrismApp", "SnowPrism")

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        button_layout = QHBoxLayout()

        self.open_downloader_btn = QPushButton("Add New Download")
        self.open_downloader_btn.setFixedSize(200, 40)
        
        self.remove_item_btn = QPushButton("Remove Selected")
        self.remove_item_btn.setFixedSize(200, 40)
        
        button_layout.addWidget(self.open_downloader_btn)
        button_layout.addWidget(self.remove_item_btn)
        button_layout.setAlignment(Qt.AlignCenter)

        self.table = QTableWidget(0, 3) 
        self.table.setHorizontalHeaderLabels(["File Name", "Progress", "Seeders"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)

        self.table.setSelectionBehavior(QTableWidget.SelectRows)
        self.table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.table.cellDoubleClicked.connect(self.open_download_directory)

        layout = QVBoxLayout(central_widget)
        layout.addLayout(button_layout)
        layout.addWidget(self.table)

        self.open_downloader_btn.clicked.connect(self.open_downloader)
        self.remove_item_btn.clicked.connect(self.remove_selected_item)
        
        self.downloader_dialog = None
        self.active_workers = []

        self.last_save_path = ""

        self.history_manager = HistoryManager()
        self.load_history_to_table()

        self.setup_system_tray()


    def setup_system_tray(self):
        """Creates the system tray icon and its right-click context menu."""
        self.tray_icon = QSystemTrayIcon(self)
        
        icon_path = get_resource_path("app_icon.ico")
        self.tray_icon.setIcon(QIcon(icon_path))
        
        tray_menu = QMenu(self)
        
        open_action = QAction("Open SnowPrism", self)
        open_action.triggered.connect(self.showNormal) 
        
        exit_action = QAction("Exit", self)
        exit_action.triggered.connect(self.force_exit) 
        
        tray_menu.addAction(open_action)
        tray_menu.addSeparator()
        tray_menu.addAction(exit_action)
        
        self.tray_icon.setContextMenu(tray_menu)
        self.tray_icon.activated.connect(self.on_tray_icon_activated)
        self.tray_icon.show()

    def on_tray_icon_activated(self, reason):
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.showNormal()
            self.activateWindow()

    def force_exit(self):
        """Bypasses the close confirmation and shuts down completely."""
        self.tray_icon.hide() 
        sys.exit(0)


    def remove_selected_item(self):
        # Get all currently selected items in the table
        selected_items = self.table.selectedItems()
        
        if not selected_items:
            return
            
        # Extract the unique row numbers (since 1 row has multiple items/columns)
        rows_to_delete = set()
        for item in selected_items:
            rows_to_delete.add(item.row())
            
        confirm = QMessageBox.question(
            self, "Confirm Removal", 
            f"Remove {len(rows_to_delete)} item(s) from your download history?\n(The downloaded files will NOT be deleted)",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if confirm == QMessageBox.Yes:
            # IMPORTANT: Sort in reverse! Delete from the bottom up so indices don't shift.
            for row in sorted(list(rows_to_delete), reverse=True):
                self.table.removeRow(row)
                
            self.save_history_from_table()

    def load_history_to_table(self):
        history_data = self.history_manager.load()
        
        for item in history_data:
            current_row = self.table.rowCount()
            self.table.insertRow(current_row)

            display_name = get_display_name(item["url"])
            name_item = QTableWidgetItem(display_name)
            
            hidden_data = {"url": item["url"], "folder_path": item["folder_path"]}
            name_item.setData(Qt.UserRole, hidden_data) 
            
            progress_item = QTableWidgetItem(item["progress"])
            progress_item.setTextAlignment(Qt.AlignCenter)

            seeder_item = QTableWidgetItem("-")
            seeder_item.setTextAlignment(Qt.AlignCenter)

            self.table.setItem(current_row, 0, name_item)
            self.table.setItem(current_row, 1, progress_item)
            self.table.setItem(current_row, 2, seeder_item)

            self.last_save_path = item["folder_path"]

    def save_history_from_table(self):
        history_data = []
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 0)
            progress_item = self.table.item(row, 1)

            if name_item and progress_item:
                hidden_data = name_item.data(Qt.UserRole)
                
                history_data.append({
                    "url": hidden_data["url"], 
                    "folder_path": hidden_data["folder_path"],
                    "progress": progress_item.text()
                })

        self.history_manager.save(history_data)

    def open_downloader(self):
        if self.downloader_dialog is None:
            self.downloader_dialog = DownloadDialog(self)
            self.downloader_dialog.download_requested.connect(self.start_download)
            
        if self.last_save_path:
            self.downloader_dialog.path_edit.setText(self.last_save_path)

        self.downloader_dialog.show()
        self.downloader_dialog.raise_()
        self.downloader_dialog.activateWindow()

    def start_download(self, url, folder_path):
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item:
                hidden_data = item.data(Qt.UserRole)
                if hidden_data and hidden_data.get("url") == url:
                    reply = QMessageBox.question(
                        self, "Duplicate Download", 
                        "This link is already in your download history.\n\nDo you want to add it again?",
                        QMessageBox.Yes | QMessageBox.No
                    )
                    
                    if reply == QMessageBox.No:
                        return

        self.last_save_path = folder_path 
        
        current_row = self.table.rowCount()
        self.table.insertRow(current_row)

        display_name = get_display_name(url)
        name_item = QTableWidgetItem(display_name)
        
        hidden_data = {"url": url, "folder_path": folder_path}
        name_item.setData(Qt.UserRole, hidden_data) 
        
        progress_item = QTableWidgetItem("Starting...")
        progress_item.setTextAlignment(Qt.AlignCenter)

        seeder_item = QTableWidgetItem("-")
        seeder_item.setTextAlignment(Qt.AlignCenter)

        self.table.setItem(current_row, 0, name_item)
        self.table.setItem(current_row, 1, progress_item)
        self.table.setItem(current_row, 2, seeder_item)

        worker = DownloadWorker(current_row, url, folder_path)
        worker.progress_signal.connect(self.on_progress_update)
        worker.finished_signal.connect(self.on_download_finished)
        
        self.active_workers.append(worker) 
        worker.start()
        
        self.save_history_from_table()

    def on_progress_update(self, row, current_status):
        # 1. Update the Percentage
        match = re.search(r'\((\d+)%\)', current_status)
        if match:
            percent_val = match.group(1)
            if percent_val != "100":
                # Safety check in case the row was deleted while downloading
                item = self.table.item(row, 1)
                if item:
                    item.setText(f"{percent_val}%")

        # 2. Update the Seeders
        seeder_match = re.search(r'SD:(\d+)', current_status)
        if seeder_match:
            seeders_val = seeder_match.group(1)
            item = self.table.item(row, 2)
            if item:
                item.setText(seeders_val)

    def on_download_finished(self, row, success, message):
        if success:
            self.table.item(row, 1).setText("100%")
        else:
            self.table.item(row, 1).setText("Error")
            QMessageBox.critical(self, "Download Failed", f"Reason:\n{message}")
        
        self.save_history_from_table()

    def open_download_directory(self, row, column):
        hidden_data = self.table.item(row, 0).data(Qt.UserRole)
        folder_path = hidden_data["folder_path"]
        
        if not folder_path or not os.path.exists(folder_path):
            print("Directory does not exist yet.")
            return
            
        if platform.system() == "Windows":
            os.startfile(folder_path)
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", folder_path])
        else:
            subprocess.Popen(["xdg-open", folder_path])

    def open_downloader_with_link(self, url):
        self.open_downloader()
        self.downloader_dialog.url_edit.setText(url)

    def closeEvent(self, event):
        """Overrides the standard Windows 'X' close button behavior."""
        self.save_history_from_table() # Always save history first!
        
        saved_preference = self.settings.value("close_behavior", "")
        
        if saved_preference == "exit":
            self.force_exit()
        elif saved_preference == "tray":
            self.hide() 
            event.ignore()
            return

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("Close SnowPrism")
        msg_box.setText("What would you like to do?")
        
        tray_button = msg_box.addButton("Run in Background", QMessageBox.ButtonRole.ActionRole)
        exit_button = msg_box.addButton("Exit Program", QMessageBox.ButtonRole.RejectRole)
        
        checkbox = QCheckBox("Remember my choice")
        msg_box.setCheckBox(checkbox)
        
        msg_box.exec()
        
        if msg_box.clickedButton() == tray_button:
            if checkbox.isChecked():
                self.settings.setValue("close_behavior", "tray")
            self.hide() 
            event.ignore() 
        else:
            if checkbox.isChecked():
                self.settings.setValue("close_behavior", "exit")
            self.force_exit()