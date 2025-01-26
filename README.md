# Documentation Scraper

A Python-based web scraper that recursively crawls documentation websites and compiles them into organized markdown documents. Currently optimized for MDN Web Docs, with support for proper handling of inline code, special characters, and hierarchical document structure.

## Features

- Recursive documentation crawling
- Clean markdown output with proper formatting
- Support for inline code blocks and special characters
- Hierarchical document structure preservation
- Navigation-friendly compiled documentation
- Test mode for limited scraping during development
- Duplicate code block detection and removal
- Source URL preservation

## Installation

### Prerequisites
- Python 3.8 or higher
- pip (Python package installer)

### Setting up a Virtual Environment
It's recommended to use a virtual environment to avoid conflicts with other Python projects:

1. Create a virtual environment:
```bash
python -m venv venv
```

2. Activate the virtual environment:
```bash
# On macOS/Linux:
source venv/bin/activate

# On Windows:
venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

To deactivate the virtual environment when you're done:
```bash
deactivate
```

## Usage

### Full Scraping
```bash
python scraper.py <url>
```

Example:
```bash
python scraper.py https://developer.mozilla.org/en-US/docs/Web/CSS
```

### Test Mode
For development or testing, use the `--test` flag to limit the number of documents scraped:
```bash
python scraper.py --test <url>
```

## Output

The scraper organizes its output in the following directory structure:

```
output/
├── docs/              # Individual markdown files for each documentation page
└── compiled/
    ├── structure.json # Documentation hierarchy
    └── compiled-documentation.md  # Single navigable document
```

### Individual Files (in docs/)
- Clean markdown formatting
- Preserved source URLs
- Well-organized sections
- Proper handling of inline code and links

### Compiled Documentation
- Table of contents with proper hierarchy
- HTML anchors for navigation
- Consistent formatting throughout
- Comprehensive coverage of all scraped content

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
