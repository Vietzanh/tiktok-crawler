import os
import json
import shutil
import argparse
from pathlib import Path

def atomic_save_json(filepath, data, make_backup=True, indent=None):
    """
    Safely writes data to a temporary file, flushes/syncs to disk,
    optionally creates/refreshes a .bak backup, and atomically renames to filepath.
    """
    target = Path(filepath).resolve()
    temp_file = target.with_name(f"{target.name}.tmp")
    backup_file = target.with_name(f"{target.name}.bak")

    try:
        with open(temp_file, "w", encoding="utf-8") as f:
            if indent is not None:
                json.dump(data, f, indent=indent, ensure_ascii=False)
            else:
                json.dump(data, f, ensure_ascii=False)
            f.flush()
            os.fsync(f.fileno())

        if make_backup and target.exists() and target.stat().st_size > 0:
            shutil.copy2(target, backup_file)

        os.replace(temp_file, target)
    except Exception as e:
        if temp_file.exists():
            try:
                temp_file.unlink()
            except Exception:
                pass
        raise e

def prune_checked_cache(cache_file=".checked_cache.json",
                       vietnamese_file="Vietnamese_channels.json",
                       channels_file="channels.json",
                       dry_run=False):
    base_dir = Path(__file__).parent.resolve()
    cache_path = base_dir / cache_file
    vietnamese_path = base_dir / vietnamese_file
    channels_path = base_dir / channels_file

    if not vietnamese_path.exists():
        print(f"Error: {vietnamese_file} not found!")
        return

    # 1. Load accepted channels from Vietnamese_channels.json
    with open(vietnamese_path, "r", encoding="utf-8") as f:
        vietnamese_data = json.load(f)

    accepted_channels = set()
    category_accepted = {}
    for cat, channels in vietnamese_data.items():
        if isinstance(channels, list):
            accepted_channels.update(channels)
            category_accepted[cat] = set(channels)

    # 2. Load existing .checked_cache.json
    checked_channels = set()
    if cache_path.exists() and cache_path.stat().st_size > 0:
        with open(cache_path, "r", encoding="utf-8") as f:
            try:
                checked_channels = set(json.load(f))
            except json.JSONDecodeError:
                print(f"Warning: {cache_file} was empty or corrupted.")

    # 3. Load channels.json to compute category-level stats
    channels_data = {}
    if channels_path.exists():
        with open(channels_path, "r", encoding="utf-8") as f:
            channels_data = json.load(f)

    # 4. Prune: New cache contains only channels that are currently accepted
    # Any channel not currently in Vietnamese_channels.json is removed from cache,
    # making it immediately eligible for re-evaluation by filter_vietnamese_channels.py.
    new_checked_cache = set(accepted_channels)
    pruned_channels = checked_channels - new_checked_cache

    print("==================================================")
    print("           CHECKED CACHE PRUNING SUMMARY          ")
    print("==================================================")
    print(f"Initial channels in {cache_file}:      {len(checked_channels)}")
    print(f"Accepted channels retained in cache:    {len(new_checked_cache)}")
    print(f"Channels removed (re-queued for check): {len(pruned_channels)}")
    print("--------------------------------------------------")
    print("Category Breakdown (from channels.json):")
    print(f"{'Category':<15} | {'Total':<8} | {'Accepted':<10} | {'Eligible to Re-check':<20}")
    print("-" * 60)

    for cat, total_chs in channels_data.items():
        total_count = len(total_chs)
        accepted_count = len(category_accepted.get(cat, set()))
        to_check = sum(1 for ch in total_chs if ch not in new_checked_cache)
        print(f"{cat:<15} | {total_count:<8} | {accepted_count:<10} | {to_check:<20}")

    print("==================================================")

    if dry_run:
        print("\n[DRY RUN] No files were modified. Run without --dry-run to apply changes.")
        return

    # 5. Save updated cache atomically with backup
    atomic_save_json(cache_path, sorted(list(new_checked_cache)), make_backup=True)
    print(f"\n[SUCCESS] Successfully pruned {cache_file}!")
    print(f"Backup saved to: {cache_path}.bak")
    print(f"You can now run `python filter_vietnamese_channels.py` to re-filter unconfirmed channels.")

def main():
    parser = argparse.ArgumentParser(
        description="Prune .checked_cache.json to re-queue channels not currently in Vietnamese_channels.json"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without modifying .checked_cache.json"
    )
    parser.add_argument(
        "--cache-file",
        default=".checked_cache.json",
        help="Path to checked cache JSON file"
    )
    parser.add_argument(
        "--vietnamese-file",
        default="Vietnamese_channels.json",
        help="Path to Vietnamese channels JSON file"
    )
    parser.add_argument(
        "--channels-file",
        default="channels.json",
        help="Path to input channels JSON file"
    )
    args = parser.parse_args()

    prune_checked_cache(
        cache_file=args.cache_file,
        vietnamese_file=args.vietnamese_file,
        channels_file=args.channels_file,
        dry_run=args.dry_run
    )

if __name__ == "__main__":
    main()
