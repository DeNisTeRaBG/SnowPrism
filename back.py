import re
import os
import sys
import json
import cloudscraper
import subprocess
import glob

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ARIA2_EXECUTABLE = os.path.join(BASE_DIR, "venv", "Scripts", "aria2c.exe")

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
}


def download_file(link, folder_path, progress_callback=None, process_callback=None):
    if not link:
        print("Error: Please provide a link")
        return

    link = link.strip()

    if link.startswith("magnet:?"):
        # Pass the new callback down to the magnet function
        return _download_magnet(link, folder_path, progress_callback, process_callback)
    elif link.startswith("http://") or link.startswith("https://"):
        return _download_direct(link, folder_path, progress_callback)
    else:
        return False, "Error: Invalid link. Must start with http, https, or magnet:?"



def _download_direct(url, folder_path, progress_callback):
    match = re.search(r'/([^/]+\.(jpg|jpeg|png|gif|txt|mp4|zip|rar|exe))$', url, re.IGNORECASE)
    filename = match.group(1) if match else "downloaded_file"
    final_save_path = os.path.join(folder_path, filename)

    scraper = cloudscraper.create_scraper()
    
    try:
        if progress_callback:
            progress_callback("Connecting to server...")
            
        r = scraper.get(url, headers=headers)
        if r.status_code == 200:
            with open(final_save_path, "wb") as file:
                file.write(r.content)
            return True, f"Success! File saved to:\n{final_save_path}"
        else:
            return False, f"Failed HTTP. Status code: {r.status_code}"
    except Exception as e:
        return False, f"HTTP Network error: {e}"


def _download_magnet(magnet_link, folder_path, progress_callback, process_callback=None):
    try:
        if progress_callback:
            progress_callback("Initializing aria2c for magnet link...")

        cmd = [
            ARIA2_EXECUTABLE,
            "--dir", folder_path,
            "--seed-time=0",
            magnet_link
        ]

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            creationflags=subprocess.CREATE_NO_WINDOW
        )

        # --- NEW BRIDGE: Send the process object back to the GUI! ---
        if process_callback:
            process_callback(process)
        # ------------------------------------------------------------

        for line in process.stdout:
            line = line.strip()
            if line and progress_callback:
                progress_callback(f"[aria2] {line}")

        process.wait()

        
        if process.returncode == 0:
            if progress_callback:
                progress_callback("Cleaning up .srt files...")
            
            remove_srt_files(folder_path)


            return True, f"Success! Magnet download completed in:\n{folder_path}"
        else:
            return False, f"Download failed. aria2c exited with code {process.returncode}."

    except FileNotFoundError:
        return False, "Error: 'aria2c' is not installed or not added to your system PATH."
    except Exception as e:
        return False, f"An unexpected error occurred: {e}"
    

def remove_srt_files(directory):
    search_pattern = os.path.join(directory, '**', '*.srt')
    
    for file_path in glob.glob(search_pattern, recursive=True):
        try:
            os.remove(file_path)
            print(f"Deleted subtitle: {file_path}")
        except Exception as e:
            print(f"Failed to delete {file_path}: {e}")
    
class HistoryManager:
    def __init__(self, filepath="download_history.json"):
        self.filepath = filepath

    def load(self):
        """Reads the JSON file and returns a list of dictionaries."""
        if not os.path.exists(self.filepath):
            return [] # Return empty list if no history exists yet

        try:
            with open(self.filepath, "r") as file:
                return json.load(file)
        except Exception as e:
            print(f"Failed to load history: {e}")
            return []

    def save(self, history_data):
        """Takes a list of dictionaries and saves it to a JSON file."""
        try:
            with open(self.filepath, "w") as file:
                json.dump(history_data, file, indent=4)
        except Exception as e:
            print(f"Failed to save history: {e}")



def get_resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller"""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        # If we are not compiled, use the normal script folder
        base_path = os.path.dirname(os.path.abspath(__file__))
    
    return os.path.join(base_path, relative_path)


ARIA2_EXECUTABLE = get_resource_path("aria2c.exe")