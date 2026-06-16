import re
import os
import sys
import json
import cloudscraper
import subprocess
import glob
import winreg
import mimetypes
from urllib.parse import urlparse, unquote

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ARIA2_EXECUTABLE = os.path.join(BASE_DIR, "venv", "Scripts", "aria2c.exe")

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
}


def download_file(link, folder_path, progress_callback=None, process_callback=None, speed_limit=0):
    if not link:
        print("Error: Please provide a link")
        return

    link = link.strip()

    if link.startswith("magnet:?"):
        # Pass the limit down to the magnet handler
        return _download_magnet(link, folder_path, progress_callback, process_callback, speed_limit)
    elif link.startswith("http://") or link.startswith("https://"):
        return _download_direct(link, folder_path, progress_callback)
    else:
        return False, "Error: Invalid link."



def _download_direct(url, folder_path, progress_callback):
    scraper = cloudscraper.create_scraper()
    
    try:
        if progress_callback:
            progress_callback("Connecting to server...")
            
        # stream=True lets us read the headers BEFORE downloading the heavy data
        with scraper.get(url, headers=headers, stream=True) as r:
            if r.status_code == 200:
                
                # --- SMART NAMING SYSTEM ---
                filename = None
                
                # 1. Check if the server explicitly tells us the exact file name
                cd = r.headers.get('content-disposition')
                if cd:
                    match = re.search(r'filename\*?=(?:UTF-8\'\')?([^;]+)', cd, re.IGNORECASE)
                    if match:
                        filename = unquote(match.group(1).strip('"\''))
                
                # 2. Fallback: Try to rip the name from the end of the URL
                if not filename:
                    parsed_url = urlparse(url)
                    filename = unquote(os.path.basename(parsed_url.path))
                
                # 3. Last Resort: Use a default name
                if not filename:
                    filename = "downloaded_file"
                    
                # 4. If the file has no extension (like your HTML example), guess it!
                if "." not in filename:
                    content_type = r.headers.get('content-type', '').split(';')[0]
                    ext = mimetypes.guess_extension(content_type)
                    if ext:
                        if ext == '.htm': ext = '.html' # Quick fix for older mimetypes
                        filename += ext
                # ----------------------------

                final_save_path = os.path.join(folder_path, filename)

                # Write the file in 8KB chunks so it doesn't crash your RAM
                with open(final_save_path, "wb") as file:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            file.write(chunk)
                            
                return True, f"Success! File saved to:\n{final_save_path}"
            else:
                return False, f"Failed HTTP. Status code: {r.status_code}"
    except Exception as e:
        return False, f"HTTP Network error: {e}"


def _download_magnet(magnet_link, folder_path, progress_callback, process_callback=None, speed_limit=0):
    try:
        if progress_callback:
            progress_callback("Initializing aria2c for magnet link...")

        cmd = [
            ARIA2_EXECUTABLE,
            "--dir", folder_path,
            "--seed-time=0"
        ]

        if speed_limit > 0:
            cmd.append(f"--max-overall-download-limit={speed_limit}K")

        # The link must always be the very last argument!
        cmd.append(magnet_link)

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


def is_default_magnet_handler():
    """Checks if SnowPrism is currently set as the default in the registry."""
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\magnet\shell\open\command")
        value, _ = winreg.QueryValueEx(key, "")
        winreg.CloseKey(key)
        return sys.executable in value
    except FileNotFoundError:
        return False

def fix_magnet_registry():
    """Rewrites the registry to point to the current executable."""
    try:
        winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\magnet\shell\open\command")
        
        key_base = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\magnet", 0, winreg.KEY_WRITE)
        winreg.SetValueEx(key_base, "", 0, winreg.REG_SZ, "URL:magnet protocol")
        winreg.SetValueEx(key_base, "URL Protocol", 0, winreg.REG_SZ, "")
        winreg.CloseKey(key_base)

        key_cmd = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\magnet\shell\open\command", 0, winreg.KEY_WRITE)
        command_string = f'"{sys.executable}" "%1"'
        winreg.SetValueEx(key_cmd, "", 0, winreg.REG_SZ, command_string)
        winreg.CloseKey(key_cmd)
        return True
    except Exception as e:
        print(f"Registry write failed: {e}")
        return False

def remove_magnet_registry():
    """Safely removes the SnowPrism magnet protocol association."""
    try:
        # Deleting the command key breaks the link, returning it to default Windows behavior
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\magnet\shell\open\command")
        return True
    except FileNotFoundError:
        return True # Already gone
    except Exception as e:
        print(f"Registry delete failed: {e}")
        return False

ARIA2_EXECUTABLE = get_resource_path("aria2c.exe")