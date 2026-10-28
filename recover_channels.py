import json
import os
import shutil
from pathlib import Path

def atomic_save_json(filepath, data, make_backup=True, indent=4):
    filepath = Path(filepath).resolve()
    temp_path = filepath.with_name(f"{filepath.name}.tmp")
    backup_path = filepath.with_name(f"{filepath.name}.bak")
    
    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=indent, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
        
    if make_backup and filepath.exists() and filepath.stat().st_size > 0:
        shutil.copy2(filepath, backup_path)
        
    os.replace(temp_path, filepath)

def recover_channels():
    base_dir = Path(__file__).parent.resolve()
    target_file = base_dir / "Vietnamese_channels.json"
    
    current_data = {}
    if target_file.exists() and target_file.stat().st_size > 0:
        try:
            with open(target_file, "r", encoding="utf-8") as f:
                current_data = json.load(f)
        except Exception as e:
            print(f"Warning: Could not read existing {target_file}: {e}")
            
    # Load channels.json to know the expected categories
    channels_file = base_dir / "channels.json"
    categories = []
    if channels_file.exists():
        with open(channels_file, "r", encoding="utf-8") as f:
            categories = list(json.load(f).keys())
    if not categories:
        categories = ["marketing", "fitness", "cook", "beauty", "shopping"]
        
    recovered = {cat: set() for cat in categories}
    
    # 1. Preserve existing channels from Vietnamese_channels.json
    for cat, ch_list in current_data.items():
        if cat in recovered:
            recovered[cat].update(ch_list)
        else:
            recovered[cat] = set(ch_list)
            
    # 2. Recover from categories/<category>.json
    categories_dir = base_dir / "categories"
    if categories_dir.exists():
        for json_path in categories_dir.glob("*.json"):
            cat_name = json_path.stem.lower()
            try:
                with open(json_path, "r", encoding="utf-8") as f:
                    cat_data = json.load(f)
                    if isinstance(cat_data, dict):
                        for k, v in cat_data.items():
                            if isinstance(v, list):
                                target_cat = k.lower()
                                if target_cat not in recovered:
                                    recovered[target_cat] = set()
                                recovered[target_cat].update(v)
            except Exception as e:
                print(f"Error reading {json_path}: {e}")

    # 3. Recover from crawled_cache_<category>.json
    for cache_path in base_dir.glob("crawled_cache_*.json"):
        # Format: crawled_cache_<category>.json
        cat_name = cache_path.stem.replace("crawled_cache_", "").lower()
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                channels = json.load(f)
                if isinstance(channels, list):
                    if cat_name not in recovered:
                        recovered[cat_name] = set()
                    recovered[cat_name].update(channels)
        except Exception as e:
            print(f"Error reading {cache_path}: {e}")

    # 4. Recover from output/<category>/ channel directories
    output_dir = base_dir / "output"
    if output_dir.exists():
        for cat_dir in output_dir.iterdir():
            if cat_dir.is_dir():
                cat_name = cat_dir.name.lower()
                if cat_name not in recovered:
                    recovered[cat_name] = set()
                for item in cat_dir.iterdir():
                    if item.is_dir() and item.name.startswith("@"):
                        recovered[cat_name].add(item.name)

    # Format output as sorted lists
    final_output = {cat: sorted(list(recovered[cat])) for cat in categories}
    
    print("\n--- Recovery Summary ---")
    for cat, chs in final_output.items():
        print(f"  {cat}: {len(chs)} channels")
        
    atomic_save_json(target_file, final_output, make_backup=True, indent=4)
    print(f"\nSuccessfully saved recovered channels to {target_file}")
    print(f"Backup saved to {target_file.with_name(target_file.name + '.bak')}")

if __name__ == "__main__":
    recover_channels()
