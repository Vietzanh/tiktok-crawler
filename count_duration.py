import os
import subprocess
import argparse
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

def to_wsl_path(win_path):
    abs_path = str(win_path.resolve())
    drive, tail = os.path.splitdrive(abs_path)
    drive_letter = drive.replace(":", "").lower()
    tail = tail.replace("\\", "/")
    return f"/mnt/{drive_letter}{tail}"

def is_valid_dataset_folder(folder_path):
    """Check if folder contains a valid subtitle.vtt (exists and > 0 bytes)."""
    vtt_path = Path(folder_path) / "subtitle.vtt"
    return vtt_path.exists() and vtt_path.stat().st_size > 0

def get_duration(file_path):
    # Skip subtitle files, we only want the main videos
    if file_path.name == "subtitle.mp4":
        return 0.0
    
    wsl_path = to_wsl_path(file_path)
    cmd = [
        "wsl", "ffprobe", 
        "-v", "error", 
        "-show_entries", "format=duration", 
        "-of", "default=noprint_wrappers=1:nokey=1", 
        wsl_path
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            return float(result.stdout.strip())
    except Exception:
        pass
    return 0.0

def format_duration(seconds):
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    return f"{hours}h {minutes}m {secs}s"

def main():
    parser = argparse.ArgumentParser(description="Count total duration of crawled videos.")
    parser.add_argument("--category", default=None, help="Target category (e.g., marketing). If none, scans all categories.")
    args = parser.parse_args()

    output_dir = Path("output")
    if not output_dir.exists():
        print(f"Folder {output_dir} does not exist.")
        return

    # Map of category -> list of mp4 files
    category_files = {}
    skipped_count = 0

    def collect_videos(start_dir):
        nonlocal skipped_count
        found_videos = []
        for root, _, files in os.walk(start_dir):
            mp4_files = [f for f in files if f.endswith(".mp4") and f != "subtitle.mp4"]
            if not mp4_files:
                continue
                
            if is_valid_dataset_folder(root):
                for f in mp4_files:
                    found_videos.append(Path(root) / f)
            else:
                skipped_count += len(mp4_files)
        return found_videos

    if args.category:
        cat_dir = output_dir / args.category.lower()
        if cat_dir.exists():
            category_files[args.category] = collect_videos(cat_dir)
        else:
            print(f"Category folder {cat_dir} does not exist.")
            return
    else:
        # Scan all subfolders in output/
        for item in output_dir.iterdir():
            if item.is_dir():
                cat_name = item.name
                if cat_name == "matched":
                    continue # ignore old matched dir
                
                category_files[cat_name] = collect_videos(item)
                            
    # Remove empty categories
    category_files = {k: v for k, v in category_files.items() if v}

    if not category_files:
        print("No video files found.")
        return

    total_files = sum(len(v) for v in category_files.values())
    print(f"Dataset Health: {total_files} valid videos, {skipped_count} skipped (missing/empty subtitle.vtt).")
    if total_files == 0:
        return
        
    print(f"Calculating durations via WSL for {len(category_files)} categories...\n")

    category_durations = {cat: 0.0 for cat in category_files}
    grand_total_seconds = 0.0

    with ThreadPoolExecutor(max_workers=10) as executor:
        for cat, mp4_files in category_files.items():
            futures = {executor.submit(get_duration, p): p for p in mp4_files}
            processed = 0
            for future in as_completed(futures):
                duration = future.result()
                category_durations[cat] += duration
                grand_total_seconds += duration
                processed += 1
                
                if processed % 10 == 0 or processed == len(mp4_files):
                    print(f"[{cat}] Processed {processed}/{len(mp4_files)} videos...", end='\r')
            if mp4_files:
                print(f"[{cat}] Processed {len(mp4_files)}/{len(mp4_files)} videos.      ")

    print(f"\n==================================================")
    print("DURATION SUMMARY:")
    for cat, duration in category_durations.items():
        print(f"  - {cat.capitalize()}: {format_duration(duration)}")
    print(f"==================================================")
    print(f"GRAND TOTAL: {format_duration(grand_total_seconds)}")
    print(f"==================================================")

if __name__ == "__main__":
    main()
