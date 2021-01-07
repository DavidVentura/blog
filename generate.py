#!/usr/bin/env python3
import glob
import json
import os
import re
import shutil
import sys

import markdown2
import pytz

from dataclasses import asdict, dataclass
from datetime import datetime, date
from pathlib import Path
from typing import Optional, List

from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator
from jinja2 import Template

BLOG_URL = 'https://blog.davidventura.com.ar/'
BODY_TEMPLATE_FILE = 'blog/template/body.html'
BODY_TEMPLATE = Template(open(BODY_TEMPLATE_FILE, 'r').read())
INDEX_TEMPLATE = Template(open('blog/template/index.html', 'r').read())
DEBUG = True
valid_title_chars = re.compile(r'[^a-zA-Z0-9._-]')

@dataclass
class PostMetadata:
    title: str
    tags: List[str]
    description: str
    date: date
    incomplete: bool = False
    path: Optional[str] = None

def debug(*msg):
    if DEBUG:
        print(*msg)


def parse_metadata(target) -> PostMetadata:
    data = open(target, 'r', encoding='utf-8').read()
    j = json.loads(data)
    j['date'] = datetime.strptime(j['date'], "%Y-%m-%d").date()
    return PostMetadata(**j)


def generate_header(metadata: PostMetadata):
    template = Template('<h1>{{ title }}</h1><small>{{ date }}</small>')
    return template.render(asdict(metadata))


def generate_post(header, body, title, tags, description):
    rendered = BODY_TEMPLATE.render(header=header,
            post=body,
            title=title,
            tags=tags,
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
        metadata_file = os.path.join(target, 'metadata.json')
        if not os.path.exists(post_file):
            print("Target post file (%s) does not exist" % post_file)
            continue
        if not os.path.exists(metadata_file):
            print("Target path (%s/metadata.json) does not exist" % target)
            continue

        debug(target)

        r = parse_metadata(metadata_file)
        if r.incomplete:
            debug('Incomplete - skipping')
            continue
        header = generate_header(r)
        safe_title = sanitize_title(r.title)
        html_fname = 'blog/html/%s.html' % safe_title

        if os.path.isfile(html_fname):
            if newer(html_fname, [post_file, metadata_file, this_script, BODY_TEMPLATE_FILE]):
                debug('Stale file')
                continue

        debug('generating body')
        md_str = open(post_file, encoding='utf-8').read()
        body_str = markdown2.markdown(md_str, extras=["fenced-code-blocks"])
        debug('generating text post')
        html_str = generate_post(header, body_str, r.title, r.tags, r.description)
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
#    fe.description(item['description'])
    # everything was mutated inside feed
    return tstamp


def generate_index():
    items: List[PostMetadata] = []
    feed = generate_feed()
    last_update = None
    for f in glob.glob("blog/raw/*/metadata.json"):
        item = parse_metadata(f)
        if item.incomplete:
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
    for f in glob.glob("blog/raw/*/metadata.json"):
        item = parse_metadata(f)
        tags = tags.union(set(item.tags))
    return tags

def generate_tag_index(tag):
    items: List[PostMetadata] = []
    for f in glob.glob("blog/raw/*/metadata.json"):
        item = parse_metadata(f)
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
