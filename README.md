# 🕷️ Devpost & GitHub Contact Scrapers

This repository contains Python scripts for scraping participants and contact information from Devpost hackathons and GitHub repositories. These tools can help identify developers, collect useful outreach information, or analyze engagement data for hackathons and developer communities.

---

## 📁 Scripts Included

### 1. `devpost_participants_scraper.py`

Scrapes usernames and profile URLs from Devpost hackathon participant pages.

**Features:**
- Input any Devpost hackathon URL
- Extracts all usernames and their Devpost profile links
- Uses `requests`, `BeautifulSoup`, and optionally Selenium for dynamic content

---

### 2. `github_script.py`

Collects data from GitHub repositories using the GitHub GraphQL API.

**Features:**
- Retrieves stargazers, contributor metadata, and emails (if available)
- Includes pagination support
- Requires a GitHub personal access token

---

### 3. `contact_scraper.py`

Extracts contact details (GitHub, LinkedIn, personal websites, emails) from Devpost user profile pages.

**Features:**
- Parses HTML of Devpost profiles
- Aggregates external contact links
- Outputs structured contact information for outreach or analysis

---

## 🚀 Getting Started

### 🔧 Installation

1. Clone the repository:

```bash
git clone https://github.com/amoghastagi/emailscrapers.git
cd emailscrapers
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

> If you're using Selenium, make sure you have `chromedriver` installed and accessible via PATH.

---

## 🧪 Usage

### Devpost Participant Scraper

```bash
python devpost_participants_scraper.py
```

Enter the Devpost URL when prompted, or customize the script to accept command-line arguments.

---

### GitHub GraphQL Script

```bash
python github_script.py
```

Make sure to set your GitHub token in the script or via environment variable.

---

### Contact Scraper

```bash
python contact_scraper.py
```

Provide a list of Devpost profile URLs (from the first script) to extract contact links.

---

## ⚠️ Ethics & Fair Use

- Do not abuse these tools — scrape respectfully and within rate limits.
- These scripts are for **educational and networking purposes** only.
- Comply with the Terms of Service of Devpost and GitHub.

---

## 📄 License

This project is licensed under the MIT License.  
See the [LICENSE](LICENSE) file for more information.

---

## 🤝 Contributing

Pull requests and feedback are welcome!  
If you have ideas for improvement or encounter bugs, feel free to open an issue.

---

**Developed by [Amogh Astagi](https://github.com/amoghastagi)**