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

```bash
pip install -r requirements.txt
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

The scraper generates the following in the `output` directory:

1. Individual markdown files for each documentation page
2. `structure.json` containing the documentation hierarchy
3. `compiled-documentation.md` combining all pages into a single, navigable document

## Output Format

### Individual Files
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
