import time
import json
import re
import random
import winsound
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains

def handle_captcha(driver):
    while True:
        try:
            captcha_elements = driver.find_elements(By.CSS_SELECTOR, '[id*="captcha"], [class*="captcha"], [id*="verify-bar"]')
            is_captcha = any(el.is_displayed() for el in captcha_elements)
            if "verify" in driver.current_url.lower() and "captcha" in driver.current_url.lower():
                is_captcha = True
            
            page_text = driver.find_element(By.TAG_NAME, 'body').text.lower()
            if "verify to continue" in page_text or "slide to complete the puzzle" in page_text:
                is_captcha = True
                
            if is_captcha:
                print("\n" + "="*50)
                print("🚨 CAPTCHA DETECTED! 🚨")
                print("Please solve the CAPTCHA in the browser window.")
                print("The script will automatically resume once it disappears.")
                print("="*50 + "\n")
                try: winsound.Beep(1000, 1000)
                except: pass
                time.sleep(5)
            else:
                break
        except Exception:
            time.sleep(3)

# ==============================================================================
# CONFIGURATION
# ==============================================================================
CATEGORIES = {
    "marketing": ["socialmedia", "socialmediamarketing", "socialmediatips", "socialmediastrategy", 
    "socialmediamanager", "socialmediamanagement", "socialmediamarketingtips", 
    "socialmediatip", "socialmediaagency", "socialmediaexpert", "socialmediatraining", 
    "socialMediaInfluencer", "socialmediastrategist", "socialmediacoach", 
    "socialmediaguru", "socialmediatools", "socialmediaconsultant", "SocialMediaContent", 
    "socialmediamarketer", "socialmediatrainer", "socialmedialife", "socialmedianetwork", 
    "socialmediaexperts", "socialmediaaddict", "socialmediahelp", "SocialMediaMarketingStrategist", 
    "socialmediaadvertising", "socialmedia101", "socialmediapromotion", "socialmediaoptimization"],

    "fitness": ["fitness", "fitnessmotivation", "fitnessmodel", "fitnessaddict", "fitnessgirl", 
    "fitnessjourney", "fitnesslifestyle", "fitnesslife", "fitnessfreak", "fitnessgoals", 
    "fitnessgear", "fitnessfood", "fitnessinspiration", "fitnessgirls", "fitnessbody", 
    "fitnesswomen", "fitnessblogger", "fitnessmodels", "fitnesscoach", "fitnessphysique", 
    "FitnessTrainer", "fitnesslover", "fitnessaddicted", "fitnessfreaks", "fitnesstips", 
    "fitnessfirst", "fitnessquote", "fitnessgoal", "healthy", "healthyfood", 
    "healthylifestyle", "healthychoices", "HealthyEating", "healthyliving", "healthylife", 
    "healthybreakfast"],

    "cook": ["cooking", "cookingtime", "cookingclass", "cookingvideo", "cookingatHome", 
    "cookingwithlove", "cookingschool", "cookingtips", "cookingshow", "cookingchannel", 
    "cookingwithkids", "cookingisfun", "cookingwithfire", "cookingdemo", "cookinglove", 
    "cookinglife", "cookingrecipesrepost", "cookingfromscratch", "cookingclasses", "cookinglover", 
    "cookingoutdoors", "cookingoutside", "cookinglesson", "cookingismypassion", "food", "foodporn", 
    "foodie", "foodstagram", "foodgasm", "foodblogger"],

    "beauty": ["skincare", "skincareroutine", "skincareaddict", "skincareproducts", "skincareman",
    "skincareluxury", "skincaretips", "skincareblogger", "skincarecommunity", "skincarelover",
    "skincareobsessed", "skincarediary", "skincarethailand", "skincareregime", "skincareproduct",
    "skincareregimen", "skincarereview", "skincareherbal", "beauty", "beautyblogger",
    "beautyblog", "beautiful", "beautyguru", "beautyqueen", "beautycare",
    "beautyaddict", "beautytips"],

    "shopping": ["fashion", "fashionblogger", "fashionable", "fashionstyle", "fashionblog", 
    "FashionAddict", "fashionweek", "fashiondiaries", "fashionpost", "fashionphotography", 
    "FashionDesigner", "fashionlover", "fashionshow", "fashionmodel", "fashiondesign", "fashionkids", 
    "fashiondaily", "fashionstylist", "fashiongirl", "fashionjewelry", "fashions", "fashioninsta", 
    "fashionart", "fashionmen", "fashionphotographer", "fashionbloggers", "shopping", "shoppingonline", 
    "shoppingday", "shoppingtime", "shoppingaddict", "shoppingspree", "shoppingmall", "shoppingbag"]
}

MAX_ITEMS_PER_HASHTAG = 200
OUTPUT_FILE = "channels.json"
# ==============================================================================

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

def scroll_smoothly_to_bottom(driver):
    current_pos = driver.execute_script("return window.pageYOffset;")
    target_pos = driver.execute_script("return document.body.scrollHeight;")
    
    while current_pos < target_pos:
        step = random.randint(30, 100)
        current_pos += step
        driver.execute_script(f"window.scrollTo(0, {current_pos});")
        time.sleep(random.uniform(0.01, 0.05))
        
        # Tiny random halt while scrolling
        if random.random() < 0.1:
            time.sleep(random.uniform(0.2, 0.8))
            handle_captcha(driver)

def scrape_hashtag_page(driver, hashtag):
    print(f"  Waiting 10-20s on previous page before jumping to #{hashtag}...")
    human_like_delay(10, 20)
    handle_captcha(driver)

    try:
        # Search UI navigation
        if "tiktok.com" not in driver.current_url:
            driver.get("https://www.tiktok.com/")
            human_like_delay(3, 6)
            
        search_input = None
        for sel in ['input[type="search"]', 'input[name="q"]', 'input[data-e2e="search-user-input"]']:
            try:
                search_input = driver.find_element(By.CSS_SELECTOR, sel)
                if search_input: break
            except: pass
            
        if search_input:
            print(f"  Typing #{hashtag} in search bar...")
            search_input.send_keys(Keys.CONTROL + "a")
            search_input.send_keys(Keys.BACKSPACE)
            time.sleep(0.5)
            for char in f"#{hashtag}":
                search_input.send_keys(char)
                time.sleep(random.uniform(0.05, 0.2))
            time.sleep(1)
            search_input.send_keys(Keys.RETURN)
            human_like_delay(3, 5)
            handle_captcha(driver)
            
        print("  Simulating organic link click to hashtag page...")
        driver.execute_script(f"""
            var a = document.createElement('a');
            a.href = 'https://www.tiktok.com/tag/{hashtag}';
            a.style.display = 'none';
            document.body.appendChild(a);
            a.click();
        """)
    except Exception as e:
        driver.get(f"https://www.tiktok.com/tag/{hashtag}")
        
    human_like_delay(4, 7)
    human_like_behavior(driver)
    handle_captcha(driver)
    
    last_height = driver.execute_script("return document.body.scrollHeight")
    channels = set()
    
    while True:
        # Extract channels dynamically while scrolling
        video_links = driver.find_elements(By.CSS_SELECTOR, 'div[id^="grid-item-container-"] a[href*="/video/"]')
        for link in video_links:
            href = link.get_attribute("href")
            if href:
                match = re.search(r'(@[\w\.]+)', href)
                if match:
                    channels.add(match.group(1))
                    
        print(f"    Found {len(channels)} unique channels so far...")
        
        # Stop scrolling if we reached the maximum unique channels (200 limit)
        if len(channels) >= MAX_ITEMS_PER_HASHTAG:
            print(f"    Reached limit of {MAX_ITEMS_PER_HASHTAG} channels.")
            break
            
        scroll_smoothly_to_bottom(driver)
        human_like_delay(3, 6) # Wait for new items to load
        human_like_behavior(driver)
        handle_captcha(driver)
        
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            # Try waiting a bit more in case of slow network
            human_like_delay(3, 6)
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                print(f"    Reached bottom of page.")
                break
        last_height = new_height

    return list(channels)

def main():
    options = webdriver.ChromeOptions()
    options.add_experimental_option('excludeSwitches', ['enable-logging'])
    
    # Enable persistent local profile to save logins and cookies
    profile_dir = Path("chrome_profile").resolve()
    options.add_argument(f"user-data-dir={profile_dir}")
    
    driver = webdriver.Chrome(options=options)
    
    result = {}
    output_path = Path(OUTPUT_FILE)
    if output_path.exists():
        with open(output_path, "r", encoding="utf-8") as f:
            try:
                result = json.load(f)
            except json.JSONDecodeError:
                pass
                
    for category, hashtags in CATEGORIES.items():
        category_channels = set(result.get(category, []))
        print(f"Processing category: {category}")
        
        for hashtag in hashtags:
            channels = scrape_hashtag_page(driver, hashtag)
            print(f"    -> Extracted {len(channels)} unique channels from #{hashtag}")
            category_channels.update(channels)
            
            # Silently save progress to JSON after every hashtag
            result[category] = list(category_channels)
            with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=4)
                
        print(f"  Total unique channels for '{category}': {len(category_channels)}\n")
        
    driver.quit()
    print(f"Done! All categories processed and saved to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
