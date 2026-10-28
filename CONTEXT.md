# Project Context

This project is used for crawling audio datasets, related metadata, and subtitles from TikTok for speech recognition (ASR) model training.

---

## Pipeline Architecture & Execution Flow

The full data collection pipeline consists of three sequential phases:

```
[ Phase 1: scrape_channels.py ]
         │ Discovers channel handles via hashtags
         ▼
    channels.json
         │
         ▼
[ Phase 2: filter_vietnamese_channels.py ]
         │ Verifies language (>= 2 Vietnamese videos)
         ▼
  Vietnamese_channels.json
         │
         ▼
[ Phase 3: crawler_v2.py ]
         │ Downloads MP4s & converts subtitles to VTT
         ▼
   output/<category>/
```

### 1. Channel Discovery (`scrape_channels.py`)
- **Role**: Stealth crawler that searches predefined hashtags using TikTok's web search UI, smoothly scrolls through video grids, and extracts unique channel handles.
- **Execution Command**:
  ```bash
  python scrape_channels.py
  ```
- **Output**: Writes channel handles organized by category into `channels.json`.

### 2. Vietnamese Channel Filter (`filter_vietnamese_channels.py`)
- **Role**: Verification filter that inspects channels from `channels.json`. Navigates to each channel via organic `<a>` tag clicks, intercepts the background `/item_list/` API payload using Chrome DevTools Protocol (CDP), and checks the `"textLanguage"` of the first 6 videos.
- **Language Criterion**: If at least 2 videos are `"vi"` (`vi_count >= 2`), the channel is accepted.
- **Empty Channel Refresh**: If the initial visit yields no posts or an empty `itemList`, it refreshes the page once (`driver.refresh()`) with human-like delays before making a final determination.
- **Evaluation Cache**: Tracks every inspected channel in `.checked_cache.json` so rejected channels are never re-checked.
- **Execution Command**:
  ```bash
  python filter_vietnamese_channels.py
  ```
- **Output**: Incrementally saves verified channels to `Vietnamese_channels.json` (with automatic atomic `.bak` backup).

### 3. Data Extraction (`crawler_v2.py`)
- **Role**: The core production crawler. Reads `Vietnamese_channels.json`, navigates through each verified channel, scrolls through posts, and intercepts background JSON payloads via CDP.
- **Targeted Categories**: Supports category-specific crawling (e.g. `marketing`, `fitness`, `cook`) or `all`.
- **Background Downloads**: When a valid post is intercepted, it spawns a lightweight thread to download the MP4 video and its matching subtitle container (`subtitle.mp4`).
- **Instant Post-Processing**: Immediately decodes `subtitle.mp4` into `subtitle.vtt` using `wsl ffmpeg`.
- **Execution Command**:
  ```bash
  python crawler_v2.py --category marketing
  # or crawl all categories sequentially:
  python crawler_v2.py --category all
  ```

---

## Multi-Browser Setup & Anti-Bot Operational Guidelines

> [!IMPORTANT]
> **Active Screen Rendering Requirement**:
> TikTok actively monitors window visibility, tab activity, DOM focus, and animation rendering to identify bots.
> - **DO NOT Alt-Tab away** or keep the windows hidden behind other applications.
> - The browsers must remain visible on screen to mimic a real user actively watching videos.

### Multi-Screen Operation (Up to 4 Simultaneous Browsers)
To achieve high crawl throughput without triggering anti-bot flags:
1. **Use a Secondary Monitor**: Connect an external monitor dedicated to crawling tasks.
2. **Arrange a 2×2 Grid**: Position up to 4 browser windows side-by-side (e.g. two on top, two on bottom) so each window is rendered and active simultaneously.
3. **Solve CAPTCHAs Quickly**: If a slider or puzzle CAPTCHA appears, the script pauses and triggers a Windows beep (`winsound.Beep`). You can immediately click into that quadrant, solve the puzzle manually, and the script will automatically detect resolution and resume crawling. This only occurs with filter_vietnamese_channels.py; crawler_v2.py does not encounter it.

### Chrome Profile Isolation
Chrome instances cannot share the same user data directory concurrently; sharing will cause locking errors or crash sessions.
- **Crawlers by Category**: `crawler_v2.py` isolates each category into its own persistent user profile:
  `chrome_profile/<category>/` (e.g. `chrome_profile/marketing`, `chrome_profile/fitness`).
- **Global / Filter Profile**: `filter_vietnamese_channels.py` and `scrape_channels.py` default to `chrome_profile/`.
- **Benefit**: Preserves independent logins, session cookies, and local storage per category without cross-process interference.

---

## Concurrency & Recommended Terminal Recipes

You can run multiple processes simultaneously across different terminal panes:
- **Verified Concurrent Pairing**: Running `filter_vietnamese_channels.py` alongside one or more `crawler_v2.py --category <name>` instances is fully supported because they operate on isolated Chrome profiles and distinct state files.
- **Caution with `scrape_channels.py`**: It is recommended to run `scrape_channels.py` independently prior to running the filter.

### Example: Running 4 Simultaneous Instances
Open separate PowerShell / CMD terminal windows and run:

```bash
# Terminal 1: Verification Filter
python filter_vietnamese_channels.py

# Terminal 2: Crawler - Marketing
python crawler_v2.py --category marketing

# Terminal 3: Crawler - Fitness
python crawler_v2.py --category fitness

# Terminal 4: Crawler - Cooking
python crawler_v2.py --category cook
```

---

## JSON Artifacts & Lifecycle Matrix

Below is the complete reference of all JSON state and cache files in this project:

| File Path                               | Created / Written By            | Read By                             | Write Mode            | Purpose & Description                                                 |
| :-------------------------------------- | :------------------------------ | :---------------------------------- | :-------------------- | :-------------------------------------------------------------------- |
| `channels.json`                         | `scrape_channels.py`            | `filter_vietnamese_channels.py`     | Update per hashtag    | Discovered channel handles grouped by category from hashtag search.   |
| `Vietnamese_channels.json`              | `filter_vietnamese_channels.py` | `crawler_v2.py`, `launcher.py`     | Atomic rewrite (.bak) | Filtered channels with >= 2 Vietnamese videos (crawler input).        |
| `.checked_cache.json`                   | `filter_vietnamese_channels.py` | `filter_vietnamese_channels.py`    | Atomic rewrite (.bak) | Cache of all evaluated channels to prevent redundant re-evaluations.  |
| `categories/<category>.json`            | `crawler_v2.py`                 | `recover_channels.py`              | Overwrite on startup  | Target channels snapshot for a category when crawler launches.        |
| `crawled_cache_<category>.json`         | `crawler_v2.py`                 | `crawler_v2.py`, `recover_channels`| Append on completion  | Completed channels for a category to support pause and resumption.    |
| `output/<category>/metadata.json`       | `crawler_v2.py`                 | `crawler_v2.py`, `clean_metadata`  | Append on download    | Map of TikTok item_ids to sequential IDs & metadata (deduplication). |
| `output/<category>/rejected_posts.json` | `crawler_v2.py`                 | `crawler_v2.py`                    | Append on rejection   | IDs of posts rejected during crawl (wrong language or no subtitles).  |

---

## Deduplication & State Tracking

Deduplication operates at both post and channel levels to support seamless pausing and resumption:

- **Post Deduplication**: The crawler maintains in-memory tracking via `processed_items`, which is the union of:
  - `output/<category>/metadata.json`: Accepted and successfully downloaded TikTok posts mapped to sequential IDs.
  - `output/<category>/rejected_posts.json`: Posts evaluated but rejected (e.g. wrong language or missing subtitles).
  When traversing channels, newly intercepted posts found in `processed_items` are immediately skipped in memory without re-downloading.
- **Channel-Level Resumption**: Completed channels are recorded in `crawled_cache_<category>.json`, ensuring crawler restarts skip already finished channels entirely.

---

## Anti-Bot Stealth Features

- **UI Navigation**: Instead of using direct `driver.get(url)` jumps (which triggers TikTok CAPTCHAs), scripts use TikTok's search bar UI and inject hidden `<a>` tags for organic click navigation.
- **Human-like Scrolling**: Hashtag grids and channel pages are scrolled continuously and smoothly with randomized pixel steps and micro-halts, avoiding instant `scrollTo(bottom)` detections.
- **CAPTCHA Hooking**: A `handle_captcha()` loop constantly monitors the DOM for verification iframes or puzzle sliders. If triggered, the bot pauses indefinitely and plays a Windows system beep, allowing manual solving without crashing the pipeline.

---

## Output Structure

The crawler organizes data cleanly by category, channel handle, and sequential ID:
```
output/
└── <category>/
    ├── metadata.json           # Map of accepted TikTok item_ids to sequential IDs
    ├── rejected_posts.json     # Map of evaluated but rejected post IDs
    ├── @channel_handle_1/
    │   ├── 1/
    │   │   ├── 1.mp4           # Downloaded video
    │   │   ├── subtitle.mp4    # Raw subtitle container
    │   │   ├── subtitle.vtt    # Extracted WebVTT subtitle
    │   │   └── info.json       # Extracted URLs, IDs, and metadata
    │   ├── 2/
    │   │   ...
    ├── @channel_handle_2/
```

---

## Helper & Maintenance Scripts

- **`count_duration.py`**: High-performance multi-threaded utility using `wsl ffprobe` to scan the `output/` directory and calculate the exact total duration of downloaded audio/video.
  - Skips standalone subtitle files and only counts valid folders containing a non-empty `subtitle.vtt`.
  - Usage:
    ```bash
    # Scan all categories
    python count_duration.py
    # Scan a specific category
    python count_duration.py --category marketing
    ```
- **`launcher.py`**: Automation script that reads `Vietnamese_channels.json` and launches a separate background process for each category using `subprocess.Popen([sys.executable, "crawler_v2.py", "--category", cat])`.
- **`clean_metadata.py`**: Sanitation utility that inspects `output/<category>/metadata.json`, checks if the corresponding folder (`output/<category>/@channel/<seq_id>/`) exists on disk, and removes orphaned or missing entries.
  - Usage:
    ```bash
    python clean_metadata.py --category marketing
    ```
- **`recover_channels.py`**: Disaster recovery utility that reconstructs `Vietnamese_channels.json` by aggregating verified channels from `categories/*.json`, `crawled_cache_*.json`, and existing `output/` directories with automatic `.bak` backups.
- **`prune_checked_cache.py`**: Cache management utility that prunes `.checked_cache.json` down to only confirmed channels in `Vietnamese_channels.json`, allowing `filter_vietnamese_channels.py` to safely re-filter all unconfirmed or missing channels without re-checking already verified ones.

---

## Technical Notes

- **CDP Interception & Buffer Sizing**: Scripts monitor Chrome's performance logs and wait for `Network.loadingFinished` before executing `Network.getResponseBody`. To avoid `"No resource with given identifier found"` race conditions when Chrome purges log bodies, `crawler_v2.py` initializes the CDP Network domain with explicit buffer sizes: 100 MB total and 20 MB per individual resource.
- **Subtitles via FFMPEG**: Subtitles are often downloaded as MP4 containers. The script automatically converts them using: `wsl ffmpeg -y -i <subtitle.mp4> -map 0:s:0 <subtitle.vtt>`. This relies on Windows Subsystem for Linux (WSL).
- **Video Format**: TikTok serves videos using HEVC (H.265). Windows media players may show unsupported codec errors for the video, but audio plays correctly. Use VLC or `ffplay` for playback.
- **Ctrl+C Handling**: The crawler uses the `signal` library to forcefully interrupt Python's blocking threads on Windows. A single `Ctrl+C` will instantly kill all background downloads, close the browser, and exit.
