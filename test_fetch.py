import requests
from bs4 import BeautifulSoup

def fetch_page():
    url = "https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_anchor_positioning"
    response = requests.get(url)
    response.raise_for_status()
    
    soup = BeautifulSoup(response.text, 'html.parser')
    main_content = soup.find('main')
    
    # Print the structure of main content
    for element in main_content.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'ul', 'ol', 'dl', 'pre', 'code']):
        print(f"\nElement: {element.name}")
        print("-" * 50)
        print(element.get_text().strip())
        
        if element.name == 'code':
            print("Parent:", element.parent.name)
            print("Classes:", element.get('class', []))

if __name__ == "__main__":
    fetch_page()
