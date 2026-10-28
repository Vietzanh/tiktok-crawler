import os
import json
import subprocess
import sys

def main():
    channels_file = "Vietnamese_channels.json"
    
    if not os.path.exists(channels_file):
        print(f"Error: {channels_file} not found.")
        sys.exit(1)
        
    with open(channels_file, "r", encoding="utf-8") as f:
        data = json.load(f)
        
    categories = list(data.keys())
    print(f"Found {len(categories)} categories: {', '.join(categories)}")
    
    processes = []
    for cat in categories:
        print(f"Launching crawler for category: {cat}")
        # Launch each crawler in the background as an independent process
        p = subprocess.Popen([sys.executable, "crawler_v2.py", "--category", cat])
        processes.append(p)
        
    print(f"\nSuccessfully launched {len(processes)} background crawlers.")
    print("Note: Output will be mixed in this console since it's the 'Quick and Dirty' approach.")
    print("To terminate them, you can use Task Manager or close this console window.")

if __name__ == "__main__":
    main()
