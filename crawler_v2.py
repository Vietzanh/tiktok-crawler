import os
import sys
import json
import time
import random
import logging
import hashlib
import threading
import subprocess
import requests
import base64
import signal
from pathlib import Path
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TikTokCrawler:
    # ========================= CONFIGURABLE VARIABLES =========================
    CHANNELS_JSON_FILE = "Vietnamese_channels.json"

    # Number of posts to extract per channel
    POSTS_PER_CHANNEL = 10000

    # If no new posts are captured within this many seconds, skip to next channel
    CHANNEL_TIMEOUT = 200

    # Wait time (seconds) after navigating to a channel before clicking first video
    CHANNEL_WAIT = 10

    # Scroll timing
    SCROLL_DELAY_MIN = 5.0
    SCROLL_DELAY_MAX = 10.0
    
    # Preferred subtitle language (e.g. "vi" for Vietnamese, "en" for English)
    # The crawler will prioritize this language when multiple subtitles are available.
    PREFERRED_SUBTITLE_LANG = "vi"
    
    # Channel quality evaluation
    EVALUATION_POST_COUNT = 50
    MAX_REJECTED_TOLERANCE = 40

    # Navigation retry settings
    # Total seconds (including CHANNEL_WAIT) before a page load/click attempt times out
    NAVIGATION_TIMEOUT = 50
    # How many times to refresh and retry if clicking the first video fails
    MAX_NAVIGATION_RETRIES = 2

    # CDP network buffer sizes (bytes) to keep response bodies available longer.
    # Reduces "No resource with given identifier found" errors when processing logs.
    # 100 MB total, 20 MB per individual resource.
    CDP_MAX_TOTAL_BUFFER_SIZE    = 100 * 1024 * 1024  # 100 MB
    CDP_MAX_RESOURCE_BUFFER_SIZE =  20 * 1024 * 1024  #  20 MB
    # ==========================================================================

    def __init__(self, category="all"):
        load_dotenv()

        self.TARGET_CATEGORY = category
        self.channel_list = self._load_target_channels()
        
        self.crawled_cache_file = Path(f"crawled_cache_{self.TARGET_CATEGORY}.json")
        self.crawled_channels = self._load_crawled_cache()

        # Output directly to category folder
        self.output_dir = Path("output") / self.TARGET_CATEGORY.lower()
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.metadata_file = self.output_dir / "metadata.json"
        self.metadata = self.load_metadata()
        
        self.rejected_file = self.output_dir / "rejected_posts.json"
        self.rejected_items = self._load_rejected()

        self.processed_items = set(self.metadata.keys()).union(self.rejected_items.keys())  # Track TikTok item_ids
        self.known_urls = set()  # Track parsed JSON API URLs

        self.captured_count = 0  # Count for current channel
        self.cookies_dict = {}
        self.request_id_map = {} # Maps CDP requestId -> URL
        self.current_channel = None  # e.g. "@heu.56mm"
        self.current_channel_seq_ids = []  # Track seq_ids for current channel (for ffmpeg)

        options = webdriver.ChromeOptions()

        # Enable persistent local profile to save logins and cookies
        if self.TARGET_CATEGORY.lower() != "all":
            profile_dir = Path(f"chrome_profile/{self.TARGET_CATEGORY}").resolve()
        else:
            profile_dir = Path("chrome_profile").resolve()
            
        options.add_argument(f"user-data-dir={profile_dir}")

        options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])

        self.driver = webdriver.Chrome(options=options)
        
        # Explicitly enable CDP Network domain so Chrome caches response bodies
        self.driver.execute_cdp_cmd('Network.enable', {
            'maxTotalBufferSize':    self.CDP_MAX_TOTAL_BUFFER_SIZE,
            'maxResourceBufferSize': self.CDP_MAX_RESOURCE_BUFFER_SIZE,
        })
        logger.info(
            f"CDP Network domain enabled "
            f"(buffer: {self.CDP_MAX_TOTAL_BUFFER_SIZE // (1024*1024)} MB total, "
            f"{self.CDP_MAX_RESOURCE_BUFFER_SIZE // (1024*1024)} MB per resource)."
        )

    def _load_target_channels(self):
        if not os.path.exists(self.CHANNELS_JSON_FILE):
            logger.error(f"Channels file '{self.CHANNELS_JSON_FILE}' not found! Run scrape_channels.py first.")
            return []
            
        with open(self.CHANNELS_JSON_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        channels = []
        if self.TARGET_CATEGORY.lower() == "all":
            logger.info("TARGET_CATEGORY is 'all'. Crawling all categories.")
            for cat, cat_channels in data.items():
                channels.extend(cat_channels)
        else:
            if self.TARGET_CATEGORY in data:
                logger.info(f"TARGET_CATEGORY is '{self.TARGET_CATEGORY}'.")
                channels.extend(data[self.TARGET_CATEGORY])
                
                # Write specifically to categories/ folder
                cat_dir = Path("categories")
                cat_dir.mkdir(exist_ok=True)
                with open(cat_dir / f"{self.TARGET_CATEGORY}.json", "w", encoding="utf-8") as f:
                    json.dump({self.TARGET_CATEGORY: channels}, f, indent=4)
            else:
                logger.warning(f"Category '{self.TARGET_CATEGORY}' not found in {self.CHANNELS_JSON_FILE}.")
                
        unique_channels = list(dict.fromkeys(channels))
        return unique_channels

    def _load_crawled_cache(self):
        if self.crawled_cache_file.exists():
            with open(self.crawled_cache_file, "r") as f:
                try:
                    return set(json.load(f))
                except json.JSONDecodeError:
                    return set()
        return set()

    def _save_crawled_cache(self):
        with open(self.crawled_cache_file, "w") as f:
            json.dump(list(self.crawled_channels), f, indent=4)

    def load_metadata(self):
        if self.metadata_file.exists():
            with open(self.metadata_file, "r") as f:
                try:
                    return json.load(f)
                except json.JSONDecodeError:
                    return {}
        return {}

    def save_metadata(self):
        with open(self.metadata_file, "w") as f:
            json.dump(self.metadata, f, indent=4)

    def _load_rejected(self):
        if self.rejected_file.exists():
            with open(self.rejected_file, "r") as f:
                try:
                    return json.load(f)
                except json.JSONDecodeError:
                    return {}
        return {}

    def _save_rejected(self):
        with open(self.rejected_file, "w") as f:
            json.dump(self.rejected_items, f, indent=4)

    def get_next_sequential_id(self):
        if not self.metadata:
            return 1
        max_id = 0
        for v in self.metadata.values():
            if isinstance(v, dict):
                max_id = max(max_id, v.get("seq_id", 0))
            elif isinstance(v, int):
                max_id = max(max_id, v)
        return max_id + 1

    def _update_cookies(self):
        """Extract live cookies from Selenium for the Python downloader."""
        cookies = self.driver.get_cookies()
        self.cookies_dict = {c['name']: c['value'] for c in cookies}

    def _download_file(self, url, filepath):
        """Download a file cleanly in the background using Python requests."""
        if not url:
            return False
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Referer': 'https://www.tiktok.com/'
            }
            resp = requests.get(url, headers=headers, cookies=self.cookies_dict, stream=True, timeout=20)
            resp.raise_for_status()

            with open(filepath, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            return True
        except Exception as e:
            logger.error(f"Download failed for {filepath.name}: {e}")
            return False

    def _download_post_data(self, item_id, video_url, subtitle_url, channel_handle):
        """Background task to download video and subtitle simultaneously."""
        meta_val = self.metadata.get(item_id)
        if not meta_val:
            return
        seq_id = meta_val["seq_id"] if isinstance(meta_val, dict) else meta_val
        
        channel_safe = channel_handle if channel_handle else "unknown"
        target_folder = self.output_dir / channel_safe / str(seq_id)
        target_folder.mkdir(parents=True, exist_ok=True)

        logger.info(f"Downloading Post {item_id} -> Folder '{seq_id}'")

        # Download Video
        if video_url:
            self._download_file(video_url, target_folder / f"{seq_id}.mp4")

        # Download Subtitle (Always named subtitle.mp4)
        has_subtitle = False
        if subtitle_url:
            has_subtitle = self._download_file(subtitle_url, target_folder / "subtitle.mp4")
            if has_subtitle:
                self._decode_single_subtitle(target_folder / "subtitle.mp4", target_folder / "subtitle.vtt", seq_id)

        # Save info.json
        info = {
            "item_id": item_id,
            "channel": self.current_channel,
            "video_url": video_url,
            "subtitle_url": subtitle_url,
            "has_subtitle": has_subtitle
        }
        with open(target_folder / "info.json", "w", encoding="utf-8") as f:
            json.dump(info, f, indent=4)

        logger.info(f"Completed downloads for Folder '{seq_id}'")

    def _process_item_list_json(self, json_body):
        """Parse JSON directly in memory and dispatch downloads.
        Only processes items that belong to the current channel.
        Returns the number of newly captured posts from this JSON.
        """
        newly_captured = 0
        try:
            data = json.loads(json_body)
            for item in data.get("itemList", []):
                if self.captured_count >= self.POSTS_PER_CHANNEL:
                    break

                item_id = str(item.get("id"))
                if not item_id or item_id in self.processed_items:
                    continue

                # Filter: only accept posts from the current channel
                author = item.get("author", {})
                author_unique_id = author.get("uniqueId", "")
                # Compare without '@' prefix
                current_handle = self.current_channel.lstrip("@") if self.current_channel else ""
                if author_unique_id.lower() != current_handle.lower():
                    logger.debug(f"Skipped item {item_id}: author '{author_unique_id}' != channel '{current_handle}'")
                    continue

                video_data = item.get("video", {})

                # Extract Video URL
                video_url = None
                for bitrate in video_data.get("bitrateInfo", []):
                    urls = bitrate.get("PlayAddr", {}).get("UrlList", [])
                    if urls:
                        video_url = urls[0]
                        break
                if not video_url:
                    urls = video_data.get("PlayAddrStruct", {}).get("UrlList", [])
                    if urls:
                        video_url = urls[0]

                # Extract Subtitle URL - prioritize PREFERRED_SUBTITLE_LANG
                subtitle_url = None
                all_captions = []  # Collect all available captions with their language info
                
                cla_info = video_data.get("claInfo", {})
                for caption in cla_info.get("captionInfos", []):
                    lang = (caption.get("lang", "") or caption.get("language", "") 
                            or caption.get("languageID", "") or caption.get("languageCodeName", "")).lower()
                    is_original = caption.get("isOriginal", False) or caption.get("is_original", False)
                    url = caption.get("url") or (caption.get("urlList", [None]) or [None])[0]
                    if url:
                        all_captions.append({"lang": lang, "url": url, "is_original": is_original, "source": "claInfo"})

                for subtitle in video_data.get("subtitleInfos", []):
                    lang = (subtitle.get("LanguageCodeName", "") or subtitle.get("languageCodeName", "")
                            or subtitle.get("Language", "") or subtitle.get("language", "")).lower()
                    is_original = subtitle.get("IsOriginal", False) or subtitle.get("is_original", False)
                    url = subtitle.get("Url") or subtitle.get("url")
                    if url:
                        all_captions.append({"lang": lang, "url": url, "is_original": is_original, "source": "subtitleInfos"})
                
                # Only accept subtitles matching PREFERRED_SUBTITLE_LANG
                pref = self.PREFERRED_SUBTITLE_LANG.lower()
                for cap in all_captions:
                    if pref in cap["lang"]:
                        subtitle_url = cap["url"]
                        logger.debug(f"Item {item_id}: selected subtitle lang='{cap['lang']}' (preferred match)")
                        break
                
                if not subtitle_url and all_captions:
                    logger.debug(f"Item {item_id}: No matching '{pref}' subtitle found among {len(all_captions)} available.")
                
                if not subtitle_url:
                    logger.info(f"Skipped item {item_id}: missing '{pref}' subtitle.")
                    self.rejected_items[item_id] = f"missing '{pref}' subtitle"
                    self.processed_items.add(item_id)
                    self._save_rejected()
                    self.current_channel_evaluated += 1
                    self.current_channel_rejected_count += 1
                    continue

                if video_url:
                    # Update metadata
                    seq_id = self.get_next_sequential_id()
                    self.metadata[item_id] = {
                        "seq_id": seq_id,
                        "channel": self.current_channel
                    }
                    self.processed_items.add(item_id)
                    self.save_metadata()

                    self.captured_count += 1
                    newly_captured += 1
                    self.current_channel_evaluated += 1
                    self.current_channel_seq_ids.append(seq_id)
                    logger.info(f"[{self.current_channel}] Found new video [{seq_id}] "
                                f"(Channel progress: {self.captured_count}/{self.POSTS_PER_CHANNEL})")

                    # Dispatch background download thread
                    threading.Thread(
                        target=self._download_post_data,
                        args=(item_id, video_url, subtitle_url, self.current_channel),
                        daemon=True
                    ).start()
                else:
                    logger.debug(f"Skipped item {item_id}: no video URL found")

        except Exception as e:
            logger.error(f"Error parsing JSON: {e}")
        return newly_captured

    def _capture_item_lists_cdp(self):
        """Use Chrome DevTools Protocol to capture item_list responses instantly.
        Returns the number of newly captured posts.
        """
        try:
            logs = self.driver.get_log('performance')
        except Exception as e:
            logger.debug(f"Failed to get performance logs: {e}")
            return 0

        self._update_cookies()  # Refresh cookies just before processing
        total_new = 0
        item_list_count = 0
        
        if logs:
            logger.debug(f"Processing {len(logs)} performance log entries...")

        for entry in logs:
            try:
                log_msg = json.loads(entry['message'])['message']
                method = log_msg['method']
                
                # 1. Track the URL when response starts
                if method == 'Network.responseReceived':
                    url = log_msg['params']['response']['url']
                    if '/item_list/' in url:
                        req_id = log_msg['params']['requestId']
                        self.request_id_map[req_id] = url
                        logger.debug(f"Detected item_list started (requestId={req_id})")

                # 2. Extract the body only when it finishes loading
                elif method == 'Network.loadingFinished':
                    req_id = log_msg['params']['requestId']
                    if req_id in self.request_id_map:
                        url = self.request_id_map[req_id]
                        if url not in self.known_urls:
                            item_list_count += 1
                            try:
                                response_body = self.driver.execute_cdp_cmd('Network.getResponseBody', {'requestId': req_id})
                            except Exception as e:
                                logger.warning(f"CDP getResponseBody FAILED for {url[:100]}...: {e}")
                                continue
                                
                            body = response_body.get('body')
                            is_b64 = response_body.get('base64Encoded', False)

                            if body:
                                if is_b64:
                                    body = base64.b64decode(body).decode('utf-8', errors='ignore')

                                self.known_urls.add(url)
                                logger.info(f"Successfully retrieved JSON body ({len(body)} chars)")
                                total_new += self._process_item_list_json(body)
                            else:
                                logger.warning(f"CDP returned empty body for requestId={req_id}")
                                
                        # Cleanup map
                        del self.request_id_map[req_id]

            except Exception as e:
                logger.debug(f"Error processing log entry: {e}")
        
        if item_list_count > 0:
            logger.info(f"CDP sweep: found {item_list_count} item_list responses, captured {total_new} new posts")
        return total_new

    def _navigate_to_channel(self, channel_handle):
        """Navigate to a TikTok channel page, wait, then click the first video.
        
        Retries up to MAX_NAVIGATION_RETRIES times by refreshing the page if
        clicking the first video fails within NAVIGATION_TIMEOUT seconds.
        Returns True if the first video was clicked, False if all retries failed.
        """
        channel_url = f"https://www.tiktok.com/{channel_handle}"

        for attempt in range(1, self.MAX_NAVIGATION_RETRIES + 1):
            nav_start = time.time()
            logger.info(f"Navigating to channel: {channel_url} (attempt {attempt}/{self.MAX_NAVIGATION_RETRIES})")
            self.driver.get(channel_url)

            logger.info(f"Waiting {self.CHANNEL_WAIT}s for channel page to load...")
            time.sleep(self.CHANNEL_WAIT)

            # Process any CDP logs accumulated during page load
            initial_captures = self._capture_item_lists_cdp()
            if initial_captures > 0:
                logger.info(f"Captured {initial_captures} initial posts during page load.")

            # How much time is left in the NAVIGATION_TIMEOUT budget?
            elapsed = time.time() - nav_start
            remaining = self.NAVIGATION_TIMEOUT - elapsed
            if remaining <= 0:
                logger.warning(f"NAVIGATION_TIMEOUT ({self.NAVIGATION_TIMEOUT}s) exhausted before click attempt.")
                continue

            # Try clicking the first video within the remaining budget
            click_success = False
            try:
                WebDriverWait(self.driver, remaining).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, '[data-e2e="user-post-item-list"]'))
                )
                first_video = self.driver.find_element(By.CSS_SELECTOR, '[id^="grid-item-container-0"]')
                first_video.click()
                logger.info("Clicked the first video in the channel grid.")
                time.sleep(3)  # Let the video player open
                click_success = True
            except Exception as e:
                logger.error(f"Attempt {attempt}: Failed to click first video: {e}. Trying anchor fallback...")
                try:
                    first_link = self.driver.find_element(By.CSS_SELECTOR, '[data-e2e="user-post-item-list"] a')
                    first_link.click()
                    logger.info("Clicked first video via fallback (anchor tag).")
                    time.sleep(3)
                    click_success = True
                except Exception as e2:
                    logger.error(f"Attempt {attempt}: Fallback click also failed: {e2}.")

            if click_success:
                return True

            if attempt < self.MAX_NAVIGATION_RETRIES:
                logger.warning(f"Refreshing page and retrying... ({attempt}/{self.MAX_NAVIGATION_RETRIES})")

        logger.warning(f"All {self.MAX_NAVIGATION_RETRIES} navigation attempts failed for {channel_handle}.")
        return False

    def _decode_single_subtitle(self, subtitle_mp4, subtitle_vtt, seq_id):
        """Run ffmpeg on a single subtitle.mp4 file to extract VTT via WSL."""
        def to_wsl_path(win_path):
            abs_path = str(win_path.resolve())
            drive, tail = os.path.splitdrive(abs_path)
            drive_letter = drive.replace(":", "").lower()
            tail = tail.replace("\\", "/")
            return f"/mnt/{drive_letter}{tail}"
            
        try:
            wsl_mp4 = to_wsl_path(subtitle_mp4)
            wsl_vtt = to_wsl_path(subtitle_vtt)
            
            result = subprocess.run(
                ["wsl", "ffmpeg", "-y", "-i", wsl_mp4, "-map", "0:s:0", wsl_vtt],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                logger.info(f"Decoded subtitle for folder '{seq_id}'")
            else:
                logger.warning(f"ffmpeg failed for folder '{seq_id}': {result.stderr[-200:]}")
        except FileNotFoundError:
            logger.error("wsl or ffmpeg not found! Please ensure WSL is installed and ffmpeg is in your Linux PATH.")
        except Exception as e:
            logger.warning(f"ffmpeg error for folder '{seq_id}': {e}")

    def crawl_channel(self, channel_handle):
        """Crawl a single channel until target posts are reached or timeout is hit."""
        self.current_channel = channel_handle
        self.captured_count = 0
        self.current_channel_seq_ids = []
        self.current_channel_evaluated = 0
        self.current_channel_rejected_count = 0

        logger.info(f"{'='*60}")
        logger.info(f"Starting crawl for channel: {channel_handle}")
        logger.info(f"Target: {self.POSTS_PER_CHANNEL} posts, Timeout: {self.CHANNEL_TIMEOUT}s")
        logger.info(f"{'='*60}")

        nav_ok = self._navigate_to_channel(channel_handle)
        if not nav_ok:
            logger.warning(f"Skipping channel {channel_handle}: could not enter video feed after {self.MAX_NAVIGATION_RETRIES} retries.")
            return
        
        # Start timeout clock AFTER navigation is complete
        last_capture_time = time.time()

        while self.captured_count < self.POSTS_PER_CHANNEL:
            delay = random.uniform(self.SCROLL_DELAY_MIN, self.SCROLL_DELAY_MAX)
            time.sleep(delay)

            ActionChains(self.driver).send_keys(Keys.ARROW_DOWN).perform()
            logger.info("Scrolled to next video.")

            # Wait a moment for network APIs to fire and settle
            time.sleep(1)
            newly_captured = self._capture_item_lists_cdp()

            if newly_captured > 0:
                last_capture_time = time.time()
                
            # Check early-exit channel quality
            if self.current_channel_evaluated >= self.EVALUATION_POST_COUNT:
                if self.current_channel_rejected_count >= self.MAX_REJECTED_TOLERANCE:
                    logger.warning(f"Channel {channel_handle} failed quality check "
                                   f"({self.current_channel_rejected_count}/{self.current_channel_evaluated} rejected). "
                                   f"Skipping to next channel...")
                    break

            # Check timeout: no new posts for CHANNEL_TIMEOUT seconds
            elapsed_since_last = time.time() - last_capture_time
            if elapsed_since_last > self.CHANNEL_TIMEOUT:
                logger.warning(f"No new posts captured for {self.CHANNEL_TIMEOUT}s. "
                               f"Moving on from {channel_handle}. "
                               f"(Captured {self.captured_count}/{self.POSTS_PER_CHANNEL})")
                break

        logger.info(f"Finished channel {channel_handle}: captured {self.captured_count} posts.")

    def run(self):
        # Open TikTok to ensure login session is active
        logger.info("Opening TikTok to verify login session...")
        self.driver.get("https://www.tiktok.com/")
        time.sleep(5)

        # Flush initial logs
        try:
            self.driver.get_log('performance')
        except Exception:
            pass

        for channel in self.channel_list:
            if channel in self.crawled_channels:
                logger.info(f"Skipping {channel}, already completely crawled in this category.")
                continue
            self.crawl_channel(channel)
            self.crawled_channels.add(channel)
            self._save_crawled_cache()

        logger.info("All channels processed!")
        logger.info("Crawl finished. Keeping browser open! Press Ctrl+C in terminal to exit.")
        while True:
            time.sleep(1)

def handle_exit(sig, frame):
    logger.info("\nCaught Ctrl+C! Forcing immediate exit...")
    try:
        crawler.driver.quit()
    except:
        pass
    os._exit(0)

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="TikTok Crawler V2")
    parser.add_argument("--category", default="all", help="Target category to crawl (e.g. marketing, fitness)")
    args = parser.parse_args()

    signal.signal(signal.SIGINT, handle_exit)
    crawler = TikTokCrawler(category=args.category)
    crawler.run()
