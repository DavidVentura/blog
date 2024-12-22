#!/usr/bin/env python3
import time
import shutil
import subprocess
import glob
import os
import re
import sys
import json
import xml.etree.ElementTree as ET

import pytz

from dataclasses import dataclass
from datetime import datetime, date
from functools import lru_cache
from pathlib import Path
from typing import Optional, List

from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
from jinja2 import Template
from markdown2 import Markdown
import yaml

sys.path.insert(0, "/home/david/git/blog")
import explode_drawio

BLOG_URL = 'https://blog.davidv.dev/'
BODY_TEMPLATE_FILE = 'blog/template/body.html'
BODY_TEMPLATE = Template(open(BODY_TEMPLATE_FILE, 'r').read())
INDEX_TEMPLATE = Template(open('blog/template/index.html', 'r').read())
DEBUG = False
valid_title_chars = re.compile(r'[^a-zA-Z0-9._-]')
EMBED_FILE_RE = re.compile(r'{embed-file (?P<fname>[^}]+)}')
EMBED_MERMAID_RE = re.compile(r'{embed-mermaid (?P<fname>[^}]+)}')
TOOLTIP_RE = re.compile(r'{\^(?P<hint>[^|]+)[|](?P<content>[^}]+)}')
md = Markdown(extras=["fenced-code-blocks", "cuddled-lists", "footnotes", "metadata", "tables", "header-ids"])

@dataclass
class BlogPosting:
    """
    {
      "@context": "https://schema.org",
      "@type": "NewsArticle",
      "headline": "Analyzing Google Search traffic drops",
      "datePublished": "2021-07-20T08:00:00+08:00",
      "dateModified": "2021-07-20T09:20:00+08:00"
    }
    """
    date: date
    title: str

    def as_dict(self):
        return {
          "@context": "https://schema.org",
          "@type": "BlogPosting",
          "author": "David Ventura",
          "dateCreated": self.date.isoformat(),
          "headline": self.title,
          }

@dataclass
class SeriesMetadata:
    name: str
    posts: list["PostMetadata"]

    @staticmethod
    @lru_cache
    def from_name(name: str) -> 'SeriesMetadata':
        path = Path('blog/series.yml')
        with path.open() as fd:
            data = yaml.load(fd, Loader=yaml.CLoader)
        posts = []
        for series in data:
            if series['name'].strip() != name.strip():
                continue
            for post in series['posts']:
                posts.append(PostMetadata.from_path(f"blog/raw/{post}/POST.md", False))
            break
        assert posts

        return SeriesMetadata(name, posts)

@dataclass
class PostMetadata:
    title: str
    tags: List[str]
    description: str
    date: date
    slug: Optional[str] = None
    incomplete: bool = False
    series: Optional[str] = None

    def get_title(self):
        title = self.title
        if self.incomplete:
            title = f"[DRAFT] {self.title}"
        return title

    @property
    def relative_url(self) -> str:
        # Used in template only
        return "/posts/%s" % self.get_slug()

    def get_slug(self) -> str:
        if self.slug:
            return self.slug

        if not self.slug and self.date.year >= 2024:
            raise ValueError(f"New posts must have slugs: {self.title} does not have it")

        tmp_title = self.title.replace(' ', '-').replace('"', '').replace("'", "").lower().strip('-')
        slug = valid_title_chars.sub('', tmp_title).strip('-')
        return slug

    @staticmethod
    def from_text(text: str) -> 'PostMetadata':
        return PostMetadata.from_dict(md.convert(text).metadata)

    @staticmethod
    @lru_cache
    def from_path(fname, with_series=True) -> 'PostMetadata':
        with open(fname, 'r') as fd:
            return PostMetadata.from_dict(md.convert(fd.read()).metadata, with_series)

    @staticmethod
    def from_dict(d, with_series=True) -> 'PostMetadata':
        date = datetime.strptime(d['date'], "%Y-%m-%d").date()
        tags = [t.strip() for t in d['tags'].split(',') if t]
        data = {**d, 'date': date, 'tags': tags} 
        data.pop('started', None)
        if with_series and data.get('series'):
            data['series'] = SeriesMetadata.from_name(data['series'].strip())
        return PostMetadata(**data)

    @property
    def as_schema_posting(self) -> BlogPosting:
        return BlogPosting(date=self.date, title=self.title)

    @property
    def full_url(self) -> str:
        return f'{BLOG_URL}posts/{self.get_slug()}'

def debug(*msg):
    if DEBUG:
        print(*msg, flush=True)

@lru_cache
def convert(text):
    return md.convert(text)

def populate_tooltips(text):
    return TOOLTIP_RE.sub(r'<span data-tooltip="\2">\1</span>', text)

def files_to_embed(relpath, text):
    ret = []
    for match in EMBED_FILE_RE.finditer(text):
        fname = match.group('fname')
        ret.append(os.path.join(relpath, fname))
    return ret

def embed_mermaid(relpath, text, r: PostMetadata):
    match_substr = None
    for match in EMBED_MERMAID_RE.finditer(text):
        fname = match.group('fname')
        bname = os.path.basename(fname)
        full_fname = os.path.join(relpath, fname)
        bdir = f'blog/html/images/{r.get_slug()}'
        os.makedirs(bdir, exist_ok=True)
        new_fname = f'{bdir}/{bname}.svg'
        if os.path.isfile(new_fname) and newer(new_fname, [full_fname, 'mermaid.css']):
            print('skipping', new_fname, 'nwer', full_fname)
            # do not regenerate the same files if the sources were 
            # not modified
        else:
            command = ['./node_modules/.bin/mmdc',
                       '-p', '.puppeteerrc.json',
                       '-i', full_fname,
                       '-o', new_fname,
                       '-b', 'white',
                       '--cssFile', 'mermaid.css']
            print(' '.join(command))
            subprocess.run(command)
            with open(new_fname) as fd:
                data = fd.read()
                data = inject_styles_into_svg(data, get_style_for_mermaid())
            with open(new_fname, 'wb') as fd:
                fd.write(data)

        match_substr = match.group(0)
        text = text.replace(match_substr, f'![](/images/{r.get_slug()}/{bname}.svg)')
    return text

def embed_files(relpath, text):
    match_substr = None
    for match in EMBED_FILE_RE.finditer(text):
        fname = match.group('fname')
        with open(os.path.join(relpath, fname), 'r') as fd:
            fcontent = fd.read()
        match_substr = match.group(0)
        text = text.replace(match_substr, fcontent)
    return text

def generate_header(metadata: PostMetadata):
    title = metadata.get_title()
    template = Template('<h1>{{ title }}</h1>')
    return template.render(title=title)


def generate_post(header: str, body: str, meta: PostMetadata):
    rendered = BODY_TEMPLATE.render(header=header,
            post=body,
            title=meta.get_title(),
            tags=meta.tags,
            date=meta.date,
            description=meta.description,
            full_url=meta.full_url,
            base_url=BLOG_URL,
            structured_metadata=json.dumps(meta.as_schema_posting.as_dict()),
            devmode=DEVMODE,
            series=meta.series)
    assert rendered is not None
    return rendered


def newer(f1, files):
    mtime = os.path.getmtime
    return all([mtime(f1) > mtime(x) for x in files])


def get_style_for_mermaid() -> str:
    diagram_style = """
<defs>
  <style type="text/css">
    @media (prefers-color-scheme: dark)
    {
      svg {
        background-color: transparent !important;
      }
      /* actor boxes */
      .actor {
        fill: #999 !important;
      }
      /* actor text */
      tspan {
        color: #eee !important;
      }
      /* arrow */
      .messageLine0 {
        stroke: #aaa !important;
      }
      /* arrow text */
      .messageText {
        stroke: none !important;
        fill: #aaa !important;
      }
      /* arrowhead */
      #arrowhead path {
        fill:#aaa !important;
        stroke:#aaa; !important
      }
      /* notes box*/
      .note {
        fill: #eee !important;
        stroke: #000 !important;
      }
      .noteText {
        color: #000 !important;
        font-size: 14px !important;
      }
    }
  </style>
</defs>
    """
    return diagram_style

def get_style_for_diagrams() -> str:
    diagram_style = """
<defs>
  <style type="text/css">
    @media (prefers-color-scheme: dark)
    {
      svg {
        --bg:             rgb(17, 24, 39);
        --light-arrow:    #666;
        --light-bg:       rgb(31, 41, 55);
        --dark-red-bg:    #951f2b;
        --dark-orange-bg: #8f4731;
        --dark-yellow-bg: #c47a53;
        --dark-gray-bg:   #999;
        --dark-green-bg:  #2b5c2b;
        --dark-blue-bg:   #2b3a57;

        background-color: var(--bg) !important;
      }

      /* colored rectangles */
      rect[fill="#f8cecc"] {
        fill: var(--dark-red-bg) !important;
      }
      rect[fill="#ffe6cc"] {
        fill: var(--dark-orange-bg) !important;
      }
      rect[fill="#fff2cc"] {
        fill: var(--dark-yellow-bg) !important;
      }
      rect[fill="#f5f5f5"] {
        fill: var(--dark-gray-bg) !important;
      }
      rect[fill="#d5e8d4"] {
        fill: var(--dark-green-bg) !important;
      }
      rect[fill="#dae8fc"] {
        fill: var(--dark-blue-bg) !important;
      }
      /* black arrows (ends) */
      path[fill="rgb(0, 0, 0)"] {
        fill: var(--light-arrow) !important;
      }
      path[fill="#000000"] {
        fill: var(--light-arrow) !important;
      }
      /* black arrows (lines) */
      path[stroke="rgb(0, 0, 0)"] {
        stroke: var(--light-arrow) !important;
      }
      path[stroke="#000000"] {
        stroke: var(--light-arrow) !important;
      }

      /* default white bg */
      rect[fill="#ffffff"] {
        fill: var(--light-bg); 
      }
      path[fill="rgb(255, 255, 255)"] {
        fill: var(--light-bg) !important;
      }
      rect[fill="rgb(255, 255, 255)"] {
        fill: var(--light-bg) !important;
      }
      /* text on top of arrow maybe? */
      div[style*="background-color: rgb(255, 255, 255)"] {
        background-color: var(--bg) !important;
        color: #fff !important;
      }

      /* transparent bg */
      rect:not([fill]) {
        fill: var(--light-bg) !important;
      }

      /* black text */
      div[style*="color: rgb(0, 0, 0)"] {
        color: #fff !important;
      }
    }
  </style>
</defs>
"""
    return diagram_style

def inject_styles_into_svg(svg: bytes, style: str) -> bytes:
    """
    Injects styles into SVG files so that they are nice in dark mode.
    """

    root = ET.fromstring(svg)
    new_defs = ET.fromstring(style)
    root.insert(0, new_defs)
    
    ET.register_namespace('', "http://www.w3.org/2000/svg")
    return ET.tostring(root, encoding='unicode', method='xml').encode()

def copy_post_md(dst_assets_dir: Path, post_dir: Path):
    shutil.copyfile(post_dir / "POST.md", dst_assets_dir / "POST.md")

def build_relative_assets(post_dir: Path):
    assets_dir = post_dir / "assets"
    if not assets_dir.exists():
        return
    freshest_svg_in_assets = max(f.stat().st_mtime for f in assets_dir.glob("*.svg"))
    freshest_drawio = max(f.stat().st_mtime for f in assets_dir.glob("*.drawio"))
    if freshest_svg_in_assets > freshest_drawio:
        return
    for f in assets_dir.glob("*.drawio"):
        explode_drawio.explode(f, f.parent)

def copy_relative_assets(html, assets_dir, post_dir):
    # Images
    for img in html.find_all('img'):
        src = img.attrs['src']
        if src.startswith('/') or src.startswith('http'):
            continue
        og_file = post_dir / src
        if og_file.exists():
            debug("copy", og_file, assets_dir / og_file.name)
            with og_file.open("rb") as fd:
                data = fd.read()
            if og_file.suffix == ".svg":
                data = inject_styles_into_svg(data, get_style_for_diagrams())
            with (assets_dir / og_file.name).open('wb') as fd:
                fd.write(data)
        else:
            print(f"Relative-referenced file {src} does not exist")

    # Videos
    for source in html.find_all('source'):
        src = source.attrs['src']
        if src.startswith('/') or src.startswith('http'):
            continue
        og_file = post_dir / src
        if og_file.exists():
            shutil.copyfile(og_file, assets_dir / og_file.name)
        else:
            print(f"Relative-referenced file {src} does not exist")

def main(filter_name: Optional[str]):
    this_script = __file__
    _all_time_start = time.time()
    for post_dir in Path("blog/raw/").iterdir():
        _time_start = time.time()
        if not post_dir.is_dir():
            continue
        post_file = post_dir / 'POST.md'
        if not post_file.exists():
            print("Target post file (%s) does not exist" % post_file)
            continue

        if filter_name:
            fn = filter_name.lower()
            #if fn not in post_dir.name.lower() and fn not in r.title.lower():
            if fn not in post_dir.name.lower():
                continue


        md_str = post_file.open(encoding='utf-8').read()
        r = PostMetadata.from_text(md_str)

        if r.incomplete and not DEVMODE:
            debug('Incomplete - skipping')
            continue

        md_str = embed_files(post_dir, md_str)
        md_str = embed_mermaid(post_dir, md_str, r)
        md_str = populate_tooltips(md_str)
        _files_to_embed = files_to_embed(post_dir, md_str)
        body = convert(md_str)

        header = generate_header(r)

        html_dir = Path(f'blog/html/posts/{r.get_slug()}')
        assets_dir = html_dir / 'assets'
        html_fname = html_dir / 'index.html'

        html_dir.mkdir(parents=True, exist_ok=True)
        assets_dir.mkdir(exist_ok=True)

        raw_assets_dir = post_dir / "assets"
        if raw_assets_dir.exists():
            _files_to_embed.extend(raw_assets_dir.glob("*.drawio"))

        if os.path.isfile(html_fname):
            _static = [post_file, this_script, BODY_TEMPLATE_FILE] + _files_to_embed
            if newer(html_fname, _static):
                #debug('Stale file')
                continue

        debug('generating text post')
        html_str = generate_post(header, body, r)
        html = BeautifulSoup(html_str, features='html5lib')
        for header in html.find('article').find_all(["h2", "h3", "h4"]):
            header.attrs["id"] = header.text.lower().replace(' ', '-').replace("'", "")
            anchor = html.new_tag("a", href=f'#{header.attrs["id"]}', **{"data-header":"1"})
            header.wrap(anchor)

        # TODO: this should also be considered for 'newer'??
        build_relative_assets(post_dir)
        copy_relative_assets(html, assets_dir, post_dir)
        copy_post_md(assets_dir, post_dir)


        if html.find('asciinema-player'):
            body = html.find('body')
            assert body is not None
            body.insert_after(html.new_tag('script', src="/js/asciinema-player.js"))

        blog_post = str(html)
        debug('writing to file')
        open(html_fname, 'w', encoding='utf-8').write(blog_post)
        debug('finished')
        taken = time.time() - _time_start
        debug(f'time to build {r.get_title()} was {taken}')
    taken_all = time.time() - _all_time_start
    debug(f'time to build all {taken_all}')


def generate_feed():
    fg = FeedGenerator()
    fg.id(BLOG_URL)
    fg.title('Mumbling about computers')
    fg.author({'name': 'David Ventura',
               'email': 'hello@davidv.dev'})
    fg.link(href=BLOG_URL, rel='alternate')
    fg.link(href=("%srss.xml" % BLOG_URL), rel='self')
    fg.description('Exploring software development, embedded systems, and homelab projects.')
    fg.language('en')
    fg.logo('https://blog.davidv.dev/images/logo.svg')
    return fg


def make_rss_entry(feed, item: PostMetadata):
    fe = feed.add_entry()
    url = item.full_url
    fe.id(url)
    tstamp = datetime.combine(item.date, datetime.min.time())
    tstamp = pytz.timezone("Europe/Amsterdam").localize(tstamp)
    fe.link(href=url)
    fe.author({'name': 'David Ventura',
               'email': 'hello@davidv.dev'})
    fe.pubDate(tstamp)
    fe.title(item.get_title())
    if item.description:
        fe.description(item.description)
    # everything was mutated inside feed
    return tstamp


def generate_index():
    items: List[PostMetadata] = []
    feed = generate_feed()
    last_update = None
    for f in glob.glob("blog/raw/*/POST.md"):
        item = PostMetadata.from_path(f)
        if item.incomplete and not DEVMODE:
            continue
        items.append(item)

    s_items = sorted(items, key=lambda k: k.date)
    for item in s_items:
        tstamp = make_rss_entry(feed, item)
        if last_update is None:
            last_update = tstamp
        last_update = max(last_update, tstamp)

    rendered = INDEX_TEMPLATE.render(index=reversed(s_items), base_url=BLOG_URL, full_url=BLOG_URL)
    assert rendered is not None
    open('blog/html/index.html', 'w', encoding='utf-8').write(rendered)
    feed.updated(last_update)
    feed.rss_file('blog/html/rss.xml', pretty=True)

def get_all_series() -> set[str]:
    series: set[str] = set()
    for f in glob.glob("blog/raw/*/POST.md"):
        item = PostMetadata.from_path(f)
        if item.series:
            series.add(item.series)
    return series

def get_all_tags() -> set[str]:
    tags: set[str] = set()
    for f in glob.glob("blog/raw/*/POST.md"):
        item = PostMetadata.from_path(f)
        tags = tags.union(set(item.tags))
    return tags

def generate_tag_index(tag):
    items: List[PostMetadata] = []
    for f in glob.glob("blog/raw/*/POST.md"):
        item = PostMetadata.from_path(f)
        if tag not in item.tags:
            continue
        if item.incomplete and not DEVMODE:
            continue
        items.append(item)

    s_items = sorted(items, key=lambda k: k.date, reverse=True)
    rendered = INDEX_TEMPLATE.render(index=s_items, tag=tag, base_url=BLOG_URL, full_url=f'{BLOG_URL}tags/{tag}/')
    assert rendered is not None
    fpath = Path('blog/html/tags/%s/index.html' % tag)
    fpath.parent.mkdir(parents=True, exist_ok=True)
    open(str(fpath), 'w', encoding='utf-8').write(rendered)

def generate_series_index(series):
    items: List[PostMetadata] = []
    for f in glob.glob("blog/raw/*/POST.md"):
        item = PostMetadata.from_path(f)
        if series != item.series:
            continue
        if item.incomplete and not DEVMODE:
            continue
        items.append(item)

    s_items = sorted(items, key=lambda k: k.date, reverse=True)
    rendered = INDEX_TEMPLATE.render(index=s_items, series=series, base_url=BLOG_URL, full_url=f'{BLOG_URL}series/{series}/')
    assert rendered is not None
    fpath = Path(f'blog/html/series/{series}/index.html')
    fpath.parent.mkdir(parents=True, exist_ok=True)
    open(str(fpath), 'w', encoding='utf-8').write(rendered)

def generate_sitemap(tags: set[str]):
    with Path('blog/html/sitemap.txt').open('w') as fd:
        fd.write(f'{BLOG_URL}\n')
        for t in sorted(tags):
            fd.write(f'{BLOG_URL}tags/{t}/\n')

if __name__ == '__main__':
    DEVMODE = False
    if len(sys.argv) > 1 and sys.argv[1].lower() == 'dev':
        DEVMODE = True
    #series = get_all_series()
    #for series_name in series:
    #    generate_series_index(series_name)
    filter_name = sys.argv[2] if len(sys.argv) > 2 else None
    main(filter_name)
    # This is a hack for devmode, probably should be cached?
    if not filter_name:
        tags = get_all_tags()
        for tag in tags:
            generate_tag_index(tag)
        generate_sitemap(tags)
        generate_index()
