import xml.etree.ElementTree as ET
import requests
import concurrent.futures

def parse_xml(file_path):
    ET.register_namespace('feeder', "https://nononsenseapps.com/feeder")
    tree = ET.parse(file_path)
    root = tree.getroot()
    namespaces = {'feeder': 'https://nononsenseapps.com/feeder'}
    return root.findall(".//outline", namespaces)

def fetch_feed_details(xml_url) -> dict | None:
    try:
        response = requests.get(xml_url, timeout=2)
        response.raise_for_status()
        feed_xml = ET.fromstring(response.content)
        
        # Try to find description or subtitle
        description = feed_xml.find(".//description")
        if description is None or description.text is None:
            description = feed_xml.find(".//subtitle")
        
        desc = ''
        url = ''

        links = feed_xml.findall("./link") + feed_xml.findall("./{http://www.w3.org/2005/Atom}link") + feed_xml.findall(".//link")
        for link in links:
            if "atom" in link.attrib.get("type", "") or "rss" in link.attrib.get("type", ""):
                continue
            # atom
            url = link.attrib.get('href')
            if not url:
                url = link.text.strip()
            break

        if not url:
            print(xml_url)
        if description is not None:
            desc = description.text.strip()
        return {"desc": desc, "url": url}
    except Exception as e:
        print(f"Error fetching description for {xml_url}: {str(e)}")

def generate_card_html(entry):
    title = entry.get('title', 'No Title').replace('+', ' ')
    xml_url = entry.get('xmlUrl', '#')
    image_url = entry.get('{https://nononsenseapps.com/feeder}imageUrl', '')

    if 'rachelbythebay' not in xml_url:
        details = fetch_feed_details(xml_url)
        if not details:
            return None
    else:
        details = {}
    description = details.get('desc', '')
    url = details.get('url', '')
    
    card_html = f"""
    <div class="card">
        <div class="flex items-center gap-4">
            <div class="avatar">
                <img src="{image_url}" alt="{title} logo">
            </div>
            <div class="grid gap-1">
                <p class="text-sm font-medium leading-none"><b><a href="{url}">{title}</a></b></p>
            </div>
        </div>
        <div class="mt-2">
            <p class="text-sm mt-2">{description}</p>
            <a href="{xml_url}" target="_blank" class="text-sm text-blue-600 hover:underline">RSS Feed</a>
        </div>
    </div>
    """
    return card_html

def generate_html_page(entries):
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        cards_html = list(executor.map(generate_card_html, entries))

    cards_html = "\n".join([c for c in cards_html if c])
    
    html_content = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>RSS Feed Entries</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                line-height: 1.6;
                color: #333;
                max-width: 1200px;
                margin: 0 auto;
                padding: 20px;
                background-color: #f0f0f0;
            }}
            .card-container {{
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
                gap: 20px;
            }}
            .card {{
                background-color: #ffffff;
                border-radius: 8px;
                padding: 16px;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
            }}
            .avatar {{
                width: 40px;
                height: 40px;
                border-radius: 10%;
                overflow: hidden;
            }}
            .avatar img {{
                width: 100%;
                height: 100%;
                object-fit: cover;
            }}
            .text-sm {{
                font-size: 0.875rem;
            }}
            .font-medium {{
                font-weight: 500;
            }}
            .text-muted-foreground {{
                color: #6b7280;
            }}
            .mt-2 {{
                margin-top: 0.5rem;
            }}
            .text-blue-600 {{
                color: #2563eb;
            }}
            .hover\:underline:hover {{
                text-decoration: underline;
            }}
        </style>
    </head>
    <body>
        <h1>RSS Feed Entries</h1>
        <div class="card-container">
            {cards_html}
        </div>
    </body>
    </html>
    """
    return html_content

def main():
    input_file = 'blog/html/feeder-export-2024-07-28T17_59_36.832.opml'
    output_file = 'rss_entries.html'
    
    entries = parse_xml(input_file)
    html_content = generate_html_page(entries)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"Generated HTML file '{output_file}' with {len(entries)} entries.")

if __name__ == "__main__":
    main()
