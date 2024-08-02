from dataclasses import dataclass
import html
import xml.etree.ElementTree as ET
import requests
import concurrent.futures
from jinja2 import Template

WEBRING_TEMPLATE_FILE = 'blog/template/webring.html'
WEBRING_TEMPLATE = Template(open(WEBRING_TEMPLATE_FILE, 'r').read())

@dataclass
class BlogMeta:
    image_url: str
    title: str
    url: str
    description: str
    xml_url: str

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
        
        descriptions = feed_xml.findall("./description") + feed_xml.findall("./channel/description")
        description = None
        for d in descriptions:
            if d.text:
                description = d.text
                break
        if description is None:
            sub = feed_xml.find(".//subtitle")
            if sub:
                description = sub.text.strip()
        
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
            desc = description.strip()
        return {"desc": desc, "url": url}
    except Exception as e:
        print(f"Error fetching description for {xml_url}: {str(e)}")

def parse_blog_meta(entry) -> BlogMeta | None:
    title = entry.get('title', 'No Title').replace('+', ' ')
    title = html.escape(title)
    xml_url = entry.get('xmlUrl', '#')
    image_url = entry.get('{https://nononsenseapps.com/feeder}imageUrl', '')

    if 'rachelbythebay' in xml_url:
        # rachel gets really angry if we scrape her feed more than once a day :(
        # and i'm not implementing caching
        return None
    if 'davidv.dev' in xml_url:
        return None

    details = fetch_feed_details(xml_url)
    if not details:
        return None
    description = details.get('desc', '')
    if len(description) > 100:
        description = description[:100] + "..."
    description = html.escape(description)
    url = details.get('url', '')

    return BlogMeta(image_url=image_url, title=title, url=url, description=description, xml_url=xml_url)

def generate_html_page(entries):
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        blogs = list(executor.map(parse_blog_meta, entries))

    blogs = [c for c in blogs if c]
    blogs = sorted(blogs, key=lambda b: b.title.strip().lower())

    html_content = WEBRING_TEMPLATE.render(blogs=blogs)
    return html_content

def main():
    input_file = 'blog/html/feeder-export-2024-07-28T17_59_36.832.opml'
    output_file = 'blog/html/blogs-i-follow.html'
    
    entries = parse_xml(input_file)
    html_content = generate_html_page(entries)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"Generated HTML file '{output_file}' with {len(entries)} entries.")

if __name__ == "__main__":
    main()
