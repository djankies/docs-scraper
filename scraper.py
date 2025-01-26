#!/usr/bin/env python3

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

class DocScraper:
    def __init__(self, base_url, test_mode=False):
        self.base_url = base_url
        parsed_base = urlparse(base_url)
        self.domain = parsed_base.netloc
        self.base_path = parsed_base.path.rstrip('/')  # Store the base path
        self.visited_urls = set()
        self.output_dir = "output"
        self.test_mode = test_mode
        self.test_limit = 5  # Only scrape 5 documents in test mode
        
        # Create output directory if it doesn't exist
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)
        
        # Store the structure of documents
        self.doc_structure = {
            "title": "",
            "url": base_url,
            "children": []
        }
        
        # Configure session with retries and rate limiting
        self.session = requests.Session()
        retries = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504]
        )
        self.session.mount('https://', HTTPAdapter(max_retries=retries, pool_maxsize=10))
        self.session.mount('http://', HTTPAdapter(max_retries=retries, pool_maxsize=10))
        self.last_request_time = 0
        self.min_request_interval = 0.5  # Minimum time between requests in seconds

    def fetch_page(self, url):
        try:
            # Rate limiting
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
        # Check if the URL path starts with the base path to ensure it's a child
        return (
            parsed.netloc == self.domain and
            '/en-US/' in parsed.path and  # Only follow English documentation
            parsed.path.startswith(self.base_path) and  # Only follow children of base path
            not url.endswith(('.pdf', '.zip', '.png', '.jpg', '.jpeg', '.gif')) and
            '#' not in url
        )

    def convert_element_to_markdown(self, element):
        """Convert an HTML element to markdown, preserving links and inline code."""
        # Handle code blocks
        if element.name in ['code', 'pre']:
            code_text = element.get_text().strip()
            return f"`{code_text}`" if code_text else ""
            
        # Handle links
        if element.name == 'a':
            href = element.get('href', '')
            if not href:
                return element.get_text().strip()
            
            # Make the link relative if it's internal
            if href.startswith('/'):
                href = f"https://{self.domain}{href}"
            
            # Handle code inside links
            text = element.get_text().strip()
            if element.find('code'):
                text = f"`{text}`"
            
            return f"[{text}]({href})"

        # For list items, process their children to preserve links and code
        if element.name == 'li':
            result = []
            for child in element:
                if isinstance(child, str):
                    text = child.strip()
                    if text:
                        result.append(text)
                else:
                    result.append(self.convert_element_to_markdown(child))
            return ' '.join(filter(None, result))
            
        # Handle paragraphs and other elements with mixed content
        if element.name in ['p', 'span', 'div']:
            result = []
            for child in element:
                if isinstance(child, str):
                    text = child.strip()
                    if text:
                        result.append(text)
                else:
                    result.append(self.convert_element_to_markdown(child))
            return ' '.join(filter(None, result))
            
        # Handle regular text with mixed inline elements
        result = []
        for child in element:
            if isinstance(child, str):
                text = child.strip()
                if text:
                    result.append(text)
            else:
                result.append(self.convert_element_to_markdown(child))
        return ' '.join(filter(None, result)) if result else element.get_text().strip()

    def extract_content(self, soup, url):
        """Extract content from the page and convert to markdown."""
        main_content = soup.find('main')
        if not main_content:
            return None

        # Extract title
        title = soup.find('h1')
        title_text = title.get_text().strip() if title else os.path.basename(url)

        # Convert content to markdown
        content = []
        content.append(f"# {title_text}\n")
        content.append(f"Source: {url}\n")

        # Find and remove interactive examples
        for interactive in main_content.find_all(['iframe', 'div'], class_=['interactive', 'interactive-example']):
            interactive.decompose()

        # Remove the main h1 title since we already added it
        if title and title in main_content:
            title.decompose()

        # Track seen code blocks to avoid duplicates
        seen_code_blocks = set()
        
        # Process content and track sections
        current_section = {'heading': None, 'content': []}
        sections = []

        for element in main_content.find_all(['h2', 'h3', 'h4', 'h5', 'h6', 'p', 'ul', 'ol']):
            # Handle headings
            if element.name.startswith('h'):
                if current_section['heading'] and current_section['content']:
                    sections.append(current_section.copy())
                current_section = {'heading': element, 'content': []}
                continue

            # Handle lists
            if element.name in ['ul', 'ol']:
                list_items = []
                for li in element.find_all('li', recursive=False):
                    # Check if the list item contains a link with code
                    code_link = li.find('a', recursive=False)
                    if code_link and code_link.find('code'):
                        # If it's a link with code, just use the link
                        item_text = self.convert_element_to_markdown(code_link)
                        code_text = code_link.find('code').get_text().strip()
                        seen_code_blocks.add(code_text)
                    else:
                        # Otherwise process normally
                        item_text = self.convert_element_to_markdown(li)
                    
                    if item_text:
                        list_items.append(f"- {item_text}")
                
                if list_items:
                    current_section['content'].extend(list_items)
                continue

            # Handle regular elements
            text = self.convert_element_to_markdown(element)
            
            # Check for standalone code blocks
            code_elements = element.find_all(['code', 'pre'])
            for code in code_elements:
                code_text = code.get_text().strip()
                if code_text in seen_code_blocks:
                    # If we've seen this code block before, remove it from the text
                    text = text.replace(f"`{code_text}`", "").strip()
                else:
                    seen_code_blocks.add(code_text)
            
            if text:
                current_section['content'].append(text)

        # Add the last section
        if current_section['heading'] and current_section['content']:
            sections.append(current_section)

        # Convert sections to markdown
        for section in sections:
            level = int(section['heading'].name[1])
            heading_text = section['heading'].get_text().strip()
            if heading_text:
                content.append(f"\n{'#' * level} {heading_text}")
                content.extend(item.strip() for item in section['content'] if item.strip())

        return {
            "title": title_text,
            "content": "\n\n".join(content)
        }

    def scrape_page(self, url, depth=0):
        if url in self.visited_urls or depth > 3:  # Limit depth to prevent infinite recursion
            return None

        # In test mode, limit the number of documents
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

        # Save the content
        filename = f"{slugify(content_data['title'])}.md"
        filepath = os.path.join(self.output_dir, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content_data['content'])

        # Find and process links
        page_structure = {
            "title": content_data['title'],
            "url": url,
            "filename": filename,
            "children": []
        }

        for link in soup.find_all('a', href=True):
            next_url = urljoin(url, link['href'])
            if self.should_follow_link(next_url):
                child_structure = self.scrape_page(next_url, depth + 1)
                if child_structure:
                    page_structure['children'].append(child_structure)

        return page_structure

    def start_scraping(self):
        structure = self.scrape_page(self.base_url)
        if structure:
            self.doc_structure.update(structure)
            
        # Save the document structure
        with open(os.path.join(self.output_dir, 'structure.json'), 'w') as f:
            json.dump(self.doc_structure, f, indent=2)

    def compile_markdown_files(self):
        """Compile all markdown files in the output directory into a single navigable file."""
        print("Compiling markdown files into a single document...")
        
        # First, load the structure to maintain the hierarchy
        structure_file = os.path.join(self.output_dir, 'structure.json')
        if not os.path.exists(structure_file):
            print("Error: structure.json not found")
            return
            
        with open(structure_file, 'r') as f:
            structure = json.load(f)
            
        def generate_toc(node, level=0):
            """Generate table of contents recursively"""
            toc = []
            indent = "  " * level
            # Create a link to the section using the filename without extension
            section_id = os.path.splitext(node.get('filename', ''))[0]
            if section_id:
                toc.append(f"{indent}- [{node['title']}](#{section_id})")
                
            for child in node.get('children', []):
                toc.extend(generate_toc(child, level + 1))
            return toc
            
        def process_content(content, filename):
            """Process content to adjust internal links and add section ID"""
            section_id = os.path.splitext(filename)[0]
            # Add section ID for navigation
            content = f'<div id="{section_id}">\n\n{content}\n\n</div>'
            return content
            
        # Generate table of contents
        toc = ["# Table of Contents\n"]
        toc.extend(generate_toc(structure))
        
        # Compile all content
        compiled_content = []
        compiled_content.extend(toc)
        compiled_content.append("\n---\n")  # Separator between TOC and content
        
        def add_content_recursive(node):
            """Add content recursively following the structure"""
            if 'filename' in node and node['filename']:
                filepath = os.path.join(self.output_dir, node['filename'])
                if os.path.exists(filepath):
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                        compiled_content.append(process_content(content, node['filename']))
                        compiled_content.append("\n---\n")  # Separator between sections
                        
            for child in node.get('children', []):
                add_content_recursive(child)
                
        add_content_recursive(structure)
        
        # Save the compiled content
        output_file = os.path.join(self.output_dir, 'compiled-documentation.md')
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
