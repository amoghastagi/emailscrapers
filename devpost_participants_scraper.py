import requests
from bs4 import BeautifulSoup
import json
import time
import random
from urllib.parse import urljoin, urlparse
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementNotInteractableException
from selenium.webdriver.common.action_chains import ActionChains
import gc
import psutil
import os

class DevpostHackathonScraper:
    """Scraper for hackathon URLs from Devpost"""
    
    def __init__(self):
        self.base_url = "https://devpost.com"
        self.hackathons_url = f"{self.base_url}/hackathons"
        self.driver = None
        
    def setup_driver(self):
        """Setup Chrome driver with optimized options"""
        if self.driver:
            return
            
        chrome_options = Options()
        chrome_options.add_argument("--start-maximized")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        # Uncomment for headless mode
        # chrome_options.add_argument("--headless")
        
        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        self.driver.set_page_load_timeout(30)
        self.driver.implicitly_wait(10)
    
    def scroll_to_load_all(self, pause_time=2, max_scrolls=10):
        """Scroll to load all hackathons"""
        print("📜 Scrolling to load all hackathons...")
        
        last_height = self.driver.execute_script("return document.body.scrollHeight")
        scrolls_done = 0
        
        for scroll in range(max_scrolls):
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(pause_time)
            
            new_height = self.driver.execute_script("return document.body.scrollHeight")
            scrolls_done += 1
            
            print(f"   Scroll {scrolls_done}/{max_scrolls} - Page height: {new_height:,}px")
            
            if new_height == last_height:
                print("   No more content to load")
                break
            last_height = new_height
    
    def extract_hackathon_urls(self):
        """Extract hackathon URLs from the page"""
        tiles = self.driver.find_elements(By.CSS_SELECTOR, 'div.hackathon-tile a.tile-anchor')
        urls = []
        
        for tile in tiles:
            href = tile.get_attribute("href")
            if href and "devpost.com" in href:
                clean_url = href.split("?")[0]  # Clean the URL
                urls.append(clean_url)
        
        return list(set(urls))  # Remove duplicates
    
    def scrape_hackathons(self, status="open", challenge_type="online"):
        """Scrape hackathon URLs with filters"""
        print("🚀 Starting hackathon URL scraper...")
        
        # Build URL with filters
        url = f"{self.hackathons_url}?status={status}&challenge_type={challenge_type}"
        print(f"🎯 Target: {url}")
        
        try:
            self.setup_driver()
            self.driver.get(url)
            time.sleep(3)  # Wait for content to load
            
            # Scroll to load all hackathons
            self.scroll_to_load_all()
            
            # Extract URLs
            hackathon_urls = self.extract_hackathon_urls()
            
            print(f"✅ Found {len(hackathon_urls)} hackathons")
            return hackathon_urls
            
        except Exception as e:
            print(f"❌ Error scraping hackathons: {e}")
            return []
        finally:
            if self.driver:
                self.driver.quit()


class DevpostParticipantsScraper:
    """Enhanced participant scraper with better error handling"""
    
    def __init__(self, hackathon_url, use_selenium=True, max_participants=5000, start_offset=0):
        self.hackathon_url = hackathon_url.rstrip('/')
        self.participants_url = f"{self.hackathon_url}/participants"
        self.use_selenium = use_selenium
        self.max_participants = max_participants
        self.start_offset = start_offset
        self.driver = None
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36'
        })
        
        # Add checkpoint mechanism
        self.checkpoint_interval = 1000  # Save every 1000 participants
        
    def setup_selenium(self):
        """Setup Selenium driver with better options and memory management"""
        if self.driver:
            return
            
        chrome_options = Options()
        # Add memory management options
        # chrome_options.add_argument("--headless")  # COMMENTED OUT - Enable headless for better performance
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--disable-plugins")
        # chrome_options.add_argument("--disable-images")  # COMMENTED OUT - Don't load images to save memory
        # chrome_options.add_argument("--disable-javascript")  # COMMENTED OUT - Disable JS if not needed
        chrome_options.add_argument("--memory-pressure-off")
        chrome_options.add_argument("--max_old_space_size=4096")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument("--window-size=1920,1080")
        
        # Set page load strategy for better performance
        chrome_options.page_load_strategy = 'eager'
        
        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        # Set timeouts
        self.driver.set_page_load_timeout(30)
        self.driver.implicitly_wait(10)
        
    def check_memory_usage(self):
        """Check memory usage and warn if getting high"""
        process = psutil.Process(os.getpid())
        memory_mb = process.memory_info().rss / 1024 / 1024
        
        if memory_mb > 2048:  # 2GB warning
            print(f"⚠️  High memory usage: {memory_mb:.1f} MB")
            return True
        return False
        
    def check_login_required(self, soup_or_text):
        """Check if login is required"""
        text = soup_or_text if isinstance(soup_or_text, str) else str(soup_or_text)
        login_indicators = [
            "log in to browse",
            "sign in to view",
            "login required",
            "please log in",
            "authentication required",
            "you need to sign in"
        ]
        return any(indicator in text.lower() for indicator in login_indicators)
        
    def scrape_with_requests(self):
        """Try scraping with requests first (faster)"""
        try:
            print("🔄 Attempting to scrape with requests...")
            response = self.session.get(self.participants_url, timeout=10)
            response.raise_for_status()
            
            if self.check_login_required(response.text):
                print("❌ Login required. Switching to Selenium method...")
                return None
                
            soup = BeautifulSoup(response.text, 'html.parser')
            participants = self.parse_participants_page(soup)
            
            if participants:
                print(f"✅ Successfully scraped {len(participants)} participants with requests")
                return participants
            else:
                print("❌ No participants found with requests method")
                return None
                
        except Exception as e:
            print(f"❌ Requests method failed: {e}")
            return None
    
    def handle_login_if_needed(self):
        """Handle login if required"""
        try:
            if self.check_login_required(self.driver.page_source):
                print("🔐 Login required. Options:")
                print("   1. Manual login (recommended)")
                print("   2. Skip login and try public access")
                choice = input("Choose option (1 or 2): ").strip()
                
                if choice == "1":
                    print("🌐 Please log in manually:")
                    print("   1. The browser will navigate to login page")
                    print("   2. Log in with your credentials")
                    print("   3. Press Enter here when you're logged in...")
                    
                    self.driver.get("https://devpost.com/users/sign_in")
                    input("Press Enter after logging in...")
                    
                    self.driver.get(self.participants_url)
                    time.sleep(3)
                    
                    if self.check_login_required(self.driver.page_source):
                        print("❌ Still not logged in. Continuing with public access...")
                        return False
                    else:
                        print("✅ Successfully logged in!")
                        return True
                else:
                    print("⚠️  Continuing without login...")
                    return False
            return True
            
        except Exception as e:
            print(f"❌ Login handling failed: {e}")
            return False
    
    def save_checkpoint(self, participants, checkpoint_num):
        """Save checkpoint data"""
        hackathon_name = self.hackathon_url.split('/')[-1]
        checkpoint_filename = f"checkpoint_{hackathon_name}_{checkpoint_num}_participants.json"
        try:
            with open(checkpoint_filename, 'w', encoding='utf-8') as f:
                json.dump(participants, f, indent=2, ensure_ascii=False)
            print(f"💾 Checkpoint saved: {checkpoint_filename} ({len(participants)} participants)")
        except Exception as e:
            print(f"❌ Error saving checkpoint: {e}")
    
    def scroll_and_load_participants(self):
        """Scroll down to load participants with better error handling and memory management"""
        print(f"📜 Loading participants with infinite scroll...")
        print(f"   Skipping first {self.start_offset:,} participants")
        print(f"   Target: participants {self.start_offset + 1:,} to {self.start_offset + self.max_participants:,}")
        
        last_height = self.driver.execute_script("return document.body.scrollHeight")
        participants_count = 0
        scroll_attempts = 0
        max_scroll_attempts = 50  # Reduced for better stability
        target_participants = self.start_offset + self.max_participants
        stale_count = 0
        
        # Store participants as we go for checkpointing
        all_participants = []
        
        while scroll_attempts < max_scroll_attempts:
            try:
                # Check memory usage periodically
                if participants_count % 500 == 0 and participants_count > 0:
                    if self.check_memory_usage():
                        # Force garbage collection
                        gc.collect()
                
                # Count current participants with retry logic
                current_participants_elements = None
                for retry in range(3):
                    try:
                        current_participants_elements = self.driver.find_elements(By.CSS_SELECTOR, ".user-profile")
                        break
                    except Exception as e:
                        print(f"   Retry {retry + 1}: Error finding elements - {e}")
                        time.sleep(2)
                        
                if not current_participants_elements:
                    print("❌ Could not find participant elements after retries")
                    break
                
                current_participants = len(current_participants_elements)
                
                # Check if we've reached the target
                if current_participants >= target_participants:
                    print(f"🎯 Reached target of {target_participants:,} participants. Stopping...")
                    break
                
                # Show progress and save checkpoints
                if current_participants > participants_count:
                    participants_count = current_participants
                    remaining_needed = target_participants - current_participants
                    print(f"   Found {current_participants:,} participants (need {remaining_needed:,} more)...")
                    
                    # Save checkpoint every N participants
                    if participants_count % self.checkpoint_interval == 0:
                        try:
                            soup = BeautifulSoup(self.driver.page_source, 'html.parser')
                            checkpoint_participants = self.parse_participants_page(soup)
                            self.save_checkpoint(checkpoint_participants, participants_count // self.checkpoint_interval)
                        except Exception as e:
                            print(f"   ⚠️  Checkpoint save failed: {e}")
                    
                    scroll_attempts = 0
                    stale_count = 0
                else:
                    stale_count += 1
                
                # Scroll down with error handling
                try:
                    self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                except Exception as e:
                    print(f"   ⚠️  Scroll error: {e}")
                    break
                
                # Wait for new content to load with adaptive timing
                wait_time = random.uniform(3, 6) if stale_count > 2 else random.uniform(2, 4)
                time.sleep(wait_time)
                
                # Check for new content
                try:
                    new_height = self.driver.execute_script("return document.body.scrollHeight")
                except Exception as e:
                    print(f"   ⚠️  Height check error: {e}")
                    break
                
                if new_height == last_height:
                    scroll_attempts += 1
                    if scroll_attempts >= 8:  # Increased patience
                        print("   No more participants to load")
                        break
                else:
                    last_height = new_height
                    scroll_attempts = 0
                    
            except Exception as e:
                print(f"   ⚠️  Error in scroll loop: {e}")
                scroll_attempts += 1
                time.sleep(5)  # Longer wait on error
                
                if scroll_attempts >= 3:
                    print("   Too many errors, stopping...")
                    break
        
        try:
            final_count = len(self.driver.find_elements(By.CSS_SELECTOR, ".user-profile"))
            print(f"✅ Finished scrolling. Found {final_count:,} total participants")
            
            if final_count < self.start_offset:
                print(f"⚠️  Warning: Only found {final_count:,} total participants, but offset is {self.start_offset:,}")
                return False
            
            available_for_batch = final_count - self.start_offset
            print(f"   Available for this batch: {available_for_batch:,}")
            
            return final_count > self.start_offset
            
        except Exception as e:
            print(f"❌ Error getting final count: {e}")
            return False
    
    def scrape_with_selenium(self):
        """Scrape using Selenium with better error handling"""
        try:
            self.setup_selenium()
            
            print("🔍 Navigating to participants page...")
            self.driver.get(self.participants_url)
            
            # Wait for page to load
            WebDriverWait(self.driver, 20).until(
                EC.presence_of_element_located((By.TAG_NAME, "body"))
            )
            
            # Handle login if needed
            if not self.handle_login_if_needed():
                print("⚠️  Proceeding without login...")
            
            # Wait for initial participants to load
            try:
                WebDriverWait(self.driver, 15).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".user-profile"))
                )
            except TimeoutException:
                print("❌ No participants found on initial load")
                return []
            
            # Scroll to load participants
            if not self.scroll_and_load_participants():
                print("❌ Failed to load participants")
                return []
            
            # Parse participants with error handling
            print("📊 Parsing participant data...")
            try:
                soup = BeautifulSoup(self.driver.page_source, 'html.parser')
                participants = self.parse_participants_page(soup)
                
                if len(participants) > self.max_participants:
                    participants = participants[:self.max_participants]
                    print(f"🔄 Limited results to {self.max_participants:,} participants")
                
                return participants
                
            except Exception as e:
                print(f"❌ Error parsing participants: {e}")
                return []
            
        except Exception as e:
            print(f"❌ Selenium method failed: {e}")
            import traceback
            traceback.print_exc()
            return []
        finally:
            if self.driver:
                print("🔄 Closing browser...")
                try:
                    self.driver.quit()
                except:
                    pass
    
    def parse_participants_page(self, soup):
        """Parse participants from BeautifulSoup object with better error handling"""
        participants = []
        
        try:
            # Find all user profile elements
            user_profiles = soup.select(".user-profile")
            
            if not user_profiles:
                print("❌ No .user-profile elements found")
                user_profiles = soup.select("[data-user-profile]")
                
            if not user_profiles:
                print("❌ No user profile elements found with any selector")
                return []
            
            total_found = len(user_profiles)
            print(f"   Found {total_found:,} total user profiles")
            
            # Apply offset and limit
            start_idx = self.start_offset
            end_idx = min(start_idx + self.max_participants, total_found)
            
            if start_idx >= total_found:
                print(f"❌ Offset {start_idx:,} is greater than total participants {total_found:,}")
                return []
            
            user_profiles_batch = user_profiles[start_idx:end_idx]
            print(f"   Processing participants {start_idx + 1:,} to {start_idx + len(user_profiles_batch):,}")
            
            # Parse each participant in the batch
            for i, profile in enumerate(user_profiles_batch):
                try:
                    participant = self.parse_participant_element(profile)
                    if participant and participant.get('username'):
                        if participant['username'] not in ['logout', 'login', 'signup', 'sign_in']:
                            participants.append(participant)
                            
                            # Show progress for large batches
                            if (i + 1) % 500 == 0:
                                print(f"   Parsed {i + 1:,}/{len(user_profiles_batch):,} participants...")
                                
                except Exception as e:
                    print(f"   ⚠️  Error parsing participant {start_idx + i + 1}: {e}")
                    continue
            
            return participants
            
        except Exception as e:
            print(f"❌ Error in parse_participants_page: {e}")
            return []
    
    def parse_participant_element(self, profile_element):
        """Parse individual participant from user-profile element"""
        participant = {
            "username": "",
            "name": "",
            "profile_url": "",
            "bio": "",
            "location": "",
            "avatar_url": "",
            "role": "",
            "projects": 0,
            "followers": 0,
            "achievements": 0,
            "team_status": "",
            "contact_links": {}
        }
        
        try:
            # Extract profile URL and username
            profile_link = profile_element.select_one("a.user-profile-link")
            if profile_link:
                href = profile_link.get('href')
                if href:
                    if href.startswith('/'):
                        href = 'https://devpost.com' + href
                    participant["profile_url"] = href
                    if '/users/' in href or 'devpost.com/' in href:
                        username = href.split('/')[-1].split('?')[0]
                        participant["username"] = username
            
            # Extract name
            name_element = profile_element.select_one(".user-name h5 a")
            if name_element:
                participant["name"] = name_element.text.strip()
            
            # Extract role
            role_element = profile_element.select_one(".role")
            if role_element:
                participant["role"] = role_element.text.strip()
            
            # Extract avatar URL
            avatar_element = profile_element.select_one(".user_photo, .user-photo")
            if avatar_element:
                src = avatar_element.get('src')
                if src:
                    if src.startswith('//'):
                        src = 'https:' + src
                    participant["avatar_url"] = src
            
            # Extract statistics
            stats_elements = profile_element.select(".participant-stat")
            for stat_element in stats_elements:
                stat_text = stat_element.text.strip()
                parent_li = stat_element.find_parent('li')
                
                if parent_li:
                    if 'software-count' in parent_li.get('class', []):
                        try:
                            participant["projects"] = int(stat_text.split()[0])
                        except (ValueError, IndexError):
                            pass
                    elif 'followers-count' in parent_li.get('class', []):
                        try:
                            participant["followers"] = int(stat_text.split()[0])
                        except (ValueError, IndexError):
                            pass
                    elif 'achievements-count' in parent_li.get('class', []):
                        try:
                            participant["achievements"] = int(stat_text.split()[0])
                        except (ValueError, IndexError):
                            pass
            
            # Extract team status
            team_status_element = profile_element.select_one(".cp-tag")
            if team_status_element:
                participant["team_status"] = team_status_element.text.strip()
            
            # Only return if we have essential information
            if participant["username"] and participant["name"]:
                return participant
                
        except Exception as e:
            print(f"   Error parsing participant element: {e}")
            
        return None
    
    def scrape_participants(self, include_contact_info=False):
        """Main method to scrape participants with better error handling"""
        hackathon_name = self.hackathon_url.split('/')[-1]
        print("🚀 Starting Devpost participants scraper...")
        print(f"🎯 Hackathon: {hackathon_name}")
        print(f"🔗 Participants URL: {self.participants_url}")
        print(f"📊 Batch: {self.start_offset + 1:,} to {self.start_offset + self.max_participants:,}")
        
        # Try requests method first
        participants = self.scrape_with_requests()
        
        # If requests fails, use Selenium
        if participants is None:
            print("🔄 Switching to Selenium method...")
            participants = self.scrape_with_selenium()
        
        participants = participants or []
        
        # Scrape detailed profile information if requested
        if include_contact_info and participants:
            print(f"\n📋 Scraping detailed profile information for {len(participants):,} participants...")
            
            for i, participant in enumerate(participants):
                if (i + 1) % 100 == 0:
                    print(f"   Progress: {i+1:,}/{len(participants):,} ({((i+1)/len(participants)*100):.1f}%)")
                
                try:
                    participants[i] = self.scrape_participant_profile(participant)
                except Exception as e:
                    print(f"   ⚠️  Error scraping profile {i+1}: {e}")
                    continue
        
        return participants
    
    def scrape_participant_profile(self, participant):
        """Scrape detailed information from a participant's profile page"""
        if not participant.get('profile_url'):
            return participant
            
        try:
            response = self.session.get(participant['profile_url'], timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract contact links
            contact_links = {}
            portfolio_links = soup.select('#portfolio-user-links li')
            
            for link_li in portfolio_links:
                link_element = link_li.select_one('a')
                if link_element:
                    href = link_element.get('href')
                    text = link_element.text.strip()
                    
                    if href and text:
                        link_type = self.classify_link(href, text)
                        if link_type:
                            contact_links[link_type] = {
                                'url': href,
                                'label': text
                            }
            
            participant['contact_links'] = contact_links
            
            # Extract bio
            bio_element = soup.select_one('.user-bio, .profile-description, .bio')
            if bio_element:
                participant['bio'] = bio_element.text.strip()
            
            # Extract location
            location_element = soup.select_one('.location, .user-location')
            if location_element:
                participant['location'] = location_element.text.strip()
            
            # Add delay to be respectful
            time.sleep(random.uniform(0.5, 1.5))
            
        except Exception as e:
            print(f"   ⚠️  Error scraping profile for {participant['username']}: {e}")
        
        return participant
    
    def classify_link(self, url, text):
        """Classify a link based on its URL or text"""
        url_lower = url.lower()
        text_lower = text.lower()
        
        if 'github.com' in url_lower or 'github' in text_lower:
            return 'github'
        elif 'linkedin.com' in url_lower or 'linkedin' in text_lower:
            return 'linkedin'
        elif 'twitter.com' in url_lower or 'x.com' in url_lower or 'twitter' in text_lower:
            return 'twitter'
        elif 'website' in text_lower or 'portfolio' in text_lower:
            return 'website'
        elif 'mailto:' in url_lower or 'email' in text_lower:
            return 'email'
        elif 'instagram.com' in url_lower or 'instagram' in text_lower:
            return 'instagram'
        elif 'youtube.com' in url_lower or 'youtu.be' in url_lower or 'youtube' in text_lower:
            return 'youtube'
        elif 'medium.com' in url_lower or 'medium' in text_lower:
            return 'medium'
        elif not any(domain in url_lower for domain in ['facebook.com', 'google.com', 'apple.com']):
            return 'website'
        
        return 'other'
    
    def save_results(self, participants, filename=None):
        """Save results to JSON file with batch info"""
        hackathon_name = self.hackathon_url.split('/')[-1]
        
        if filename is None:
            batch_start = self.start_offset + 1
            batch_end = self.start_offset + len(participants)
            filename = f"{hackathon_name}_participants_{batch_start}-{batch_end}.json"
        
        try:
            data = {
                "metadata": {
                    "hackathon_url": self.hackathon_url,
                    "hackathon_name": hackathon_name,
                    "batch_start": self.start_offset + 1,
                    "batch_end": self.start_offset + len(participants),
                    "total_in_batch": len(participants),
                    "scraped_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "max_participants": self.max_participants,
                    "start_offset": self.start_offset
                },
                "participants": participants
            }
            
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print(f"📁 Results saved to {filename}")
            print(f"   Batch info: participants {self.start_offset + 1:,} to {self.start_offset + len(participants):,}")
        except Exception as e:
            print(f"❌ Error saving results: {e}")
    
    def validate_participants(self, participants):
        """Validate and clean participant data"""
        valid_participants = []
        seen_usernames = set()
        
        for participant in participants:
            if not participant.get('username') or not participant.get('name'):
                continue
            
            username = participant.get('username', '').lower()
            if username in ['logout', 'login', 'signup', 'sign_in', 'register']:
                continue
            
            if username in seen_usernames:
                continue
            
            seen_usernames.add(username)
            valid_participants.append(participant)
        
        return valid_participants


def main():
    """Main execution function with menu system"""
    print("🚀 Combined Devpost Hackathon & Participant Scraper")
    print("=" * 60)
    
    while True:
        print("\n📋 What would you like to do?")
        print("   1. 🔍 Scrape hackathon URLs")
        print("   2. 👥 Scrape participants from a hackathon")
        print("   3. 🔄 Full workflow (scrape hackathons, then participants)")
        print("   4. 📊 Batch scrape participants (with offset)")
        print("   5. ❌ Exit")
        
        choice = input("\n💭 Enter your choice (1-5): ").strip()
        
        if choice == '1':
            # Scrape hackathon URLs
            print("\n🔍 HACKATHON URL SCRAPER")
            print("-" * 30)
            
            # Get filter options
            print("\n🎯 Filter Options:")
            print("   Status options: open, completed, upcoming")
            status = input("Enter status (default: open): ").strip() or "open"
            
            print("   Type options: online, in-person, hybrid")
            challenge_type = input("Enter type (default: online): ").strip() or "online"
            
            # Scrape hackathons
            hackathon_scraper = DevpostHackathonScraper()
            hackathon_urls = hackathon_scraper.scrape_hackathons(status=status, challenge_type=challenge_type)
            
            if hackathon_urls:
                print(f"\n✅ Successfully scraped {len(hackathon_urls)} hackathon URLs")
                
                # Save to file
                filename = f"hackathons_{status}_{challenge_type}_{int(time.time())}.json"
                try:
                    data = {
                        "metadata": {
                            "status": status,
                            "challenge_type": challenge_type,
                            "scraped_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                            "total_hackathons": len(hackathon_urls)
                        },
                        "hackathon_urls": hackathon_urls
                    }
                    
                    with open(filename, 'w', encoding='utf-8') as f:
                        json.dump(data, f, indent=2, ensure_ascii=False)
                    print(f"📁 URLs saved to: {filename}")
                    
                    # Show first few URLs as preview
                    print("\n👀 Preview (first 5 URLs):")
                    for i, url in enumerate(hackathon_urls[:5], 1):
                        print(f"   {i}. {url}")
                    
                    if len(hackathon_urls) > 5:
                        print(f"   ... and {len(hackathon_urls) - 5} more")
                        
                except Exception as e:
                    print(f"❌ Error saving URLs: {e}")
            else:
                print("❌ No hackathon URLs found")
        
        elif choice == '2':
            # Scrape participants from single hackathon
            print("\n👥 PARTICIPANT SCRAPER")
            print("-" * 25)
            
            hackathon_url = input("🔗 Enter hackathon URL: ").strip()
            if not hackathon_url:
                print("❌ No URL provided")
                continue
            
            # Get scraping options
            print("\n⚙️  Scraping Options:")
            max_participants = input("📊 Max participants (default: 5000): ").strip()
            max_participants = int(max_participants) if max_participants.isdigit() else 5000
            
            include_contact = input("📞 Include contact info? (y/n, default: n): ").strip().lower()
            include_contact_info = include_contact in ['y', 'yes', '1', 'true']
            
            # Create scraper and run
            participant_scraper = DevpostParticipantsScraper(
                hackathon_url=hackathon_url,
                max_participants=max_participants
            )
            
            participants = participant_scraper.scrape_participants(include_contact_info=include_contact_info)
            
            if participants:
                # Validate participants
                participants = participant_scraper.validate_participants(participants)
                
                print(f"\n✅ Successfully scraped {len(participants)} participants")
                
                # Save results
                participant_scraper.save_results(participants)
                
                # Show summary
                print("\n📊 Summary:")
                print(f"   Total participants: {len(participants)}")
                if participants:
                    avg_projects = sum(p.get('projects', 0) for p in participants) / len(participants)
                    avg_followers = sum(p.get('followers', 0) for p in participants) / len(participants)
                    print(f"   Average projects: {avg_projects:.1f}")
                    print(f"   Average followers: {avg_followers:.1f}")
                    
                    # Show roles distribution
                    roles = {}
                    for p in participants:
                        role = p.get('role', 'Unknown')
                        roles[role] = roles.get(role, 0) + 1
                    
                    if roles:
                        print("   Top roles:")
                        for role, count in sorted(roles.items(), key=lambda x: x[1], reverse=True)[:5]:
                            print(f"     {role}: {count}")
            else:
                print("❌ No participants found")
        
        elif choice == '3':
            # Full workflow
            print("\n🔄 FULL WORKFLOW")
            print("-" * 20)
            
            print("Step 1: Scraping hackathon URLs...")
            hackathon_scraper = DevpostHackathonScraper()
            hackathon_urls = hackathon_scraper.scrape_hackathons()
            
            if not hackathon_urls:
                print("❌ No hackathons found, stopping workflow")
                continue
            
            print(f"✅ Found {len(hackathon_urls)} hackathons")
            
            # Ask which hackathons to scrape
            print("\nStep 2: Select hackathons to scrape participants from:")
            print("   1. All hackathons")
            print("   2. First N hackathons")
            print("   3. Select specific hackathons")
            
            selection = input("Choose option (1-3): ").strip()
            
            selected_urls = []
            if selection == '1':
                selected_urls = hackathon_urls
            elif selection == '2':
                n = input("How many hackathons? ").strip()
                n = int(n) if n.isdigit() else 5
                selected_urls = hackathon_urls[:n]
            elif selection == '3':
                print("\nAvailable hackathons:")
                for i, url in enumerate(hackathon_urls, 1):
                    hackathon_name = url.split('/')[-1]
                    print(f"   {i}. {hackathon_name}")
                
                indices = input("Enter indices (comma-separated): ").strip()
                try:
                    indices = [int(i.strip()) - 1 for i in indices.split(',')]
                    selected_urls = [hackathon_urls[i] for i in indices if 0 <= i < len(hackathon_urls)]
                except:
                    print("❌ Invalid indices, using first 3 hackathons")
                    selected_urls = hackathon_urls[:3]
            
            # Get participant scraping options
            max_participants = input("\n📊 Max participants per hackathon (default: 1000): ").strip()
            max_participants = int(max_participants) if max_participants.isdigit() else 1000
            
            # Scrape participants from selected hackathons
            print(f"\nStep 3: Scraping participants from {len(selected_urls)} hackathons...")
            
            all_results = {}
            for i, url in enumerate(selected_urls, 1):
                hackathon_name = url.split('/')[-1]
                print(f"\n📋 Processing {i}/{len(selected_urls)}: {hackathon_name}")
                
                try:
                    participant_scraper = DevpostParticipantsScraper(
                        hackathon_url=url,
                        max_participants=max_participants
                    )
                    
                    participants = participant_scraper.scrape_participants()
                    participants = participant_scraper.validate_participants(participants)
                    
                    if participants:
                        participant_scraper.save_results(participants)
                        all_results[hackathon_name] = len(participants)
                        print(f"   ✅ {len(participants)} participants scraped")
                    else:
                        print(f"   ❌ No participants found")
                        all_results[hackathon_name] = 0
                    
                    # Add delay between hackathons
                    if i < len(selected_urls):
                        print("   ⏸️  Waiting 30 seconds before next hackathon...")
                        time.sleep(30)
                        
                except Exception as e:
                    print(f"   ❌ Error scraping {hackathon_name}: {e}")
                    all_results[hackathon_name] = 0
            
            # Show final summary
            print("\n🎯 WORKFLOW COMPLETE")
            print("=" * 30)
            total_participants = sum(all_results.values())
            print(f"Total participants scraped: {total_participants:,}")
            print("\nResults by hackathon:")
            for hackathon, count in all_results.items():
                print(f"   {hackathon}: {count:,} participants")
        
        elif choice == '4':
            # Batch scrape with offset
            print("\n📊 BATCH PARTICIPANT SCRAPER")
            print("-" * 30)
            
            hackathon_url = input("🔗 Enter hackathon URL: ").strip()
            if not hackathon_url:
                print("❌ No URL provided")
                continue
            
            print("\n⚙️  Batch Options:")
            start_offset = input("🔢 Start offset (default: 0): ").strip()
            start_offset = int(start_offset) if start_offset.isdigit() else 0
            
            batch_size = input("📦 Batch size (default: 1000): ").strip()
            batch_size = int(batch_size) if batch_size.isdigit() else 1000
            
            total_batches = input("🔄 Number of batches (default: 1): ").strip()
            total_batches = int(total_batches) if total_batches.isdigit() else 1
            
            # Run batches
            for batch_num in range(total_batches):
                current_offset = start_offset + (batch_num * batch_size)
                
                print(f"\n📦 Processing batch {batch_num + 1}/{total_batches}")
                print(f"   Offset: {current_offset:,}")
                print(f"   Target: participants {current_offset + 1:,} to {current_offset + batch_size:,}")
                
                try:
                    participant_scraper = DevpostParticipantsScraper(
                        hackathon_url=hackathon_url,
                        max_participants=batch_size,
                        start_offset=current_offset
                    )
                    
                    participants = participant_scraper.scrape_participants()
                    participants = participant_scraper.validate_participants(participants)
                    
                    if participants:
                        participant_scraper.save_results(participants)
                        print(f"   ✅ Batch {batch_num + 1} complete: {len(participants)} participants")
                    else:
                        print(f"   ❌ Batch {batch_num + 1} failed: No participants found")
                        break  # Stop if no more participants
                    
                    # Add delay between batches
                    if batch_num < total_batches - 1:
                        delay = random.randint(60, 120)  # 1-2 minute delay
                        print(f"   ⏸️  Waiting {delay} seconds before next batch...")
                        time.sleep(delay)
                        
                except Exception as e:
                    print(f"   ❌ Batch {batch_num + 1} error: {e}")
                    continue
        
        elif choice == '5':
            print("\n👋 Thanks for using the scraper!")
            break
        
        else:
            print("❌ Invalid choice. Please enter 1-5.")
        
        # Ask if user wants to continue
        if choice in ['1', '2', '3', '4']:
            print("\n" + "="*60)
            continue_choice = input("Continue with another operation? (y/n): ").strip().lower()
            if continue_choice not in ['y', 'yes', '1']:
                print("\n👋 Thanks for using the scraper!")
                break


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⛔ Operation cancelled by user")
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()