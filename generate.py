#!/usr/bin/env python3
import glob
import os
import re
import shutil
import sys

import pytz

from dataclasses import asdict, dataclass
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
md = Markdown(extras=["fenced-code-blocks", "nofollow", "footnotes", "metadata", "tables", "header-ids"])

@dataclass
class PostMetadata:
    title: str
    tags: List[str]
    description: str
    date: date
    incomplete: bool = False
    path: Optional[str] = None

    @staticmethod
    def from_dict(d) -> 'PostMetadata':
        date = datetime.strptime(d['date'], "%Y-%m-%d").date()
        tags = [t.strip() for t in d['tags'].split(',') if t]
        data = {**d, 'date': date, 'tags': tags} 
        return PostMetadata(**data)

def debug(*msg):
    if DEBUG:
        print(*msg, flush=True)

def convert_f(fname):
    with open(fname, 'r') as fd:
        return convert(fd.read())

@lru_cache
def convert(text):
    return md.convert(text)

def files_to_embed(relpath, text):
    ret = []
    for match in EMBED_FILE_RE.finditer(text):
        fname = match.group('fname')
        ret.append(os.path.join(relpath, fname))
    return ret

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
    template = Template('<h1>{{ title }}</h1>')
    return template.render(asdict(metadata))


def generate_post(header, body, title, tags, description, date):
    rendered = BODY_TEMPLATE.render(header=header,
            post=body,
            title=title,
            tags=tags,
            date=date,
            description=description,
            devmode=DEVMODE)
    return rendered


def sanitize_title(title):
    tmp_title = title.replace(' ', '-').lower().strip('-')
    return valid_title_chars.sub('', tmp_title).strip('-')


def newer(f1, files):
    mtime = os.path.getmtime
    return all([mtime(f1) > mtime(x) for x in files])


def main():
    this_script = __file__
    for target in glob.glob("blog/raw/*"):
        post_file = os.path.join(target, 'POST.md')
        if not os.path.exists(post_file):
            print("Target post file (%s) does not exist" % post_file)
            continue

        debug(target)

        md_str = open(post_file, encoding='utf-8').read()
        md_str = embed_files(target, md_str)
        _files_to_embed = files_to_embed(target, md_str)
        body = convert(md_str)

        r = PostMetadata.from_dict(body.metadata)

        if r.incomplete and not DEVMODE:
            debug('Incomplete - skipping')
            continue

        header = generate_header(r)
        safe_title = sanitize_title(r.title)
        html_fname = 'blog/html/%s.html' % safe_title

        if os.path.isfile(html_fname):
            if newer(html_fname, [post_file, this_script, BODY_TEMPLATE_FILE] + _files_to_embed):
                debug('Stale file')
                continue

        debug('generating text post')
        html_str = generate_post(header, body, r.title, r.tags, r.description, r.date)
        html = BeautifulSoup(html_str, features='html5lib')
        for header in html.find('article').find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
            header.attrs["id"] = header.text.lower().replace(' ', '-')

        if html.find('asciinema-player'):
            html.find('body').insert_after(html.new_tag('script', src="/js/asciinema-player.js"))

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
    return fg


def make_rss_entry(feed, item: PostMetadata):
    fe = feed.add_entry()
    url = '%s%s' % (BLOG_URL, item.path[1:])
    fe.id(url)
    tstamp = datetime.combine(item.date, datetime.min.time())
    tstamp = pytz.timezone("Europe/Amsterdam").localize(tstamp)
    fe.link(href=url)
    fe.author({'name': 'David Ventura',
               'email': 'davidventura27+blog@gmail.com'})
    fe.pubDate(tstamp)
    fe.title(item.title)
    if item.description:
        fe.description(item.description)
    # everything was mutated inside feed
    return tstamp


def generate_index():
    items: List[PostMetadata] = []
    feed = generate_feed()
    last_update = None
    for f in glob.glob("blog/raw/*/POST.md"):
        item = PostMetadata.from_dict(convert_f(f).metadata)
        if item.incomplete and not DEVMODE:
            continue
        item.path = "/%s.html" % sanitize_title(item.title)
        items.append(item)

    s_items = sorted(items, key=lambda k: k.date)
    for item in s_items:
        tstamp = make_rss_entry(feed, item)
        if last_update is None:
            last_update = tstamp
        last_update = max(last_update, tstamp)

    rendered = INDEX_TEMPLATE.render(index=reversed(s_items))
    open('blog/html/index.html', 'w', encoding='utf-8').write(rendered)
    feed.updated(last_update)
    feed.rss_file('blog/html/rss.xml', pretty=True)

def get_all_tags():
    tags = set()
    for f in glob.glob("blog/raw/*/POST.md"):
        item = PostMetadata.from_dict(convert_f(f).metadata)
        tags = tags.union(set(item.tags))
    return tags

def generate_tag_index(tag):
    items: List[PostMetadata] = []
    for f in glob.glob("blog/raw/*/POST.md"):
        item = PostMetadata.from_dict(convert_f(f).metadata)
        if tag not in item.tags:
            continue
        item.path = "/%s.html" % sanitize_title(item.title)
        items.append(item)

    s_items = sorted(items, key=lambda k: k.date, reverse=True)
    rendered = INDEX_TEMPLATE.render(index=s_items)
    fpath = Path('blog/html/tags/%s/index.html' % tag)
    fpath.parent.mkdir(parents=True, exist_ok=True)
    open(str(fpath), 'w', encoding='utf-8').write(rendered)

def copy_followed():
    shutil.copyfile('blog/template/blogs-i-follow.html', 'blog/html/blogs-i-follow.html')

if __name__ == '__main__':
    DEVMODE = False
    if len(sys.argv) > 1 and sys.argv[1].lower() == 'dev':
        DEVMODE = True
    for tag in get_all_tags():
        generate_tag_index(tag)
    main()
    generate_index()
    copy_followed()
