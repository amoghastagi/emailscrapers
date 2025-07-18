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

class ContactInfoScraper:
    def __init__(self, json_file="devpost_participants1.json", use_selenium=False):
        self.json_file = json_file
        self.use_selenium = use_selenium
        self.participants = []
        self.enhanced_contacts = []
        self.driver = None
        
        # Setup requests session
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })
        
        # Email regex pattern
        self.email_pattern = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
        
        self.load_data()
    
    def load_data(self):
        """Load participant data from JSON file"""
        try:
            with open(self.json_file, 'r', encoding='utf-8') as f:
                self.participants = json.load(f)
            print(f"✅ Loaded {len(self.participants)} participants")
        except FileNotFoundError:
            print(f"❌ File {self.json_file} not found")
            return
        except json.JSONDecodeError:
            print(f"❌ Invalid JSON in {self.json_file}")
            return
    
    def clean_url(self, url):
        """Clean and validate URL to handle duplicates and formatting issues"""
        if not url:
            return None
        
        # Remove any leading/trailing whitespace
        url = url.strip()
        
        # Handle duplicate URLs like "https://github.com/https://github.com/username"
        if url.count('https://github.com/') > 1:
            # Extract the last occurrence
            parts = url.split('https://github.com/')
            if len(parts) > 2:
                # Take the last part and reconstruct
                username = parts[-1]
                url = f"https://github.com/{username}"
        
        # Handle duplicate URLs for other platforms
        if url.count('https://linkedin.com/') > 1:
            parts = url.split('https://linkedin.com/')
            if len(parts) > 2:
                profile_path = parts[-1]
                url = f"https://linkedin.com/{profile_path}"
        
        # Handle duplicate URLs for websites
        if url.count('https://') > 1 and 'github.com' not in url and 'linkedin.com' not in url:
            # Find the last occurrence of https://
            last_https = url.rfind('https://')
            if last_https > 0:
                url = url[last_https:]
        
        # Handle duplicate http:// URLs
        if url.count('http://') > 1:
            last_http = url.rfind('http://')
            if last_http > 0:
                url = url[last_http:]
        
        # Validate URL format
        parsed = urlparse(url)
        if not parsed.scheme:
            # If no scheme, assume https
            url = f"https://{url}"
            parsed = urlparse(url)
        
        # Basic validation
        if not parsed.netloc:
            print(f"   ⚠️  Invalid URL format: {url}")
            return None
        
        return url
    
    def setup_selenium(self):
        """Setup Selenium driver for sites that require JavaScript"""
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
        except Exception as e:
            print(f"⚠️  Selenium setup failed: {e}")
            self.driver = None
    
    def scrape_github_profile(self, github_url, participant_name):
        """Scrape GitHub profile for email and additional info"""
        try:
            # Clean the URL first
            cleaned_url = self.clean_url(github_url)
            if not cleaned_url:
                print(f"   ⚠️  Invalid GitHub URL: {github_url}")
                return {}
            
            print(f"   🔍 Scraping GitHub: {cleaned_url}")
            
            response = self.session.get(cleaned_url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            github_info = {
                'email': None,
                'bio': None,
                'location': None,
                'company': None,
                'twitter': None,
                'website': None,
                'followers': None,
                'following': None,
                'public_repos': None,
                'cleaned_url': cleaned_url
            }
            
            # Extract email from profile
            email_element = soup.select_one('a[href^="mailto:"]')
            if email_element:
                github_info['email'] = email_element.get('href').replace('mailto:', '')
            
            # Extract bio
            bio_element = soup.select_one('.p-note .user-profile-bio')
            if bio_element:
                github_info['bio'] = bio_element.text.strip()
            
            # Extract location
            location_element = soup.select_one('[data-test-selector="profile-location"]')
            if location_element:
                github_info['location'] = location_element.text.strip()
            
            # Extract company
            company_element = soup.select_one('[data-test-selector="profile-company"]')
            if company_element:
                github_info['company'] = company_element.text.strip()
            
            # Extract Twitter
            twitter_element = soup.select_one('a[href*="twitter.com"], a[href*="x.com"]')
            if twitter_element:
                github_info['twitter'] = twitter_element.get('href')
            
            # Extract website
            website_element = soup.select_one('[data-test-selector="profile-website"] a')
            if website_element:
                github_info['website'] = website_element.get('href')
            
            # Extract stats
            stats = soup.select('.text-bold.color-fg-default')
            for stat in stats:
                stat_text = stat.text.strip()
                parent = stat.find_parent()
                if parent and 'followers' in parent.text.lower():
                    github_info['followers'] = stat_text
                elif parent and 'following' in parent.text.lower():
                    github_info['following'] = stat_text
                elif parent and 'repositories' in parent.text.lower():
                    github_info['public_repos'] = stat_text
            
            # Try to find email in README or other public info
            if not github_info['email']:
                github_info['email'] = self.find_email_in_github_repos(cleaned_url)
            
            return github_info
            
        except requests.exceptions.RequestException as e:
            print(f"   ⚠️  Request error for GitHub profile: {e}")
            return {}
        except Exception as e:
            print(f"   ⚠️  Error scraping GitHub profile: {e}")
            return {}
    
    def find_email_in_github_repos(self, github_url):
        """Search for email in GitHub repositories"""
        try:
            username = github_url.split('/')[-1]
            repos_url = f"https://github.com/{username}?tab=repositories"
            
            response = self.session.get(repos_url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Look for README files or repo descriptions
            repo_links = soup.select('a[href*="/' + username + '/"]')[:5]  # Check first 5 repos
            
            for repo_link in repo_links:
                repo_url = urljoin("https://github.com", repo_link.get('href'))
                if '/blob/' not in repo_url:  # Skip file links
                    readme_url = repo_url + '/blob/main/README.md'
                    email = self.find_email_in_readme(readme_url)
                    if email:
                        return email
                        
        except Exception as e:
            print(f"   ⚠️  Error searching repos for email: {e}")
        
        return None
    
    def find_email_in_readme(self, readme_url):
        """Find email in README file"""
        try:
            response = self.session.get(readme_url, timeout=5)
            if response.status_code == 200:
                emails = self.email_pattern.findall(response.text)
                # Filter out common non-personal emails
                filtered_emails = [email for email in emails if not any(
                    domain in email.lower() for domain in ['github.com', 'example.com', 'test.com', 'noreply']
                )]
                if filtered_emails:
                    return filtered_emails[0]
        except:
            pass
        
        return None
    
    def scrape_linkedin_profile(self, linkedin_url, participant_name):
        """Scrape LinkedIn profile (limited due to LinkedIn's restrictions)"""
        try:
            # Clean the URL first
            cleaned_url = self.clean_url(linkedin_url)
            if not cleaned_url:
                print(f"   ⚠️  Invalid LinkedIn URL: {linkedin_url}")
                return {}
            
            print(f"   🔍 Scraping LinkedIn: {cleaned_url}")
            
            # LinkedIn heavily restricts scraping, so this is limited
            response = self.session.get(cleaned_url, timeout=10)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, 'html.parser')
                
                linkedin_info = {
                    'title': None,
                    'company': None,
                    'location': None,
                    'summary': None,
                    'cleaned_url': cleaned_url
                }
                
                # Try to extract basic info (very limited due to LinkedIn's restrictions)
                title_element = soup.select_one('title')
                if title_element:
                    linkedin_info['title'] = title_element.text.strip()
                
                return linkedin_info
            else:
                print(f"   ⚠️  LinkedIn returned status code: {response.status_code}")
                return {}
                
        except requests.exceptions.RequestException as e:
            print(f"   ⚠️  Request error for LinkedIn profile: {e}")
            return {}
        except Exception as e:
            print(f"   ⚠️  Error scraping LinkedIn profile: {e}")
            return {}
    
    def scrape_personal_website(self, website_url, participant_name):
        """Scrape personal website for contact information"""
        try:
            # Clean the URL first
            cleaned_url = self.clean_url(website_url)
            if not cleaned_url:
                print(f"   ⚠️  Invalid website URL: {website_url}")
                return {}
            
            print(f"   🔍 Scraping website: {cleaned_url}")
            
            response = self.session.get(cleaned_url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            website_info = {
                'email': None,
                'phone': None,
                'social_links': [],
                'title': None,
                'description': None,
                'cleaned_url': cleaned_url
            }
            
            # Extract title
            title_element = soup.select_one('title')
            if title_element:
                website_info['title'] = title_element.text.strip()
            
            # Extract description
            desc_element = soup.select_one('meta[name="description"]')
            if desc_element:
                website_info['description'] = desc_element.get('content')
            
            # Find emails in the page
            page_text = soup.get_text()
            emails = self.email_pattern.findall(page_text)
            if emails:
                # Filter out common non-personal emails and get the first one
                filtered_emails = [email for email in emails if not any(
                    domain in email.lower() for domain in ['example.com', 'test.com', 'noreply', 'no-reply']
                )]
                if filtered_emails:
                    website_info['email'] = filtered_emails[0]
            
            # Look for phone numbers
            phone_pattern = re.compile(r'(\+\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}')
            phones = phone_pattern.findall(page_text)
            if phones:
                website_info['phone'] = phones[0]
            
            # Find social media links
            social_links = []
            social_selectors = [
                'a[href*="github.com"]',
                'a[href*="linkedin.com"]',
                'a[href*="twitter.com"]',
                'a[href*="x.com"]',
                'a[href*="instagram.com"]',
                'a[href*="youtube.com"]',
                'a[href*="medium.com"]',
                'a[href*="facebook.com"]'
            ]
            
            for selector in social_selectors:
                links = soup.select(selector)
                for link in links:
                    href = link.get('href')
                    if href and href not in social_links:
                        social_links.append(href)
            
            website_info['social_links'] = social_links
            
            return website_info
            
        except requests.exceptions.RequestException as e:
            print(f"   ⚠️  Request error for website: {e}")
            return {}
        except Exception as e:
            print(f"   ⚠️  Error scraping website: {e}")
            return {}
    
    def enhance_contact_info(self, participant):
        """Enhance contact information for a single participant"""
        enhanced = {
            'name': participant.get('name', ''),
            'username': participant.get('username', ''),
            'devpost_profile': participant.get('profile_url', ''),
            'original_contacts': participant.get('contact_links', {}),
            'enhanced_info': {}
        }
        
        contact_links = participant.get('contact_links', {})
        
        # Process each contact type
        for contact_type, contact_data in contact_links.items():
            url = contact_data.get('url', '')
            
            if not url:
                continue
            
            try:
                if contact_type == 'github' and 'github.com' in url:
                    enhanced['enhanced_info']['github'] = self.scrape_github_profile(url, participant.get('name'))
                
                elif contact_type == 'linkedin' and 'linkedin.com' in url:
                    enhanced['enhanced_info']['linkedin'] = self.scrape_linkedin_profile(url, participant.get('name'))
                
                elif contact_type == 'website' or contact_type == 'other':
                    enhanced['enhanced_info']['website'] = self.scrape_personal_website(url, participant.get('name'))
                
                # Add small delay to be respectful
                time.sleep(random.uniform(1, 3))
                
            except Exception as e:
                print(f"   ⚠️  Error processing {contact_type}: {e}")
                continue
        
        return enhanced
    
    def scrape_all_contacts(self):
        """Scrape enhanced contact information for all participants"""
        print("🚀 Starting enhanced contact information scraping...")
        
        participants_with_contacts = [p for p in self.participants if p.get('contact_links')]
        
        if not participants_with_contacts:
            print("❌ No participants with contact information found")
            return []
        
        print(f"📊 Found {len(participants_with_contacts)} participants with contact links")
        
        enhanced_contacts = []
        
        for i, participant in enumerate(participants_with_contacts):
            print(f"\n📋 Processing participant {i+1}/{len(participants_with_contacts)}: {participant.get('name', 'Unknown')}")
            
            enhanced = self.enhance_contact_info(participant)
            enhanced_contacts.append(enhanced)
            
            # Save intermediate results every 10 participants
            if (i + 1) % 10 == 0:
                self.save_enhanced_contacts(enhanced_contacts, f"enhanced_contacts_backup_{i+1}.json")
        
        self.enhanced_contacts = enhanced_contacts
        return enhanced_contacts
    
    def save_enhanced_contacts(self, contacts, filename="enhanced_contacts.json"):
        """Save enhanced contact information to JSON file"""
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(contacts, f, indent=2, ensure_ascii=False)
            print(f"📁 Enhanced contacts saved to {filename}")
        except Exception as e:
            print(f"❌ Error saving enhanced contacts: {e}")
    
    def export_emails_csv(self, filename="participant_emails.csv"):
        """Export found emails to CSV file"""
        try:
            emails_data = []
            
            for contact in self.enhanced_contacts:
                email_found = False
                email_sources = []
                
                # Check GitHub email
                github_info = contact.get('enhanced_info', {}).get('github', {})
                if github_info.get('email'):
                    emails_data.append({
                        'name': contact['name'],
                        'username': contact['username'],
                        'email': github_info['email'],
                        'source': 'GitHub',
                        'devpost_profile': contact['devpost_profile'],
                        'github_profile': github_info.get('cleaned_url', contact['original_contacts'].get('github', {}).get('url', '')),
                        'additional_info': github_info.get('bio', '')
                    })
                    email_found = True
                
                # Check website email
                website_info = contact.get('enhanced_info', {}).get('website', {})
                if website_info.get('email'):
                    emails_data.append({
                        'name': contact['name'],
                        'username': contact['username'],
                        'email': website_info['email'],
                        'source': 'Website',
                        'devpost_profile': contact['devpost_profile'],
                        'website_url': website_info.get('cleaned_url', contact['original_contacts'].get('website', {}).get('url', '')),
                        'additional_info': website_info.get('description', '')
                    })
                    email_found = True
            
            if emails_data:
                with open(filename, 'w', newline='', encoding='utf-8') as f:
                    fieldnames = ['name', 'username', 'email', 'source', 'devpost_profile', 'github_profile', 'website_url', 'additional_info']
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(emails_data)
                
                print(f"📧 Found {len(emails_data)} email addresses and saved to {filename}")
            else:
                print("❌ No email addresses found")
                
        except Exception as e:
            print(f"❌ Error exporting emails: {e}")
    
    def generate_summary_report(self):
        """Generate a summary report of the scraping results"""
        if not self.enhanced_contacts:
            print("❌ No enhanced contacts to analyze")
            return
        
        print(f"\n📊 ENHANCED CONTACT SCRAPING SUMMARY")
        print(f"=" * 50)
        
        total_participants = len(self.enhanced_contacts)
        print(f"Total participants processed: {total_participants}")
        
        # Count emails found
        github_emails = sum(1 for c in self.enhanced_contacts if c.get('enhanced_info', {}).get('github', {}).get('email'))
        website_emails = sum(1 for c in self.enhanced_contacts if c.get('enhanced_info', {}).get('website', {}).get('email'))
        total_emails = github_emails + website_emails
        
        print(f"\n📧 Email Addresses Found:")
        print(f"   From GitHub: {github_emails}")
        print(f"   From Websites: {website_emails}")
        print(f"   Total unique emails: {total_emails}")
        
        # Count additional info
        github_bios = sum(1 for c in self.enhanced_contacts if c.get('enhanced_info', {}).get('github', {}).get('bio'))
        linkedin_profiles = sum(1 for c in self.enhanced_contacts if c.get('enhanced_info', {}).get('linkedin'))
        
        print(f"\n📋 Additional Information Found:")
        print(f"   GitHub bios: {github_bios}")
        print(f"   LinkedIn profiles processed: {linkedin_profiles}")
        
        # Count URL cleaning issues
        cleaned_urls = sum(1 for c in self.enhanced_contacts 
                          for info in c.get('enhanced_info', {}).values() 
                          if isinstance(info, dict) and info.get('cleaned_url'))
        
        print(f"\n🔧 URL Processing:")
        print(f"   URLs cleaned and processed: {cleaned_urls}")
        
        # Show sample results
        print(f"\n📝 Sample Results:")
        count = 0
        for contact in self.enhanced_contacts[:5]:
            github_info = contact.get('enhanced_info', {}).get('github', {})
            website_info = contact.get('enhanced_info', {}).get('website', {})
            
            if github_info.get('email') or website_info.get('email'):
                count += 1
                print(f"   {count}. {contact['name']} (@{contact['username']})")
                
                if github_info.get('email'):
                    print(f"      GitHub Email: {github_info['email']}")
                if website_info.get('email'):
                    print(f"      Website Email: {website_info['email']}")
                if github_info.get('bio'):
                    print(f"      Bio: {github_info['bio'][:100]}...")
                if github_info.get('cleaned_url'):
                    print(f"      Cleaned GitHub URL: {github_info['cleaned_url']}")
                print()
    
    def cleanup(self):
        """Clean up resources"""
        if self.driver:
            self.driver.quit()

def main():
    """Main execution function"""
    print("🔍 Enhanced Contact Information Scraper")
    print("=" * 50)
    
    # Get input file
    json_file = input("Enter JSON file path (default: devpost_participants.json): ").strip()
    if not json_file:
        json_file = "devpost_participants.json"
    
    scraper = ContactInfoScraper(json_file)
    
    if not scraper.participants:
        print("❌ No participant data loaded. Please check the file path.")
        return
    
    try:
        # Scrape enhanced contact information
        enhanced_contacts = scraper.scrape_all_contacts()
        
        if enhanced_contacts:
            # Save results
            scraper.save_enhanced_contacts(enhanced_contacts)
            
            # Export emails
            scraper.export_emails_csv()
            
            # Generate summary report
            scraper.generate_summary_report()
            
            print(f"\n🎉 SUCCESS! Enhanced contact information extracted and saved.")
            
        else:
            print("❌ No enhanced contacts found")
            
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