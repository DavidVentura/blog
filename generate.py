#!/usr/bin/env python3
import subprocess
import glob
import os
import re
import sys
import json

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

BLOG_URL = 'https://blog.davidv.dev/'
BODY_TEMPLATE_FILE = 'blog/template/body.html'
BODY_TEMPLATE = Template(open(BODY_TEMPLATE_FILE, 'r').read())
INDEX_TEMPLATE = Template(open('blog/template/index.html', 'r').read())
DEBUG = True
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
class PostMetadata:
    title: str
    tags: List[str]
    description: str
    date: date
    slug: Optional[str] = None
    incomplete: bool = False

    def get_title(self):
        title = self.title
        if self.incomplete:
            title = f"[DRAFT] {self.title}"
        return title

    @property
    def path(self) -> str:
        return "/%s.html" % self.get_slug()

    def get_slug(self) -> str:
        if self.slug:
            return self.slug

        if not self.slug and self.date.year >= 2024:
            raise ValueError(f"New posts must have slugs: {self.title} does not have it")

        tmp_title = self.title.replace(' ', '-').replace('"', '').lower().strip('-')
        slug = valid_title_chars.sub('', tmp_title).strip('-')
        return slug

    @staticmethod
    def from_text(text: str) -> 'PostMetadata':
        return PostMetadata.from_dict(md.convert(text).metadata)

    @staticmethod
    @lru_cache
    def from_path(fname) -> 'PostMetadata':
        with open(fname, 'r') as fd:
            return PostMetadata.from_dict(md.convert(fd.read()).metadata)

    @staticmethod
    def from_dict(d) -> 'PostMetadata':
        date = datetime.strptime(d['date'], "%Y-%m-%d").date()
        tags = [t.strip() for t in d['tags'].split(',') if t]
        data = {**d, 'date': date, 'tags': tags} 
        return PostMetadata(**data)

    @property
    def as_schema_posting(self) -> BlogPosting:
        return BlogPosting(date=self.date, title=self.title)

    @property
    def full_url(self) -> str:
        return f'{BLOG_URL}{self.get_slug()}.html'

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
        full_fname = os.path.join(relpath, fname)
        bdir = f'blog/html/images/mermaid/{r.get_slug()}'
        os.makedirs(bdir, exist_ok=True)
        new_fname = f'{bdir}/{fname}.svg'
        if os.path.isfile(new_fname) and newer(new_fname, [full_fname]):
            print('skipping', new_fname, 'nwer', full_fname)
            # do not regenerate the same files if the sources were 
            # not modified
            continue
        print('out=', new_fname)
        subprocess.run(['./node_modules/.bin/mmdc', '-i', full_fname, '-o', new_fname, '-b', 'white'])
        match_substr = match.group(0)
        text = text.replace(match_substr, f'![](/images/mermaid/{r.get_slug()}/{fname}.svg)')
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
            devmode=DEVMODE)
    assert rendered is not None
    return rendered


def newer(f1, files):
    mtime = os.path.getmtime
    return all([mtime(f1) > mtime(x) for x in files])


def main(filter_name: Optional[str]):
    this_script = __file__
    for target in glob.glob("blog/raw/*"):
        post_file = os.path.join(target, 'POST.md')
        if not os.path.exists(post_file):
            print("Target post file (%s) does not exist" % post_file)
            continue
        if filter_name and filter_name.lower() not in post_file.lower():
            continue

        debug(target)

        md_str = open(post_file, encoding='utf-8').read()
        r = PostMetadata.from_text(md_str)

        if r.incomplete and not DEVMODE:
            debug('Incomplete - skipping')
            continue

        md_str = embed_files(target, md_str)
        md_str = embed_mermaid(target, md_str, r)
        md_str = populate_tooltips(md_str)
        _files_to_embed = files_to_embed(target, md_str)
        body = convert(md_str)

        header = generate_header(r)
        html_fname = 'blog/html/%s.html' % r.get_slug()

        if os.path.isfile(html_fname):
            if newer(html_fname, [post_file, this_script, BODY_TEMPLATE_FILE] + _files_to_embed):
                debug('Stale file')
                continue

        debug('generating text post')
        html_str = generate_post(header, body, r)
        html = BeautifulSoup(html_str, features='html5lib')
        for header in html.find('article').find_all(["h2", "h3", "h4", "h5", "h6"]):
            header.attrs["id"] = header.text.lower().replace(' ', '-').replace("'", "")
            anchor = html.new_tag("a", href=f'#{header.attrs["id"]}', **{"data-header":"1"})
            anchor.string = "#"
            header.append(anchor)

        if html.find('asciinema-player'):
            body = html.find('body')
            assert body is not None
            body.insert_after(html.new_tag('script', src="/js/asciinema-player.js"))

        blog_post = str(html)
        debug('writing to file')
        open(html_fname, 'w', encoding='utf-8').write(blog_post)
        debug('finished')


def generate_feed():
    fg = FeedGenerator()
    fg.id(BLOG_URL)
    fg.title('Mumbling about computers')
    fg.author({'name': 'David Ventura',
               'email': 'davidventura27+blog@gmail.com'})
    fg.link(href=BLOG_URL, rel='alternate')
    fg.link(href=("%srss.xml" % BLOG_URL), rel='self')
    fg.description('Blog')
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
               'email': 'davidventura27+blog@gmail.com'})
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

def generate_sitemap(tags: set[str]):
    with Path('blog/html/sitemap.txt').open('w') as fd:
        fd.write(f'{BLOG_URL}\n')
        for t in sorted(tags):
            fd.write(f'{BLOG_URL}tags/{t}\n')

if __name__ == '__main__':
    DEVMODE = False
    if len(sys.argv) > 1 and sys.argv[1].lower() == 'dev':
        DEVMODE = True
    tags = get_all_tags()
    for tag in tags:
        generate_tag_index(tag)
    generate_sitemap(tags)
    filter_name = sys.argv[2] if len(sys.argv) > 2 else None
    main(filter_name)
    generate_index()
