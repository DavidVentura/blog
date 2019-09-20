#!/usr/bin/env python3
import glob
import json
import markdown2
import os
import re
import sys
import pytz

from pathlib import Path
from datetime import datetime
from jinja2 import Template
from feedgen.feed import FeedGenerator
from bs4 import BeautifulSoup

BLOG_URL = 'https://blog.davidventura.com.ar/'
DEBUG = True
valid_title_chars = re.compile(r'[^a-zA-Z0-9._-]')

os.environ['HTTP_PROXY'] = 'http://proxies.labs:3128'
os.environ['HTTPS_PROXY'] = 'http://proxies.labs:3128'

def debug(*msg):
    if DEBUG:
        print(*msg)


def parse_metadata(target):
    data = open(target, 'r', encoding='utf-8').read()
    j = json.loads(data)
    j['date'] = datetime.strptime(j['date'], "%Y-%m-%d").date()
    return j


def generate_header(metadata):
    template = Template('<small>{{ date }}</small><h1>{{ title }}</h1>')
    return template.render(metadata)


def generate_post(header, body, title, tags):
    template = Template(open('blog/template/body.html', 'r').read())
    rendered = template.render(header=header, post=body, title=title, tags=tags)
    return rendered


def sanitize_title(title):
    tmp_title = title.replace(' ', '-').lower().strip('-')
    return valid_title_chars.sub('', tmp_title).strip('-')


def main():
    for target in glob.glob("blog/raw/*"):
        if not os.path.exists(target):
            print("Target path (%s) does not exist" % target)
            continue
        if not os.path.exists(os.path.join(target, 'POST.md')):
            print("Target path (%s/POST.md) does not exist" % target)
            continue
        if not os.path.exists(os.path.join(target, 'metadata.json')):
            print("Target path (%s/metadata.json) does not exist" % target)
            continue

        debug(target)
        debug('parsing metadata')
        r = parse_metadata('%s/metadata.json' % target)
        if 'incomplete' in r:
            debug('Incomplete - skipping')
            continue
        debug('generating header')
        header = generate_header(r)
        debug('sanitizing title')
        safe_title = sanitize_title(r['title'])
        debug('generating body')
        md_str = open("%s/POST.md" % target, encoding='utf-8').read()
        body_str = markdown2.markdown(md_str, extras=["fenced-code-blocks"])
        debug('generating text post')
        html_str = generate_post(header, body_str, r['title'], r['tags'])
        html = BeautifulSoup(html_str, features='html5lib')
        blog_post = html.prettify()
        html_fname = 'blog/html/%s.html' % safe_title
        debug('writing to file')
        open(html_fname, 'w', encoding='utf-8').write(blog_post)
        debug('finished')


def generate_feed():
    fg = FeedGenerator()
    fg.id(BLOG_URL)
    fg.title('Grouch mumbling about computers')
    fg.author({'name': 'David Ventura',
               'email': 'davidventura27+blog@gmail.com'})
    fg.link(href=BLOG_URL, rel='alternate')
    fg.link(href=("%srss.xml" % BLOG_URL), rel='self')
    fg.description('Blog')
    fg.language('en')
    return fg


def make_rss_entry(feed, item):
    fe = feed.add_entry()
    url = '%s%s' % (BLOG_URL, item['path'][1:])
    fe.id(url)
    tstamp = datetime.combine(item['date'], datetime.min.time())
    tstamp = pytz.timezone("Europe/Amsterdam").localize(tstamp)
    fe.link(href=url)
    fe.author({'name': 'David Ventura',
               'email': 'davidventura27+blog@gmail.com'})
    fe.pubDate(tstamp)
    fe.title(item['title'])
    # everything was mutated inside feed
    return tstamp


def generate_index():
    items = []
    feed = generate_feed()
    last_update = None
    for f in glob.glob("blog/raw/*/metadata.json"):
        item = parse_metadata(f)
        if 'incomplete' in item and item['incomplete']:
            continue
        item['path'] = "/%s.html" % sanitize_title(item['title'])
        items.append(item)

    s_items = sorted(items, key=lambda k: k['date'], reverse=True)
    for item in s_items[::-1]:
        tstamp = make_rss_entry(feed, item)
        if last_update is None:
            last_update = tstamp
        last_update = max(last_update, tstamp)

    template = Template(open('blog/template/index.html', 'r').read())
    rendered = template.render(index=s_items)
    open('blog/html/index.html', 'w', encoding='utf-8').write(rendered)
    feed.updated(last_update)
    feed.rss_file('blog/html/rss.xml', pretty=True)

def get_all_tags():
    tags = set()
    for f in glob.glob("blog/raw/*/metadata.json"):
        item = parse_metadata(f)
        tags = tags.union(set(item['tags']))
    return tags

def generate_tag_index(tag):
    items = []
    for f in glob.glob("blog/raw/*/metadata.json"):
        item = parse_metadata(f)
        if tag not in item['tags']:
            continue
        item['path'] = "/%s.html" % sanitize_title(item['title'])
        items.append(item)
    print(items)

    s_items = sorted(items, key=lambda k: k['date'], reverse=True)
    template = Template(open('blog/template/index.html', 'r').read())
    rendered = template.render(index=s_items)
    fpath = Path('blog/html/tags/%s/index.html' % tag)
    fpath.parent.mkdir(parents=True, exist_ok=True)
    open(str(fpath), 'w', encoding='utf-8').write(rendered)

if __name__ == '__main__':
    for tag in get_all_tags():
        generate_tag_index(tag)
    main()
    generate_index()
