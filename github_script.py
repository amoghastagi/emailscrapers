import json
import requests
from bs4 import BeautifulSoup
import re
import time
import random
from urllib.parse import urljoin, urlparse
import csv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import warnings
warnings.filterwarnings("ignore")

class StargazersEmailScraper:
    def __init__(self, use_selenium=False):
        self.use_selenium = use_selenium
        self.stargazers = []
        self.emails_found = []
        self.driver = None
        
        # Setup requests session
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        
        # Email regex pattern
        self.email_pattern = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
    
    def setup_selenium(self):
        """Setup Selenium driver for JavaScript-heavy pages"""
        if self.driver:
            return
            
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        
        try:
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
            print("✅ Selenium WebDriver initialized")
        except Exception as e:
            print(f"⚠️  Selenium setup failed: {e}")
            self.driver = None
    
    def scrape_stargazers_page(self, stargazers_url):
        """Scrape all usernames from a stargazers page with proper pagination"""
        print(f"🔍 Scraping stargazers from: {stargazers_url}")
        
        try:
            page = 1
            all_usernames = []
            consecutive_empty_pages = 0
            max_empty_pages = 3  # Stop after 3 consecutive empty pages
            
            while consecutive_empty_pages < max_empty_pages:
                if page == 1:
                    current_url = stargazers_url
                else:
                    # GitHub stargazers pagination
                    current_url = f"{stargazers_url}?page={page}"
                
                print(f"   📄 Scraping page {page}...")
                
                try:
                    response = self.session.get(current_url, timeout=15)
                    response.raise_for_status()
                    
                    soup = BeautifulSoup(response.text, 'html.parser')
                    
                    # Multiple selectors to find stargazer usernames
                    # Try different selectors that GitHub might use
                    stargazer_links = []
                    
                    # Try the most common selectors for stargazers
                    selectors = [
                        'a[data-hovercard-type="user"]',  # Primary selector
                        'a[href^="/"][data-hovercard-type="user"]',  # More specific
                        '.js-user-link',  # Alternative selector
                        'a[href*="github.com/"][data-hovercard-type="user"]',  # Full URL format
                        'a[data-octo-click="hovercard-link-click"]',  # Another GitHub pattern
                    ]
                    
                    for selector in selectors:
                        stargazer_links = soup.select(selector)
                        if stargazer_links:
                            break
                    
                    # If no links found with data-hovercard-type, try broader search
                    if not stargazer_links:
                        # Look for links in the stargazers container
                        stargazers_container = soup.find('div', class_='d-flex flex-wrap')
                        if stargazers_container:
                            stargazer_links = stargazers_container.find_all('a', href=True)
                    
                    # Extract usernames from found links
                    page_usernames = []
                    for link in stargazer_links:
                        href = link.get('href')
                        if href:
                            # Handle both relative and absolute URLs
                            if href.startswith('/'):
                                # Relative URL: /username
                                username = href[1:]  # Remove leading slash
                            elif 'github.com/' in href:
                                # Absolute URL: https://github.com/username
                                username = href.split('github.com/')[-1]
                            else:
                                continue
                            
                            # Clean username and validate
                            username = username.split('?')[0]  # Remove query parameters
                            username = username.split('/')[0]  # Take first part if there are more slashes
                            
                            # Skip if username is empty, too long, or contains invalid characters
                            if (username and 
                                len(username) <= 39 and  # GitHub username max length
                                username not in ['orgs', 'topics', 'explore', 'settings', 'notifications'] and  # Skip GitHub pages
                                not username.startswith('.') and
                                username not in all_usernames):
                                
                                all_usernames.append(username)
                                page_usernames.append(username)
                    
                    if page_usernames:
                        print(f"   ✅ Found {len(page_usernames)} unique usernames on page {page}")
                        consecutive_empty_pages = 0  # Reset counter
                    else:
                        print(f"   ⚠️  No usernames found on page {page}")
                        consecutive_empty_pages += 1
                    
                    # Check if there's a next page button
                    next_button = soup.select_one('a[rel="next"]')
                    has_next_page = next_button is not None
                    
                    # Also check if we're at the end by looking for pagination info
                    pagination_info = soup.select_one('.paginate-container')
                    if pagination_info:
                        # Look for disabled next button or end indicator
                        disabled_next = soup.select_one('a[rel="next"][aria-disabled="true"]')
                        if disabled_next:
                            has_next_page = False
                    
                    if not has_next_page and consecutive_empty_pages > 0:
                        print(f"   📄 No more pages found")
                        break
                    
                    page += 1
                    
                    # Add delay to be respectful to GitHub
                    time.sleep(random.uniform(1, 3))
                    
                    # Safety limit to prevent infinite loops
                    if page > 200:  # Increased from 50 to handle large repos
                        print(f"   ⚠️  Reached page limit (200), stopping")
                        break
                        
                except requests.exceptions.RequestException as e:
                    print(f"   ❌ Request error on page {page}: {e}")
                    consecutive_empty_pages += 1
                    if consecutive_empty_pages >= max_empty_pages:
                        break
                    time.sleep(5)  # Wait longer before retrying
                    continue
                
            print(f"🎉 Total unique stargazers found: {len(all_usernames)}")
            return all_usernames
            
        except Exception as e:
            print(f"❌ Unexpected error in scrape_stargazers_page: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def scrape_github_profile_email(self, username):
        """Scrape a single GitHub profile for email addresses"""
        profile_url = f"https://github.com/{username}"
        
        try:
            print(f"   🔍 Checking profile: {username}")
            
            response = self.session.get(profile_url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            profile_info = {
                'username': username,
                'profile_url': profile_url,
                'emails': [],
                'bio': None,
                'location': None,
                'company': None,
                'website': None,
                'twitter': None,
                'name': None
            }
            
            # Extract name - try multiple selectors
            name_selectors = [
                '[data-test-selector="profile-name"]',
                '.p-name',
                '.vcard-fullname',
                'h1.vcard-names span.p-name'
            ]
            
            for selector in name_selectors:
                name_element = soup.select_one(selector)
                if name_element:
                    profile_info['name'] = name_element.text.strip()
                    break
            
            # Extract direct email from profile
            email_element = soup.select_one('a[href^="mailto:"]')
            if email_element:
                email = email_element.get('href').replace('mailto:', '')
                profile_info['emails'].append(email)
                print(f"   ✅ Found direct email: {email}")
            
            # Extract bio - try multiple selectors
            bio_selectors = [
                '.p-note .user-profile-bio',
                '.p-note',
                '[data-bio-text]',
                '.user-profile-bio'
            ]
            
            for selector in bio_selectors:
                bio_element = soup.select_one(selector)
                if bio_element:
                    profile_info['bio'] = bio_element.text.strip()
                    break
            
            # Extract location
            location_selectors = [
                '[data-test-selector="profile-location"]',
                '.p-label',
                '[aria-label*="location"]'
            ]
            
            for selector in location_selectors:
                location_element = soup.select_one(selector)
                if location_element:
                    profile_info['location'] = location_element.text.strip()
                    break
            
            # Extract company
            company_selectors = [
                '[data-test-selector="profile-company"]',
                '.p-org',
                '[aria-label*="company"]'
            ]
            
            for selector in company_selectors:
                company_element = soup.select_one(selector)
                if company_element:
                    profile_info['company'] = company_element.text.strip()
                    break
            
            # Extract website
            website_selectors = [
                '[data-test-selector="profile-website"] a',
                '.p-label a',
                '.Link--primary'
            ]
            
            for selector in website_selectors:
                website_element = soup.select_one(selector)
                if website_element:
                    profile_info['website'] = website_element.get('href')
                    break
            
            # Extract Twitter/X
            social_links = soup.select('a[href*="twitter.com"], a[href*="x.com"]')
            if social_links:
                profile_info['twitter'] = social_links[0].get('href')
            
            # Look for emails in repositories
            repo_emails = self.find_emails_in_repositories(username)
            profile_info['emails'].extend(repo_emails)
            
            # Look for emails in commit messages
            commit_emails = self.find_emails_in_commits(username)
            profile_info['emails'].extend(commit_emails)
            
            # Remove duplicates and filter out common false positives
            profile_info['emails'] = list(set([
                email for email in profile_info['emails'] 
                if email and not any(
                    domain in email.lower() 
                    for domain in ['github.com', 'example.com', 'test.com', 'noreply', 'no-reply']
                )
            ]))
            
            if profile_info['emails']:
                print(f"   🎉 Found {len(profile_info['emails'])} email(s) for {username}")
                return profile_info
            else:
                print(f"   ⚠️  No emails found for {username}")
                return None
                
        except requests.exceptions.RequestException as e:
            print(f"   ❌ Request error for {username}: {e}")
            return None
        except Exception as e:
            print(f"   ❌ Error scraping {username}: {e}")
            return None
    
    def find_emails_in_repositories(self, username):
        """Find emails in user's repositories"""
        emails = []
        
        try:
            # Get repositories
            repos_url = f"https://github.com/{username}?tab=repositories"
            response = self.session.get(repos_url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Find repository links - updated selector
            repo_links = soup.select(f'a[href*="/{username}/"][href$="/"]')
            
            # Check first few repositories for README files
            for repo_link in repo_links[:3]:  # Limit to first 3 repos
                repo_path = repo_link.get('href')
                if repo_path and '/blob/' not in repo_path:
                    # Try to find README
                    readme_urls = [
                        f"https://github.com{repo_path}blob/main/README.md",
                        f"https://github.com{repo_path}blob/master/README.md",
                        f"https://github.com{repo_path}blob/main/README.rst",
                        f"https://github.com{repo_path}blob/master/README.rst"
                    ]
                    
                    for readme_url in readme_urls:
                        try:
                            readme_response = self.session.get(readme_url, timeout=5)
                            if readme_response.status_code == 200:
                                readme_emails = self.email_pattern.findall(readme_response.text)
                                # Filter out common non-personal emails
                                filtered_emails = [email for email in readme_emails if not any(
                                    domain in email.lower() for domain in ['github.com', 'example.com', 'test.com', 'noreply', 'no-reply']
                                )]
                                emails.extend(filtered_emails)
                                break
                        except:
                            continue
            
        except Exception as e:
            print(f"   ⚠️  Error searching repositories for {username}: {e}")
        
        return emails
    
    def find_emails_in_commits(self, username):
        """Find emails in commit messages (using GitHub's commit pages)"""
        emails = []
        
        try:
            # Get recent commits from user's activity
            commits_url = f"https://github.com/{username}?tab=repositories"
            response = self.session.get(commits_url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Look for recent commit information that might contain emails
            commit_elements = soup.select('.commit-message')
            
            for commit_element in commit_elements[:5]:  # Check first 5 commits
                commit_text = commit_element.get_text()
                commit_emails = self.email_pattern.findall(commit_text)
                filtered_emails = [email for email in commit_emails if not any(
                    domain in email.lower() for domain in ['github.com', 'example.com', 'test.com', 'noreply']
                )]
                emails.extend(filtered_emails)
            
        except Exception as e:
            print(f"   ⚠️  Error searching commits for {username}: {e}")
        
        return emails
    
    def scrape_all_stargazer_emails(self, stargazers_url):
        """Main method to scrape all emails from stargazers"""
        print("🚀 Starting GitHub Stargazers Email Scraper")
        print("=" * 60)
        
        # Step 1: Get all stargazer usernames
        usernames = self.scrape_stargazers_page(stargazers_url)
        
        if not usernames:
            print("❌ No stargazers found")
            return []
        
        print(f"\n📊 Found {len(usernames)} stargazers to process")
        
        # Step 2: Scrape each profile for emails
        all_emails = []
        
        for i, username in enumerate(usernames):
            print(f"\n👤 Processing {i+1}/{len(usernames)}: {username}")
            
            profile_info = self.scrape_github_profile_email(username)
            
            if profile_info and profile_info['emails']:
                all_emails.append(profile_info)
                
                # Save intermediate results every 25 profiles
                if (i + 1) % 25 == 0:
                    self.save_emails_to_files(all_emails, f"stargazers_emails_backup_{i+1}")
            
            # Be respectful to GitHub's servers
            time.sleep(random.uniform(2, 5))
        
        self.emails_found = all_emails
        return all_emails
    
    def save_emails_to_files(self, emails_data, filename_prefix="stargazers_emails"):
        """Save emails to both JSON and CSV files"""
        
        # Save to JSON
        json_filename = f"{filename_prefix}.json"
        try:
            with open(json_filename, 'w', encoding='utf-8') as f:
                json.dump(emails_data, f, indent=2, ensure_ascii=False)
            print(f"📁 Saved to {json_filename}")
        except Exception as e:
            print(f"❌ Error saving JSON: {e}")
        
        # Save to CSV
        csv_filename = f"{filename_prefix}.csv"
        try:
            with open(csv_filename, 'w', newline='', encoding='utf-8') as f:
                fieldnames = ['username', 'name', 'email', 'profile_url', 'bio', 'location', 'company', 'website', 'twitter']
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                
                for profile in emails_data:
                    for email in profile['emails']:
                        writer.writerow({
                            'username': profile['username'],
                            'name': profile.get('name', ''),
                            'email': email,
                            'profile_url': profile['profile_url'],
                            'bio': profile.get('bio', ''),
                            'location': profile.get('location', ''),
                            'company': profile.get('company', ''),
                            'website': profile.get('website', ''),
                            'twitter': profile.get('twitter', '')
                        })
            
            print(f"📁 Saved to {csv_filename}")
        except Exception as e:
            print(f"❌ Error saving CSV: {e}")
    
    def generate_summary_report(self):
        """Generate a summary report"""
        if not self.emails_found:
            print("❌ No email data to summarize")
            return
        
        print(f"\n📊 STARGAZERS EMAIL SCRAPING SUMMARY")
        print("=" * 60)
        
        total_profiles = len(self.emails_found)
        total_emails = sum(len(profile['emails']) for profile in self.emails_found)
        
        print(f"Total profiles with emails: {total_profiles}")
        print(f"Total email addresses found: {total_emails}")
        
        # Show breakdown by email domain
        email_domains = {}
        for profile in self.emails_found:
            for email in profile['emails']:
                domain = email.split('@')[1] if '@' in email else 'unknown'
                email_domains[domain] = email_domains.get(domain, 0) + 1
        
        print(f"\n📧 Email domains breakdown:")
        for domain, count in sorted(email_domains.items(), key=lambda x: x[1], reverse=True)[:10]:
            print(f"   {domain}: {count}")
        
        # Show sample results
        print(f"\n📝 Sample results:")
        for i, profile in enumerate(self.emails_found[:5]):
            print(f"   {i+1}. {profile['username']} ({profile.get('name', 'No name')})")
            for email in profile['emails']:
                print(f"      📧 {email}")
            if profile.get('bio'):
                print(f"      📝 {profile['bio'][:100]}...")
            print()
    
    def cleanup(self):
        """Clean up resources"""
        if self.driver:
            self.driver.quit()

def main():
    """Main execution function"""
    print("🔍 GitHub Stargazers Email Scraper")
    print("=" * 50)
    
    # Get stargazers URL from user
    stargazers_url = input("Enter the GitHub stargazers URL (e.g., https://github.com/vercel/ai/stargazers): ").strip()
    
    if not stargazers_url:
        print("❌ No URL provided")
        return
    
    # Validate URL
    if not stargazers_url.startswith('https://github.com/') or '/stargazers' not in stargazers_url:
        print("❌ Invalid stargazers URL. Please provide a URL like: https://github.com/owner/repo/stargazers")
        return
    
    # Ask about selenium usage
    use_selenium = input("Use Selenium for JavaScript-heavy pages? (y/N): ").strip().lower() == 'y'
    
    scraper = StargazersEmailScraper(use_selenium=use_selenium)
    
    try:
        # Scrape all emails
        emails_data = scraper.scrape_all_stargazer_emails(stargazers_url)
        
        if emails_data:
            # Save results
            scraper.save_emails_to_files(emails_data)
            
            # Generate summary
            scraper.generate_summary_report()
            
            print(f"\n🎉 SUCCESS! Found emails from {len(emails_data)} stargazers")
            print("📁 Results saved to stargazers_emails.json and stargazers_emails.csv")
            
        else:
            print("❌ No emails found")
            
    except KeyboardInterrupt:
        print("\n⚠️  Scraping interrupted by user")
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        scraper.cleanup()

if __name__ == "__main__":
    main()