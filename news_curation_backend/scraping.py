from bs4 import BeautifulSoup
import requests
from datetime import datetime
from typing import List, Dict, Optional

# Placeholder for list of news sources to scrape
# In a real application, this would be more dynamic or configurable
NEWS_SOURCES = {
    "example_news": {
        "url": "https://example.com/news", # Replace with actual news site URL
        "selectors": {
            "article": "div.article-summary", # CSS selector for an article container
            "title": "h2.article-title",
            "url": "a.article-link",
            "source": "span.article-source",
            "published_at": "span.article-date",
            "category": "span.article-category"
        }
    },
    # Add more sources here
}

def scrape_news_from_source(source_name: str, source_config: Dict) -> List[Dict]:
    """Scrapes news articles from a single configured source."""
    articles_data = []
    try:
        response = requests.get(source_config["url"], timeout=10)
        response.raise_for_status() # Raise an exception for bad status codes
        soup = BeautifulSoup(response.content, "html.parser")

        article_containers = soup.select(source_config["selectors"]["article"])
        for container in article_containers:
            title_tag = container.select_one(source_config["selectors"]["title"])
            url_tag = container.select_one(source_config["selectors"]["url"])
            source_tag = container.select_one(source_config["selectors"]["source"])
            published_at_tag = container.select_one(source_config["selectors"]["published_at"])
            category_tag = container.select_one(source_config["selectors"]["category"])

            title = title_tag.get_text(strip=True) if title_tag else "N/A"
            url = url_tag["href"] if url_tag and "href" in url_tag.attrs else None
            source = source_tag.get_text(strip=True) if source_tag else source_name
            published_at_str = published_at_tag.get_text(strip=True) if published_at_tag else None
            category = category_tag.get_text(strip=True) if category_tag else "General"

            # Basic date parsing - will need improvement for various formats
            published_at = None
            if published_at_str:
                try:
                    # Example parsing, adjust based on actual date formats
                    published_at = datetime.strptime(published_at_str, "%Y-%m-%dT%H:%M:%SZ") # ISO format
                except ValueError:
                    try:
                        published_at = datetime.strptime(published_at_str, "%Y-%m-%d %H:%M:%S")
                    except ValueError:
                        published_at = datetime.strptime(published_at_str, "%b %d, %Y") # e.g., "Mar 22, 2026"
            
            if url: # Only add if a URL is found
                articles_data.append({
                    "title": title,
                    "url": url,
                    "source": source,
                    "published_at": published_at,
                    "category": category,
                    "scraped_at": datetime.utcnow()
                })
    except requests.exceptions.RequestException as e:
        print(f"Error scraping {source_name}: {e}")
    except Exception as e:
        print(f"An unexpected error occurred during scraping {source_name}: {e}")
        
    return articles_data

def scrape_all_news() -> List[Dict]:
    """Scrapes news from all configured sources."""
    all_scraped_data = []
    for source_name, config in NEWS_SOURCES.items():
        print(f"Scraping from {source_name}...")
        data = scrape_news_from_source(source_name, config)
        all_scraped_data.extend(data)
    return all_scraped_data

if __name__ == "__main__":
    # This is for testing the scraping module independently
    print("Testing scraping module...")
    # IMPORTANT: Replace example_news with a real, accessible news source for testing
    # or mock the requests.get call. For now, it will likely fail or return empty.
    # Example of adding a test source (this URL might not work or have correct selectors):
    # NEWS_SOURCES["test_site"] = {
    #     "url": "https://news.google.com/home?hl=en-US&gl=US&ceid=US:en", # Example, might need complex handling
    #     "selectors": {
    #         "article": "article",
    #         "title": "a[aria-label]",
    #         "url": "a[aria-label]",
    #         "source": "span[aria-label]",
    #         "published_at": "time",
    #         "category": "div.section-name" # Placeholder category selector
    #     }
    # }
    
    # To make this runnable without external websites, one would typically mock requests.get
    # For now, we'll just call scrape_all_news which will print errors if sources are bad.
    scraped_articles = scrape_all_news()
    print(f"Scraped {len(scraped_articles)} articles.")
    for i, article in enumerate(scraped_articles[:5]): # Print first 5
        print(f"{i+1}. {article['title']} - {article['url']} (Source: {article['source']}, Category: {article['category']})")

