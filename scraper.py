import os
import sys
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from slugify import slugify
import json
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed

class DocScraper:
    def __init__(self, base_url, test_mode=False):
        self.base_url = base_url
        parsed_base = urlparse(base_url)
        self.domain = parsed_base.netloc
        self.base_path = parsed_base.path.rstrip('/')
        self.visited_urls = set()
        self.output_dir = "output"
        self.scraped_docs_dir = os.path.join(self.output_dir, "docs")
        self.compiled_dir = os.path.join(self.output_dir, "compiled")
        self.test_mode = test_mode
        self.test_limit = 50
        
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
        if not os.path.exists(self.scraped_docs_dir):
            os.makedirs(self.scraped_docs_dir)
        if not os.path.exists(self.compiled_dir):
            os.makedirs(self.compiled_dir)
        
        self.doc_structure = {
            "title": "",
            "url": base_url,
            "children": []
        }
        
        self.session = requests.Session()
        retries = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504]
        )
        self.session.mount('https://', HTTPAdapter(max_retries=retries, pool_maxsize=10))
        self.session.mount('http://', HTTPAdapter(max_retries=retries, pool_maxsize=10))
        self.last_request_time = 0
        self.min_request_interval = 0.5

    def fetch_page(self, url):
        try:
            current_time = time.time()
            time_since_last_request = current_time - self.last_request_time
            if time_since_last_request < self.min_request_interval:
                time.sleep(self.min_request_interval - time_since_last_request)
            
            response = self.session.get(url, timeout=10)
            self.last_request_time = time.time()
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            print(f"Error fetching {url}: {e}")
            return None

    def should_follow_link(self, url):
        parsed = urlparse(url)
        return (
            parsed.netloc == self.domain and
            '/en-US/' in parsed.path and
            parsed.path.startswith(self.base_path) and
            not url.endswith(('.pdf', '.zip', '.png', '.jpg', '.jpeg', '.gif')) and
            '#' not in url
        )

    def convert_element_to_markdown(self, element):
        if element.name in ['code', 'pre']:
            # Skip code elements that will be handled by their parent pre element
            if element.name == 'code' and element.parent and element.parent.name == 'pre':
                return ""
            # Don't process code elements that are inside links
            if element.parent and element.parent.name == 'a':
                return ""
            code_text = element.get_text().strip()
            if element.name == 'pre':
                return f"\n```\n{code_text}\n```\n" if code_text else ""
            return f"`{code_text}`" if code_text else ""
            
        if element.name == 'a':
            href = element.get('href', '')
            if not href:
                return element.get_text().strip()
            
            # Convert absolute URLs to relative ones if they're under our base path
            if href.startswith('/'):
                href = f"https://{self.domain}{href}"
            
            # Only convert URLs that are part of our documentation
            if href.startswith(f"https://{self.domain}{self.base_path}"):
                # Get the relative path from the base path
                relative_path = href[len(f"https://{self.domain}{self.base_path}"):].lstrip('/')
                
                # Handle fragment identifiers
                fragment = ""
                if '#' in relative_path:
                    relative_path, fragment = relative_path.split('#', 1)
                
                # Skip certain sections that should remain as external links
                if any(section in relative_path.lower() for section in ['/api/', '/html/', '/javascript/', '/learn/']):
                    pass
                # Convert documentation links to internal references
                elif relative_path:
                    # Handle both the path and any fragments
                    parts = [p for p in relative_path.split('/') if p]
                    if parts:
                        # Use the last meaningful part of the path for the slug
                        slug = slugify(parts[-1])
                        if fragment:
                            href = f"#{slug}-{fragment}"
                        else:
                            href = f"#{slug}"
            
            text = element.get_text().strip()
            code_element = element.find('code')
            if code_element:
                text = f"`{code_element.get_text().strip()}`"
            return f"[{text}]({href})"

        if element.name == 'li':
            result = []
            for child in element:
                if isinstance(child, str):
                    text = child.strip()
                    if text:
                        result.append(text)
                else:
                    child_text = self.convert_element_to_markdown(child)
                    if child_text:
                        result.append(child_text)
            return ' '.join(result)
            
        if element.name in ['p', 'span', 'div', 'dd', 'dt']:  
            result = []
            for child in element:
                if isinstance(child, str):
                    text = child.strip()
                    if text:
                        result.append(text)
                else:
                    child_text = self.convert_element_to_markdown(child)
                    if child_text:
                        result.append(child_text)
            return ' '.join(result)
            
        result = []
        for child in element:
            if isinstance(child, str):
                text = child.strip()
                if text:
                    result.append(text)
            else:
                child_text = self.convert_element_to_markdown(child)
                if child_text:
                    result.append(child_text)
        return ' '.join(result) if result else element.get_text().strip()

    def extract_content(self, soup, url):
        # Try different selectors for main content
        main_content = None
        for selector in ['main', 'article', 'div[role="main"]', '#content']:
            main_content = soup.select_one(selector)
            if main_content:
                break
                
        if not main_content:
            print(f"Warning: Could not find main content in {url}")
            return None
            
        title = soup.find('h1')
        title_text = title.get_text().strip() if title else os.path.basename(url)

        content = []
        content.append(f"# {title_text}\n")
        content.append(f"Source: {url}\n")
        
        # Remove interactive elements, feedback sections, and navigation
        for element in main_content.find_all(['iframe', 'div', 'section', 'nav', 'aside'], 
            class_=['interactive', 'interactive-example', 'metadata', 'document-meta', 'article-footer', 'bc-data', 'page-footer', 'document-toc', 'sidebar']):
            element.decompose()

        # Remove script and style tags
        for element in main_content.find_all(['script', 'style']):
            element.decompose()

        if title and title in main_content:
            title.decompose()

        # Extract introduction text
        intro = None
        intro_p = main_content.find('p')
        if intro_p:
            intro = self.convert_element_to_markdown(intro_p)
            if intro:
                content.append(intro + "\n")

        current_section = {'heading': None, 'content': []}
        sections = []

        # First pass: collect all headings to build the structure
        headings = main_content.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6'])
        for heading in headings:
            if current_section['heading'] or current_section['content']:
                sections.append(current_section.copy())
            current_section = {'heading': heading, 'content': []}
            
            # Collect content until next heading
            current = heading.next_sibling
            while current and not (current.name and current.name.startswith('h')):
                if isinstance(current, str):
                    text = current.strip()
                    if text:
                        current_section['content'].append(text)
                elif current.name:
                    # Skip elements that should be ignored
                    if current.get('class') and any(cls in current.get('class') for cls in ['hidden', 'offscreen', 'visuallyhidden']):
                        current = current.next_sibling
                        continue

                    # Handle definition lists
                    if current.name == 'dl':
                        dl_content = []
                        for dt in current.find_all('dt', recursive=False):
                            dd = dt.find_next_sibling('dd')
                            if dd:
                                term = self.convert_element_to_markdown(dt)
                                definition = self.convert_element_to_markdown(dd)
                                if term and definition:
                                    dl_content.append(f"- **{term}**")
                                    dl_content.append(f"  {definition}")
                        if dl_content:
                            current_section['content'].extend(dl_content)
                            current_section['content'].append("")
                    
                    # Handle lists
                    elif current.name in ['ul', 'ol']:
                        list_items = []
                        for li in current.find_all('li', recursive=False):
                            item_text = self.convert_element_to_markdown(li)
                            if item_text:
                                list_items.append(f"- {item_text}")
                        if list_items:
                            current_section['content'].extend(list_items)
                            current_section['content'].append("")
                    
                    # Handle code blocks
                    elif current.name == 'pre':
                        code_text = current.get_text().strip()
                        if code_text:
                            current_section['content'].append(f"\n```\n{code_text}\n```\n")
                    
                    # Handle regular content
                    else:
                        text = self.convert_element_to_markdown(current)
                        if text:
                            current_section['content'].append(text)
                            current_section['content'].append("")
                
                current = current.next_sibling

        # Add the last section
        if current_section['heading'] or current_section['content']:
            sections.append(current_section)

        # If no sections were found, try to get content directly
        if not sections:
            text = self.convert_element_to_markdown(main_content)
            if text:
                sections.append({'heading': None, 'content': [text]})

        # Add all sections to content
        for section in sections:
            if section['heading']:
                level = int(section['heading'].name[1])
                heading_text = section['heading'].get_text().strip()
                content.append(f"\n{'#' * level} {heading_text}\n")
            content.extend(section['content'])

        # Remove any consecutive blank lines
        content = [line for i, line in enumerate(content) if i == 0 or not (line == "" and content[i-1] == "")]
        
        return {
            'title': title_text,
            'content': content
        }

    def scrape_page(self, url, depth=0):
        if url in self.visited_urls or depth > 3:
            return None

        if self.test_mode and len(self.visited_urls) >= self.test_limit:
            return None

        self.visited_urls.add(url)
        print(f"Scraping: {url}")

        html = self.fetch_page(url)
        if not html:
            return None

        soup = BeautifulSoup(html, 'html.parser')
        content_data = self.extract_content(soup, url)
        
        if not content_data:
            return None

        filename = f"{slugify(content_data['title'])}.md"
        filepath = os.path.join(self.scraped_docs_dir, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(content_data['content']))

        page_structure = {
            "title": content_data['title'],
            "url": url,
            "filename": filename,
            "children": []
        }

        links_to_scrape = []
        for link in soup.find_all('a', href=True):
            next_url = urljoin(url, link['href'])
            if self.should_follow_link(next_url):
                links_to_scrape.append(next_url)

        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_url = {executor.submit(self.scrape_page, next_url, depth + 1): next_url for next_url in links_to_scrape}
            for future in as_completed(future_to_url):
                child_structure = future.result()
                if child_structure:
                    page_structure['children'].append(child_structure)

        return page_structure

    def start_scraping(self):
        structure = self.scrape_page(self.base_url)
        if structure:
            self.doc_structure.update(structure)
            
        with open(os.path.join(self.compiled_dir, 'structure.json'), 'w') as f:
            json.dump(self.doc_structure, f, indent=2)

    def compile_markdown_files(self):
        print("Compiling markdown files into a single document...")
        
        structure_file = os.path.join(self.compiled_dir, 'structure.json')
        if not os.path.exists(structure_file):
            print("Error: structure.json not found")
            return
            
        with open(structure_file, 'r') as f:
            structure = json.load(f)
            
        def generate_toc(node, level=0):
            toc = []
            indent = "  " * level
            section_id = os.path.splitext(node.get('filename', ''))[0]
            if section_id:
                toc.append(f"{indent}- [{node['title']}](#{section_id})")
                
            for child in node.get('children', []):
                toc.extend(generate_toc(child, level + 1))
            return toc
            
        def process_content(content, filename):
            section_id = os.path.splitext(filename)[0]
            content = f'<div id="{section_id}">\n\n{content}\n\n</div>'
            return content
            
        toc = ["# Table of Contents\n"]
        toc.extend(generate_toc(structure))
        
        compiled_content = []
        compiled_content.extend(toc)
        compiled_content.append("\n---\n")
        
        def add_content_recursive(node):
            if 'filename' in node and node['filename']:
                filepath = os.path.join(self.scraped_docs_dir, node['filename'])
                if os.path.exists(filepath):
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                        compiled_content.append(process_content(content, node['filename']))
                        compiled_content.append("\n---\n")
                        
            for child in node.get('children', []):
                add_content_recursive(child)
                
        add_content_recursive(structure)
        
        output_file = os.path.join(self.compiled_dir, 'compiled-documentation.md')
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("\n".join(compiled_content))
            
        print(f"Compiled documentation has been saved to '{output_file}'")

def main():
    parser = argparse.ArgumentParser(description='Scrape documentation from a website.')
    parser.add_argument('url', help='The URL to start scraping from')
    parser.add_argument('--test', action='store_true', help='Run in test mode (only scrape a few documents)')
    args = parser.parse_args()

    scraper = DocScraper(args.url, test_mode=args.test)
    scraper.start_scraping()
    scraper.compile_markdown_files()
    print(f"\nDone! Documentation has been saved to the '{scraper.output_dir}' directory.")

if __name__ == "__main__":
    main()
