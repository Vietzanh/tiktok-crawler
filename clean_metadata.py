import os
import json
import argparse
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(description="Clean up metadata.json by removing missing folders.")
    parser.add_argument("--category", required=True, help="Target category (e.g., marketing)")
    args = parser.parse_args()

    category = args.category.lower()
    output_dir = Path("output") / category
    metadata_file = output_dir / "metadata.json"

    if not metadata_file.exists():
        print(f"Metadata file not found: {metadata_file}")
        return

    with open(metadata_file, "r") as f:
        try:
            metadata = json.load(f)
        except json.JSONDecodeError:
            print("Invalid JSON in metadata file.")
            return

    initial_count = len(metadata)
    items_to_remove = []

    for item_id, meta_val in metadata.items():
        if isinstance(meta_val, dict):
            seq_id = meta_val.get("seq_id")
            channel = meta_val.get("channel")
            if seq_id is not None and channel:
                target_folder = output_dir / channel / str(seq_id)
                if not target_folder.exists():
                    items_to_remove.append(item_id)
            else:
                print(f"Skipping malformed entry for {item_id}: {meta_val}")
        else:
            # Legacy format - user specified they are starting fresh
            print(f"Skipping legacy integer entry for {item_id}")

    for item_id in items_to_remove:
        del metadata[item_id]

    if items_to_remove:
        with open(metadata_file, "w") as f:
            json.dump(metadata, f, indent=4)
        print(f"Removed {len(items_to_remove)} missing items. Metadata size reduced from {initial_count} to {len(metadata)}.")
    else:
        print(f"All {initial_count} items are valid. No cleanup needed.")

if __name__ == "__main__":
    main()
