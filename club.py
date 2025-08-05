# Enhanced University Club Scraper with Automatic Link Discovery
import asyncio
import re
import time
from urllib.parse import urljoin, urlparse, quote
from typing import List, Dict, Optional, Set
import logging

# Required packages - install with:
# pip install playwright selenium supabase beautifulsoup4 requests python-dotenv webdriver-manager

from playwright.async_api import async_playwright, Page, Browser
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, ElementClickInterceptedException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import requests
from supabase import create_client, Client
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class UniversityClubLinkDiscovery:
    def __init__(self):
        # Target URL patterns we're looking for
        self.target_patterns = [
            r'https?://[^/]+\.campuslabs\.com/engage/organizations',
            r'https?://[^/]+\.collegiatelink\.net/organizations',
            r'https?://[^/]+/organizations',
            r'https?://involved\.[^/]+/organizations',
            r'https?://engage\.[^/]+/organizations',
            r'https?://[^/]+\.orgsync\.com/organizations',
            r'https?://[^/]+\.presence\.io/organizations',
            r'https?://[^/]+\.campusgroups\.com/organizations'
        ]
        
        # Known good examples for validation
        self.known_examples = [
            'https://heellife.unc.edu/organizations',
            'https://utexas.campuslabs.com/engage/organizations',
            'https://involved.risd.edu/organizations',
            'https://callink.berkeley.edu/organizations',
            'https://gatech.campuslabs.com/engage/organizations'
        ]
        
        # Search queries to find these types of links
        self.search_queries = [
            'site:campuslabs.com/engage/organizations',
            'site:collegiatelink.net/organizations',
            '"student organizations" site:edu/organizations',
            'site:involved. organizations',
            'site:engage. organizations',
            '"campus organizations" inurl:organizations',
            'campuslabs engage organizations',
            'student organizations directory site:edu',
            'college clubs organizations site:edu',
            'university student organizations site:campuslabs.com'
        ]

    async def discover_organization_links(self, max_links: int = 50) -> List[Dict]:
        """Discover organization directory links from the internet"""
        logger.info(f"Searching for organization directory links (target: {max_links} links)...")
        
        discovered_links = []
        
        # Method 1: Search with Playwright (simulating Google search)
        search_links = await self.search_with_playwright()
        discovered_links.extend(search_links)
        
        # Method 2: Direct platform searches
        platform_links = await self.search_platforms_directly()
        discovered_links.extend(platform_links)
        
        # Method 3: Crawl known platform domains
        crawl_links = await self.crawl_platform_domains()
        discovered_links.extend(crawl_links)
        
        # Validate and deduplicate
        valid_links = self.validate_and_deduplicate(discovered_links, max_links)
        
        logger.info(f"Found {len(valid_links)} valid organization directory links")
        return valid_links

    async def search_with_playwright(self) -> List[Dict]:
        """Search for organization links using web search"""
        logger.info("Searching for organization links on the web...")
        links = []
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            page = await context.new_page()
            
            # Search on DuckDuckGo (more permissive than Google for automated searches)
            for query in self.search_queries[:5]:  # Limit queries to avoid rate limiting
                try:
                    search_url = f"https://duckduckgo.com/?q={quote(query)}"
                    logger.info(f"Searching: {query}")
                    
                    await page.goto(search_url, timeout=15000)
                    await page.wait_for_timeout(2000)
                    
                    # Extract links from search results
                    search_links = await page.query_selector_all('a[href]')
                    
                    for link_element in search_links:
                        try:
                            href = await link_element.get_attribute('href')
                            if href and self.matches_target_pattern(href):
                                # Clean the URL (remove tracking parameters)
                                clean_url = self.clean_url(href)
                                if clean_url:
                                    links.append({
                                        'url': clean_url,
                                        'source': 'search',
                                        'platform': self.detect_platform(clean_url),
                                        'school_name': self.extract_school_name(clean_url)
                                    })
                                    logger.info(f"Found from search: {clean_url}")
                        except Exception as e:
                            continue
                    
                    await asyncio.sleep(3)  # Be respectful with delays
                    
                except Exception as e:
                    logger.debug(f"Search error for query '{query}': {e}")
                    continue
            
            await browser.close()
        
        return links

    async def search_platforms_directly(self) -> List[Dict]:
        """Search platform domains directly for organization directories"""
        logger.info("Searching platform domains directly...")
        links = []
        
        platform_domains = [
            'campuslabs.com',
            'collegiatelink.net',
            'orgsync.com',
            'presence.io',
            'campusgroups.com'
        ]
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()
            
            for domain in platform_domains:
                try:
                    # Search for subdomains with organization pages
                    search_patterns = [
                        f"site:{domain} organizations",
                        f"site:{domain} engage/organizations",
                        f"site:{domain}/organizations"
                    ]
                    
                    for pattern in search_patterns:
                        try:
                            search_url = f"https://duckduckgo.com/?q={quote(pattern)}"
                            await page.goto(search_url, timeout=10000)
                            await page.wait_for_timeout(2000)
                            
                            # Extract results
                            result_links = await page.query_selector_all('a[href]')
                            
                            for link_element in result_links:
                                try:
                                    href = await link_element.get_attribute('href')
                                    if href and self.matches_target_pattern(href):
                                        clean_url = self.clean_url(href)
                                        if clean_url:
                                            links.append({
                                                'url': clean_url,
                                                'source': f'platform_{domain}',
                                                'platform': self.detect_platform(clean_url),
                                                'school_name': self.extract_school_name(clean_url)
                                            })
                                            logger.info(f"Found from platform search: {clean_url}")
                                except:
                                    continue
                            
                            await asyncio.sleep(2)
                            
                        except Exception as e:
                            logger.debug(f"Platform search error for {pattern}: {e}")
                            continue
                    
                except Exception as e:
                    logger.debug(f"Error searching domain {domain}: {e}")
                    continue
            
            await browser.close()
        
        return links

    async def crawl_platform_domains(self) -> List[Dict]:
        """Crawl known platform domains for organization directories"""
        logger.info("Crawling platform domains for organization links...")
        links = []
        
        # Common subdomain patterns for universities
        common_prefixes = [
            'utexas', 'gatech', 'stanford', 'berkeley', 'ucla', 'usc', 'nyu', 
            'columbia', 'harvard', 'yale', 'princeton', 'mit', 'caltech',
            'unc', 'duke', 'ncstate', 'virginia', 'vtech', 'miami', 'fsu',
            'ufl', 'georgia', 'alabama', 'auburn', 'tennessee', 'vanderbilt',
            'rice', 'baylor', 'tcu', 'smu', 'ou', 'osu', 'texas', 'tamu'
        ]
        
        platform_bases = [
            '.campuslabs.com/engage/organizations',
            '.collegiatelink.net/organizations'
        ]
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            page = await context.new_page()
            
            for prefix in common_prefixes[:20]:  # Limit to avoid too many requests
                for base in platform_bases:
                    try:
                        test_url = f"https://{prefix}{base}"
                        logger.debug(f"Testing: {test_url}")
                        
                        response = await page.goto(test_url, timeout=8000)
                        
                        if response and response.status == 200:
                            # Check if page actually contains organizations
                            content = await page.content()
                            if self.is_valid_organization_page(content):
                                links.append({
                                    'url': test_url,
                                    'source': 'crawl',
                                    'platform': self.detect_platform(test_url),
                                    'school_name': self.extract_school_name(test_url)
                                })
                                logger.info(f"Found by crawling: {test_url}")
                        
                        await asyncio.sleep(0.5)  # Small delay between requests
                        
                    except Exception as e:
                        logger.debug(f"Crawl error for {test_url}: {e}")
                        continue
            
            await browser.close()
        
        return links

    def matches_target_pattern(self, url: str) -> bool:
        """Check if URL matches our target patterns"""
        if not url:
            return False
        
        for pattern in self.target_patterns:
            if re.match(pattern, url, re.IGNORECASE):
                return True
        
        return False

    def clean_url(self, url: str) -> Optional[str]:
        """Clean URL by removing tracking parameters and validating"""
        if not url:
            return None
        
        # Remove common tracking parameters
        if '?' in url:
            base_url = url.split('?')[0]
        else:
            base_url = url
        
        # Validate cleaned URL
        if self.matches_target_pattern(base_url):
            return base_url
        
        return None

    def detect_platform(self, url: str) -> str:
        """Detect platform type from URL"""
        url_lower = url.lower()
        
        if 'campuslabs.com' in url_lower:
            return 'campuslabs'
        elif 'collegiatelink.net' in url_lower:
            return 'collegiatelink'
        elif 'orgsync.com' in url_lower:
            return 'orgsync'
        elif 'presence.io' in url_lower:
            return 'presence'
        elif 'campusgroups.com' in url_lower:
            return 'campusgroups'
        elif 'involved.' in url_lower:
            return 'involved'
        elif 'engage.' in url_lower:
            return 'engage'
        else:
            return 'other'

    def extract_school_name(self, url: str) -> str:
        """Extract school name from URL"""
        try:
            parsed = urlparse(url)
            hostname = parsed.hostname
            
            if not hostname:
                return "Unknown"
            
            # Handle different formats
            if 'campuslabs.com' in hostname:
                # Format: school.campuslabs.com
                school_part = hostname.split('.campuslabs.com')[0]
            elif 'collegiatelink.net' in hostname:
                # Format: school.collegiatelink.net
                school_part = hostname.split('.collegiatelink.net')[0]
            elif hostname.startswith('involved.'):
                # Format: involved.school.edu
                school_part = hostname.replace('involved.', '').split('.')[0]
            elif hostname.startswith('engage.'):
                # Format: engage.school.edu
                school_part = hostname.replace('engage.', '').split('.')[0]
            else:
                # Format: school.edu or other
                school_part = hostname.split('.')[0]
            
            # Clean up common patterns
            school_part = school_part.replace('-', ' ').replace('_', ' ')
            
            return school_part.title()
            
        except Exception as e:
            logger.debug(f"Error extracting school name from {url}: {e}")
            return "Unknown"

    def is_valid_organization_page(self, content: str) -> bool:
        """Check if page content indicates it's a valid organization directory"""
        content_lower = content.lower()
        
        # Look for organization-related keywords
        org_keywords = [
            'student organization', 'student club', 'campus organization',
            'organizations', 'clubs', 'join', 'browse', 'directory',
            'get involved', 'student activities'
        ]
        
        keyword_count = sum(1 for keyword in org_keywords if keyword in content_lower)
        
        # Check for typical organization page structure
        structure_indicators = [
            'class="organization', 'class="club', 'data-org-',
            'href="/organization/', 'href="/club/', '/engage/organization'
        ]
        
        structure_count = sum(1 for indicator in structure_indicators if indicator in content)
        
        return keyword_count >= 2 and structure_count >= 1

    def validate_and_deduplicate(self, links: List[Dict], max_links: int) -> List[Dict]:
        """Validate and deduplicate discovered links"""
        # Remove duplicates based on URL
        seen_urls = set()
        unique_links = []
        
        for link in links:
            url = link['url']
            if url not in seen_urls and self.matches_target_pattern(url):
                seen_urls.add(url)
                unique_links.append(link)
        
        # Sort by platform preference and school name
        platform_priority = {
            'campuslabs': 1,
            'collegiatelink': 2,
            'involved': 3,
            'engage': 4,
            'other': 5
        }
        
        unique_links.sort(key=lambda x: (
            platform_priority.get(x['platform'], 5),
            x['school_name']
        ))
        
        # Limit results
        return unique_links[:max_links]

class EnhancedClubScraper:
    def __init__(self):
        # Supabase configuration
        self.supabase_url = os.getenv('SUPABASE_URL')
        self.supabase_key = os.getenv('SUPABASE_ANON_KEY')
        self.supabase: Client = create_client(self.supabase_url, self.supabase_key)
        
        self.discovery = UniversityClubLinkDiscovery()
        self.scraped_clubs: Set[str] = set()
        
        # Platform configurations
        self.platform_configs = {
            'campuslabs': {
                'load_more_selectors': [
                    'div[style*="Load More"]',
                    'span:contains("Load More")',
                    'button:contains("Load More")',
                    '[data-testid*="load-more"]',
                    '.load-more'
                ],
                'club_link_selectors': [
                    'a[href*="/engage/organization/"]',
                    'a[href*="/organization/"]'
                ]
            },
            'collegiatelink': {
                'load_more_selectors': [
                    '.load-more',
                    'button:contains("Load More")',
                    '[class*="load-more"]'
                ],
                'club_link_selectors': [
                    'a[href*="/organization/"]',
                    'a[href*="/org/"]'
                ]
            },
            'default': {
                'load_more_selectors': [
                    'div[style*="Load More"]',
                    'span:contains("Load More")',
                    'button:contains("Load More")',
                    '[data-testid*="load-more"]',
                    '.load-more',
                    'button[class*="load"]',
                    '[class*="show-more"]'
                ],
                'club_link_selectors': [
                    'a[href*="/organization/"]',
                    'a[href*="/org/"]',
                    'a[href*="/club/"]',
                    'a[href*="/group/"]',
                    'a[href*="organization"]'
                ]
            }
        }

    def get_platform_config(self, platform: str) -> Dict:
        """Get configuration for specific platform"""
        return self.platform_configs.get(platform, self.platform_configs['default'])

    def display_discovered_links(self, links: List[Dict]) -> List[Dict]:
        """Display discovered links and let user choose which to scrape"""
        if not links:
            print("No organization directory links discovered.")
            return []
        
        print(f"\n{'='*80}")
        print("DISCOVERED ORGANIZATION DIRECTORY LINKS")
        print(f"{'='*80}")
        
        for i, link in enumerate(links, 1):
            print(f"\n{i:2d}. {link['school_name']}")
            print(f"     URL: {link['url']}")
            print(f"     Platform: {link['platform']}")
            print(f"     Source: {link['source']}")
        
        print(f"\n{'='*80}")
        print(f"Total found: {len(links)} organization directories")
        
        # Get user selection
        while True:
            try:
                selection = input(f"\nEnter numbers to scrape (comma-separated, 'all' for all, or 'quit'): ").strip()
                
                if selection.lower() in ['quit', 'exit', 'q']:
                    return []
                
                if selection.lower() == 'all':
                    confirm = input(f"\nScrape all {len(links)} directories? This may take a long time. (y/n): ").strip().lower()
                    if confirm in ['y', 'yes']:
                        return links
                    else:
                        continue
                
                # Parse selection
                selected_indices = []
                for num in selection.split(','):
                    num = num.strip()
                    if num.isdigit():
                        idx = int(num) - 1
                        if 0 <= idx < len(links):
                            selected_indices.append(idx)
                        else:
                            print(f"Invalid number: {num}")
                
                if selected_indices:
                    selected_links = [links[i] for i in selected_indices]
                    
                    # Show selection
                    print(f"\nSelected {len(selected_links)} directories:")
                    for link in selected_links:
                        print(f"  - {link['school_name']} ({link['platform']})")
                    
                    confirm = input("\nProceed with scraping? (y/n): ").strip().lower()
                    if confirm in ['y', 'yes']:
                        return selected_links
                    else:
                        continue
                else:
                    print("No valid selections made.")
                    
            except KeyboardInterrupt:
                print("\nOperation cancelled.")
                return []
            except Exception as e:
                print(f"Error processing selection: {e}")

    def setup_selenium_driver(self):
        """Setup Selenium WebDriver with proper configuration"""
        chrome_options = Options()
        chrome_options.add_argument('--no-sandbox')
        chrome_options.add_argument('--disable-dev-shm-usage')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        
        # For debugging, keep headless=False. Set to True for production
        # chrome_options.add_argument('--headless')
        
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        
        # Execute script to remove webdriver property
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        return driver

    def load_all_clubs_selenium(self, driver, website_config: Dict) -> List[str]:
        """Use Selenium to load all clubs by clicking 'Load More' until all are loaded"""
        logger.info(f"Loading {website_config['url']} with Selenium...")
        
        try:
            driver.get(website_config['url'])
            time.sleep(5)
            
            all_club_links = set()
            load_more_clicks = 0
            max_load_more_clicks = 50
            
            platform_config = self.get_platform_config(website_config['platform'])
            
            while load_more_clicks < max_load_more_clicks:
                # Find current club links
                current_links = self.find_club_links_selenium(driver, website_config, platform_config)
                new_links = set(current_links) - all_club_links
                
                if new_links:
                    all_club_links.update(new_links)
                    logger.info(f"Found {len(new_links)} new club links. Total: {len(all_club_links)}")
                
                # Try to find and click "Load More" button
                load_more_found = False
                
                for selector in platform_config['load_more_selectors']:
                    try:
                        if 'contains' in selector:
                            if selector.startswith('span:contains'):
                                xpath = "//span[contains(text(), 'Load More')]"
                            elif selector.startswith('button:contains'):
                                xpath = "//button[contains(text(), 'Load More')]"
                            else:
                                continue
                            
                            load_more_elements = driver.find_elements(By.XPATH, xpath)
                        else:
                            load_more_elements = driver.find_elements(By.CSS_SELECTOR, selector)
                        
                        for element in load_more_elements:
                            try:
                                if element.is_displayed() and element.is_enabled():
                                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                                    time.sleep(1)
                                    
                                    try:
                                        element.click()
                                    except ElementClickInterceptedException:
                                        driver.execute_script("arguments[0].click();", element)
                                    
                                    load_more_found = True
                                    load_more_clicks += 1
                                    logger.info(f"Clicked 'Load More' button #{load_more_clicks}")
                                    
                                    time.sleep(3)
                                    break
                            except Exception as e:
                                continue
                        
                        if load_more_found:
                            break
                            
                    except Exception as e:
                        continue
                
                # If no load more, try scrolling
                if not load_more_found:
                    last_height = driver.execute_script("return document.body.scrollHeight")
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(3)
                    new_height = driver.execute_script("return document.body.scrollHeight")
                    
                    if new_height == last_height:
                        logger.info("No more content to load")
                        break
                
                time.sleep(2)
            
            # Final collection
            final_links = self.find_club_links_selenium(driver, website_config, platform_config)
            all_club_links.update(final_links)
            
            logger.info(f"Total club links found: {len(all_club_links)}")
            return list(all_club_links)
            
        except Exception as e:
            logger.error(f"Error loading clubs: {e}")
            return []

    def find_club_links_selenium(self, driver, website_config: Dict, platform_config: Dict) -> List[str]:
        """Find all club links on the current page"""
        club_links = []
        
        for selector in platform_config['club_link_selectors']:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                for element in elements:
                    href = element.get_attribute('href')
                    if href:
                        if href.startswith('/'):
                            href = website_config.get('base_url', urlparse(website_config['url']).scheme + '://' + urlparse(website_config['url']).netloc) + href
                        
                        if href not in club_links:
                            club_links.append(href)
                            
            except Exception as e:
                continue
        
        return club_links

    async def scrape_club_detail_with_playwright(self, club_url: str, school: str) -> Optional[Dict]:
        """Scrape detailed club information using Playwright"""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            page = await context.new_page()
            
            try:
                logger.info(f"Scraping club detail: {club_url}")
                
                await page.goto(club_url, wait_until='networkidle', timeout=30000)
                await page.wait_for_timeout(3000)
                
                # Extract club name
                club_name = self.extract_club_name_from_url(club_url) or "Unknown Club"
                
                name_selectors = ['h1', 'h2', '.club-name', '.org-name', '[class*="title"]', '[class*="name"]']
                
                for selector in name_selectors:
                    try:
                        name_element = await page.query_selector(selector)
                        if name_element:
                            name_text = (await name_element.inner_text()).strip()
                            if name_text and len(name_text) > 2 and len(name_text) < 100:
                                club_name = name_text
                                break
                    except:
                        continue
                
                # Initialize club data
                club_data = {
                    'name': club_name,
                    'description': '',
                    'email': '',
                    'address': '',
                    'website': '',
                    'social_media': [],
                    'phone': '',
                    'meeting_times': '',
                    'meeting_location': '',
                    'contact_person': '',
                    'categories': [],
                    'school': school,
                    'scraped_at': time.strftime('%Y-%m-%d %H:%M:%S'),
                    'detail_page_url': club_url
                }
                
                # Get page content
                page_content = await page.content()
                soup = BeautifulSoup(page_content, 'html.parser')
                all_text = soup.get_text()
                
                # Extract information
                await self.extract_description(page, club_data)
                await self.extract_contact_info(page, club_data, all_text)
                await self.extract_meeting_info(page, club_data, all_text)
                await self.extract_categories(page, club_data)
                await self.extract_social_media(page, club_data)
                
                await browser.close()
                
                logger.info(f"Successfully scraped {club_name}")
                return club_data
                
            except Exception as e:
                logger.error(f"Error scraping {club_url}: {e}")
                await browser.close()
                return None

    def extract_club_name_from_url(self, url: str) -> Optional[str]:
        """Extract club name from URL"""
        try:
            parts = url.split('/')
            if 'organization' in parts:
                idx = parts.index('organization')
                if idx + 1 < len(parts):
                    name = parts[idx + 1]
                    name = name.replace('-', ' ').replace('_', ' ')
                    return name.title()
        except:
            pass
        return None

    async def extract_description(self, page: Page, club_data: Dict):
        """Extract club description"""
        desc_selectors = ['.DescriptionExcerpt', '[class*="description"]', '[class*="about"]', '[class*="summary"]', '.content', '.details', '.info', 'p']
        
        for selector in desc_selectors:
            try:
                desc_elements = await page.query_selector_all(selector)
                for desc_element in desc_elements:
                    desc_text = (await desc_element.inner_text()).strip()
                    if desc_text and len(desc_text) > 50:
                        club_data['description'] = desc_text
                        return
            except:
                continue

    async def extract_contact_info(self, page: Page, club_data: Dict, all_text: str):
        """Extract email, phone, and contact information"""
        # Email extraction
        email_selectors = ['[href^="mailto:"]', '[class*="email"]', '[data-testid*="email"]']
        
        for selector in email_selectors:
            try:
                email_elements = await page.query_selector_all(selector)
                for email_element in email_elements:
                    if selector == '[href^="mailto:"]':
                        email_href = await email_element.get_attribute('href')
                        if email_href:
                            email = email_href.replace('mailto:', '')
                            if self.is_valid_email(email):
                                club_data['email'] = email
                                break
                    else:
                        email_text = (await email_element.inner_text()).strip()
                        if self.is_valid_email(email_text):
                            club_data['email'] = email_text
                            break
                if club_data['email']:
                    break
            except:
                continue
        
        # If no email found, use regex
        if not club_data['email']:
            email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
            emails = re.findall(email_pattern, all_text)
            filtered_emails = [email for email in emails if self.is_valid_email(email)]
            if filtered_emails:
                club_data['email'] = filtered_emails[0]
        
        # Extract phone
        phone_pattern = r'\b(?:\+?1[-.\s]?)?\(?([0-9]{3})\)?[-.\s]?([0-9]{3})[-.\s]?([0-9]{4})\b'
        phones = re.findall(phone_pattern, all_text)
        if phones:
            phone = f"({phones[0][0]}) {phones[0][1]}-{phones[0][2]}"
            club_data['phone'] = phone

    async def extract_meeting_info(self, page: Page, club_data: Dict, all_text: str):
        """Extract meeting times and location"""
        meeting_keywords = ['meet', 'meeting', 'when', 'time', 'schedule', 'every', 'weekly', 'monthly']
        meeting_selectors = ['[class*="meeting"]', '[class*="schedule"]', '[class*="time"]']
        
        meeting_info = []
        for selector in meeting_selectors:
            try:
                meeting_elements = await page.query_selector_all(selector)
                for meeting_element in meeting_elements:
                    meeting_text = (await meeting_element.inner_text()).strip()
                    if meeting_text and any(keyword in meeting_text.lower() for keyword in meeting_keywords):
                        meeting_info.append(meeting_text)
            except:
                continue
        
        club_data['meeting_times'] = ' | '.join(meeting_info[:2])

    async def extract_categories(self, page: Page, club_data: Dict):
        """Extract categories/tags"""
        category_selectors = ['[class*="category"]', '[class*="tag"]', '[class*="type"]']
        
        categories = []
        for selector in category_selectors:
            try:
                cat_elements = await page.query_selector_all(selector)
                for cat_element in cat_elements:
                    cat_text = (await cat_element.inner_text()).strip()
                    if cat_text and len(cat_text) < 50:
                        categories.append(cat_text)
            except:
                continue
        
        club_data['categories'] = categories[:5]

    async def extract_social_media(self, page: Page, club_data: Dict):
        """Extract social media links"""
        social_platforms = ['facebook', 'twitter', 'instagram', 'linkedin', 'youtube', 'tiktok']
        social_links = []
        
        for platform in social_platforms:
            try:
                social_elements = await page.query_selector_all(f'a[href*="{platform}"]')
                for social_element in social_elements:
                    social_url = await social_element.get_attribute('href')
                    if social_url and social_url not in social_links:
                        social_links.append(social_url)
            except:
                continue
        
        club_data['social_media'] = social_links

    def is_valid_email(self, email: str) -> bool:
        """Validate email address"""
        if not email or len(email) < 5:
            return False
        
        email_pattern = r'^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}$'
        if not re.match(email_pattern, email):
            return False
        
        # Filter out invalid emails
        invalid_patterns = ['example', 'test', 'noreply', 'no-reply', 'donotreply']
        
        email_lower = email.lower()
        if any(pattern in email_lower for pattern in invalid_patterns):
            return False
        
        return True

    def insert_to_supabase(self, club_data: Dict) -> bool:
        """Insert club data into Supabase"""
        try:
            logger.debug(f"Attempting to insert club: {club_data['name']}")
            
            # Check if club already exists
            try:
                existing = self.supabase.table('clubs').select('id').eq('detail_page_url', club_data['detail_page_url']).execute()
            except Exception as column_error:
                logger.warning(f"detail_page_url column might not exist, checking by name and school: {column_error}")
                existing = self.supabase.table('clubs').select('id').eq('name', club_data['name']).eq('school', club_data['school']).execute()
            
            if existing.data:
                logger.info(f"Club {club_data['name']} already exists, skipping...")
                return True
            
            # Create clean data
            clean_club_data = {
                'name': club_data.get('name', ''),
                'description': club_data.get('description', ''),
                'email': club_data.get('email', ''),
                'address': club_data.get('address', ''),
                'website': club_data.get('website', ''),
                'social_media': club_data.get('social_media', []),
                'phone': club_data.get('phone', ''),
                'meeting_times': club_data.get('meeting_times', ''),
                'meeting_location': club_data.get('meeting_location', ''),
                'contact_person': club_data.get('contact_person', ''),
                'categories': club_data.get('categories', []),
                'school': club_data.get('school', ''),
                'detail_page_url': club_data.get('detail_page_url', ''),
                'scraped_at': club_data.get('scraped_at', time.strftime('%Y-%m-%d %H:%M:%S'))
            }
            
            # Insert new club
            result = self.supabase.table('clubs').insert(clean_club_data).execute()
            
            if result.data:
                logger.info(f"Successfully inserted {club_data['name']} into Supabase")
                return True
            else:
                logger.error(f"Failed to insert {club_data['name']}: {result}")
                return False
                
        except Exception as e:
            logger.error(f"Error inserting to Supabase: {e}")
            return False

    async def run_auto_discovery_scraper(self):
        """Main function with automatic link discovery"""
        logger.info("Starting University Club Scraper with Auto-Discovery...")
        
        # Verify Supabase connection
        if not self.supabase_url or not self.supabase_key:
            logger.error("Supabase credentials not found. Please check your .env file.")
            return
        
        # Get number of schools to search for
        print(f"\n{'='*80}")
        print("UNIVERSITY CLUB SCRAPER - AUTO DISCOVERY MODE")
        print(f"{'='*80}")
        print("\nThis scraper will automatically find university organization directories")
        print("from various platforms like CampusLabs, CollegiateLink, and others.")
        
        while True:
            try:
                max_schools_input = input(f"\nHow many schools do you want to discover? (default: 20, max: 100): ").strip()
                
                if not max_schools_input:
                    max_schools = 20
                    break
                elif max_schools_input.isdigit():
                    max_schools = min(int(max_schools_input), 100)
                    break
                else:
                    print("Please enter a valid number.")
                    
            except KeyboardInterrupt:
                print("\nOperation cancelled.")
                return
        
        print(f"\nSearching for up to {max_schools} organization directories...")
        
        # Discover organization directory links
        discovered_links = await self.discovery.discover_organization_links(max_schools)
        
        if not discovered_links:
            print("No organization directory links found. Try again later or check your internet connection.")
            return
        
        # Display and let user select
        selected_links = self.display_discovered_links(discovered_links)
        
        if not selected_links:
            print("No directories selected for scraping.")
            return
        
        # Convert to website configs and scrape
        total_clubs = 0
        
        for i, link_data in enumerate(selected_links, 1):
            try:
                logger.info(f"Processing {i}/{len(selected_links)}: {link_data['school_name']}")
                
                # Create website config from discovered link
                website_config = {
                    'name': link_data['school_name'],
                    'url': link_data['url'],
                    'base_url': f"{urlparse(link_data['url']).scheme}://{urlparse(link_data['url']).netloc}",
                    'platform': link_data['platform']
                }
                
                # Use Selenium to load all club links
                driver = self.setup_selenium_driver()
                
                try:
                    club_links = self.load_all_clubs_selenium(driver, website_config)
                    logger.info(f"Found {len(club_links)} club links from {link_data['school_name']}")
                    
                    if not club_links:
                        logger.warning(f"No club links found for {link_data['school_name']}, skipping...")
                        continue
                    
                    # Use Playwright to scrape each club's detail page
                    for j, club_url in enumerate(club_links):
                        if club_url in self.scraped_clubs:
                            continue
                        
                        logger.info(f"Processing club {j+1}/{len(club_links)}: {club_url}")
                        
                        club_data = await self.scrape_club_detail_with_playwright(
                            club_url, 
                            link_data['school_name'].lower().replace(' ', '_')
                        )
                        
                        if club_data:
                            if self.insert_to_supabase(club_data):
                                total_clubs += 1
                                self.scraped_clubs.add(club_url)
                        
                        # Be respectful with delays
                        await asyncio.sleep(2)
                        
                        # Optional: limit for testing (uncomment for testing)
                        # if j >= 5:  # Remove this for full scraping
                        #     break
                    
                except Exception as e:
                    logger.error(f"Error processing {link_data['school_name']}: {e}")
                finally:
                    driver.quit()
                
                # Delay between schools
                await asyncio.sleep(10)
                
                print(f"\nCompleted {i}/{len(selected_links)} schools. Total clubs scraped so far: {total_clubs}")
                
            except Exception as e:
                logger.error(f"Error with {link_data['school_name']}: {e}")
                continue
        
        print(f"\n{'='*80}")
        print("SCRAPING COMPLETED!")
        print(f"{'='*80}")
        print(f"Total organization directories processed: {len(selected_links)}")
        print(f"Total clubs scraped and saved: {total_clubs}")
        print(f"{'='*80}")

# SQL for creating the clubs table
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS clubs (
    id BIGSERIAL PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    email TEXT,
    address TEXT,
    website TEXT,
    social_media TEXT[],
    phone TEXT,
    meeting_times TEXT,
    meeting_location TEXT,
    contact_person TEXT,
    categories TEXT[],
    school TEXT NOT NULL,
    detail_page_url TEXT UNIQUE,
    scraped_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Create indexes for better performance
CREATE INDEX IF NOT EXISTS idx_clubs_school ON clubs(school);
CREATE INDEX IF NOT EXISTS idx_clubs_name ON clubs(name);
CREATE INDEX IF NOT EXISTS idx_clubs_email ON clubs(email);
CREATE INDEX IF NOT EXISTS idx_clubs_detail_url ON clubs(detail_page_url);
"""

async def main():
    """Main function to run the auto-discovery scraper"""
    scraper = EnhancedClubScraper()
    await scraper.run_auto_discovery_scraper()

if __name__ == "__main__":
    print("Enhanced University Club Scraper - Auto Discovery Mode")
    print("=" * 60)
    print("\nThis scraper will:")
    print("1. Automatically discover university organization directory URLs")
    print("2. Show you a list of discovered directories to choose from")
    print("3. Scrape the selected directories for club information")
    print("\nBefore running:")
    print("1. Install: pip install playwright selenium supabase beautifulsoup4 requests python-dotenv webdriver-manager")
    print("2. Install Playwright browsers: playwright install")
    print("3. Create .env file with Supabase credentials")
    print("4. Create the 'clubs' table in Supabase using the provided SQL")
    print("\nStarting auto-discovery scraper...")
    
    asyncio.run(main())