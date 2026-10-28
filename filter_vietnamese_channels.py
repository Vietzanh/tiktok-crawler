import os
import time
import json
import base64
import logging
import random
import winsound
import shutil
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

def handle_captcha(driver):
    while True:
        try:
            captcha_elements = driver.find_elements(By.CSS_SELECTOR, '[id*="captcha"], [class*="captcha"], [id*="verify-bar"]')
            is_captcha = any(el.is_displayed() for el in captcha_elements if getattr(el, 'is_displayed', lambda: False)())
            if not is_captcha:
                is_captcha = any(el.is_displayed() for el in captcha_elements)
            if "verify" in driver.current_url.lower() and "captcha" in driver.current_url.lower():
                is_captcha = True
            
            page_text = driver.find_element(By.TAG_NAME, 'body').text.lower()
            if "verify to continue" in page_text or "slide to complete the puzzle" in page_text:
                is_captcha = True
                
            if is_captcha:
                logger.warning("🚨 CAPTCHA DETECTED! Please solve it in the browser window. 🚨")
                try: winsound.Beep(1000, 1000)
                except: pass
                time.sleep(5)
            else:
                break
        except Exception:
            time.sleep(3)

INPUT_FILE = "channels.json"
OUTPUT_FILE = "Vietnamese_channels.json"
CACHE_FILE = ".checked_cache.json"

def atomic_save_json(filepath, data, make_backup=True, indent=None):
    """
    Safely writes data to a temporary file, flushes/syncs to disk,
    optionally creates/refreshes a .bak backup, and atomically renames to filepath.
    Guarantees the target file is never left empty or corrupted if disk is full or process is interrupted.
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
            try:
                shutil.copy2(target, backup_file)
            except Exception as e:
                logger.warning(f"Could not update backup {backup_file}: {e}")

        os.replace(temp_file, target)
    except Exception as e:
        if temp_file.exists():
            try:
                temp_file.unlink()
            except Exception:
                pass
        logger.error(f"Failed to atomically write {target}: {e}")
        raise

def safe_load_json(filepath, backup_filepath=None, default=None):
    """
    Safely loads a JSON file.
    If the file is 0 bytes or corrupted, attempts to fall back to backup_filepath.
    If both fail, raises RuntimeError instead of silently wiping state.
    """
    path = Path(filepath)
    backup_path = Path(backup_filepath) if backup_filepath else None

    if not path.exists():
        return default if default is not None else {}

    # Check for empty file (0 bytes)
    if path.stat().st_size == 0:
        logger.warning(f"Warning: {filepath} is 0 bytes.")
        if backup_path and backup_path.exists() and backup_path.stat().st_size > 0:
            logger.info(f"Restoring {filepath} from valid backup: {backup_filepath}")
            with open(backup_path, "r", encoding="utf-8") as f:
                return json.load(f)
        raise RuntimeError(f"File {filepath} is 0 bytes and no valid backup was found!")

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.error(f"JSON decode failed for {filepath}: {e}")
        if backup_path and backup_path.exists() and backup_path.stat().st_size > 0:
            logger.info(f"Falling back to backup {backup_filepath}...")
            with open(backup_path, "r", encoding="utf-8") as f:
                return json.load(f)
        raise RuntimeError(f"Corrupted JSON in {filepath} and no valid backup available. Error: {e}")

def human_like_delay(min_sec=3, max_sec=6):
    time.sleep(random.uniform(min_sec, max_sec))

def human_like_behavior(driver):
    try:
        action = ActionChains(driver)
        body = driver.find_element(By.TAG_NAME, 'body')
        x_offset = random.randint(10, 300)
        y_offset = random.randint(10, 300)
        action.move_to_element_with_offset(body, x_offset, y_offset).perform()
    except Exception:
        pass
        
    if random.random() < 0.3:
        driver.execute_script(f"window.scrollBy(0, -{random.randint(50, 300)});")
        time.sleep(random.uniform(0.5, 1.5))
        driver.execute_script(f"window.scrollBy(0, {random.randint(50, 200)});")

def get_item_list_response(driver, request_id_map, known_urls):
    bodies = []
    try:
        logs = driver.get_log('performance')
    except Exception:
        return bodies

    for entry in logs:
        try:
            log_msg = json.loads(entry['message'])['message']
            method = log_msg['method']
            
            if method == 'Network.responseReceived':
                url = log_msg['params']['response']['url']
                if '/item_list/' in url:
                    req_id = log_msg['params']['requestId']
                    request_id_map[req_id] = url
                    
            elif method == 'Network.loadingFinished':
                req_id = log_msg['params']['requestId']
                if req_id in request_id_map:
                    url = request_id_map[req_id]
                    if url not in known_urls:
                        try:
                            response_body = driver.execute_cdp_cmd('Network.getResponseBody', {'requestId': req_id})
                            body = response_body.get('body')
                            is_b64 = response_body.get('base64Encoded', False)
                            if body:
                                if is_b64:
                                    body = base64.b64decode(body).decode('utf-8', errors='ignore')
                                bodies.append(body)
                                known_urls.add(url)
                        except Exception:
                            pass
                    del request_id_map[req_id]
        except Exception:
            pass
            
    return bodies

def _try_evaluate_channel_videos(driver, retries=3):
    request_id_map = {}
    known_urls = set()
    
    # Wait for the page to load and trigger the item_list API
    for i in range(retries):
        human_like_delay(1, 2) # Wait for network requests
        human_like_behavior(driver)
        bodies = get_item_list_response(driver, request_id_map, known_urls)
        
        for body_str in bodies:
            try:
                data = json.loads(body_str)
                items = data.get("itemList", [])
                if not items:
                    continue
                    
                # Evaluate the first 6 videos
                videos_to_check = items[:6]
                vi_count = sum(1 for item in videos_to_check if item.get("textLanguage") == "vi")
                        
                logger.info(f"  -> {vi_count}/{len(videos_to_check)} videos are Vietnamese ('vi').")
                return vi_count >= 2
                
            except Exception as e:
                logger.warning(f"  JSON parse error: {e}")
                
    return None

def check_channel_is_vietnamese(driver, channel_handle):
    logger.info(f"Waiting 2-4s on previous page before jumping to {channel_handle}...")
    human_like_delay(1, 2)
    handle_captcha(driver)
    
    logger.info(f"Checking {channel_handle}...")
    
    # Flush old logs
    try:
        driver.get_log('performance')
    except:
        pass
        
    try:
        driver.execute_script(f"""
            var a = document.createElement('a');
            a.href = 'https://www.tiktok.com/{channel_handle}';
            a.style.display = 'none';
            document.body.appendChild(a);
            a.click();
        """)
    except:
        driver.get(f"https://www.tiktok.com/{channel_handle}")
        
    human_like_delay(2, 3) # Random delay after loading new URL
    human_like_behavior(driver)
    handle_captcha(driver)
    
    # First attempt: check after initial navigation
    result = _try_evaluate_channel_videos(driver, retries=3)
    if result is not None:
        return result
        
    # If no posts found or intercepted, refresh once
    logger.info(f"  -> No posts found/intercepted for {channel_handle}. Refreshing page once...")
    try:
        driver.get_log('performance')
    except:
        pass
        
    driver.refresh()
    human_like_delay(2, 3)
    human_like_behavior(driver)
    handle_captcha(driver)
    
    # Second attempt: check after refresh
    result = _try_evaluate_channel_videos(driver, retries=3)
    if result is not None:
        return result
        
    logger.warning(f"  -> Could not intercept item_list API for {channel_handle} after refresh. Skipping.")
    return False

def main():
    if not os.path.exists(INPUT_FILE):
        logger.error(f"Input file {INPUT_FILE} not found!")
        return
        
    input_data = safe_load_json(INPUT_FILE, default={})
        
    # Load existing output and cache safely (with .bak fallback)
    output_backup = f"{OUTPUT_FILE}.bak"
    cache_backup = f"{CACHE_FILE}.bak"
    
    output_data = safe_load_json(OUTPUT_FILE, backup_filepath=output_backup, default={})
    raw_cache = safe_load_json(CACHE_FILE, backup_filepath=cache_backup, default=[])
    checked_channels = set(raw_cache) if isinstance(raw_cache, list) else set()
    
    # Desync integrity guard: warn if output categories are unexpectedly empty while cache is populated
    if checked_channels:
        for cat, ch_list in input_data.items():
            checked_in_cat = sum(1 for ch in ch_list if ch in checked_channels)
            accepted_in_cat = len(output_data.get(cat, []))
            if checked_in_cat > 20 and accepted_in_cat == 0:
                logger.warning(
                    f"⚠️ WARNING: Category '{cat}' has {checked_in_cat} channels in {CACHE_FILE} "
                    f"but 0 accepted channels in {OUTPUT_FILE}! If channels were lost, run "
                    f"`python recover_channels.py` before continuing."
                )
                
    options = webdriver.ChromeOptions()
    options.add_experimental_option('excludeSwitches', ['enable-logging'])
    profile_dir = Path("chrome_profile").resolve()
    options.add_argument(f"user-data-dir={profile_dir}")
    options.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
    
    driver = webdriver.Chrome(options=options)
    driver.execute_cdp_cmd('Network.enable', {})
    
    try:
        for category, channels in input_data.items():
            if category not in output_data:
                output_data[category] = []
                
            accepted_set = set(output_data[category])
            
            for channel in channels:
                if channel in checked_channels:
                    continue # Skip if we already checked it in a previous run
                    
                is_vi = check_channel_is_vietnamese(driver, channel)
                checked_channels.add(channel)
                
                if is_vi:
                    logger.info(f"  [+] ACCEPTED: {channel}")
                    accepted_set.add(channel)
                else:
                    logger.info(f"  [-] REJECTED: {channel}")
                    
                # Incrementally save results atomically
                output_data[category] = sorted(list(accepted_set))
                atomic_save_json(OUTPUT_FILE, output_data, make_backup=True, indent=4)
                
                # Incrementally save cache atomically
                atomic_save_json(CACHE_FILE, list(checked_channels), make_backup=True)
    finally:
        driver.quit()
        logger.info(f"Done! Filtered channels saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
