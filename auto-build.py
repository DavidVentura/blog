import sys
import os
import time
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
import subprocess

def print_usage_and_exit():
    print("1 arg -- directory to watch")
    sys.exit(1)

def validate_directory(dir_path):
    if not os.path.isdir(dir_path):
        print(f"{dir_path} does not exist/is not a dir")
        sys.exit(1)

def update_timestamps(dir_to_watch):
    """Update timestamps of markdown files for next non-dev builds"""
    print("updating timestamps so next non-dev builds will process this post")
    for md_file in Path(dir_to_watch).glob('**/*.md'):
        os.utime(md_file, None)

class ChangeHandler(FileSystemEventHandler):
    def __init__(self, dir_to_watch):
        self.dir_to_watch = dir_to_watch
        self.filter = os.path.basename(dir_to_watch)
        # Add small delay to prevent multiple rapid fires
        self.last_modified = 0
        self.cooldown = 0.1

    def on_modified(self, event):
        if event.is_directory:
            return
        print(event)
        
        current_time = time.time()
        if current_time - self.last_modified < self.cooldown:
            return
        print(current_time,self.last_modified)

        
        print('filter = ', self.filter)
        # Run generate script
        try:
            subprocess.run([
                os.path.join("venv", "bin", "python"),
                "generate.py",
                "dev",
                self.filter
            ], check=True)
        except subprocess.CalledProcessError as e:
            print(f"Error running generate script: {e}")

        self.last_modified = time.time()

def main():
    if len(sys.argv) != 2:
        print_usage_and_exit()

    dir_to_watch = sys.argv[1]
    validate_directory(dir_to_watch)

    # Set up watchdog
    event_handler = ChangeHandler(dir_to_watch)
    observer = Observer()
    observer.schedule(event_handler, dir_to_watch, recursive=True)
    assets_dir = os.path.join(dir_to_watch, "assets")
    if Path(assets_dir).exists():
        observer.schedule(event_handler, assets_dir, recursive=False)
    observer.schedule(event_handler, "generate.py")

    print("watching...")
    observer.start()
    
    try:
        while True:
            time.sleep(0.1)
    except KeyboardInterrupt:
        observer.stop()
        update_timestamps(dir_to_watch)
    
    observer.join()

if __name__ == "__main__":
    main()
