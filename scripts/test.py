#!/usr/bin/env python3
import glob
import json
import markdown2
import os
import re
import sys
import tinys3
import pytz

from datetime import datetime
from jinja2 import Template
from feedgen.feed import FeedGenerator

BLOG_URL = 'https://blog-devops.davidventura.com.ar/'
BUCKET = 'blog-davidventura'
ENDPOINT = 's3-sa-east-1.amazonaws.com'
DEBUG = False
valid_title_chars = re.compile(r'[^a-zA-Z0-9._-]')


def debug(*msg):
    if DEBUG:
        print(*msg)


def connect_to_s3():
    S3_ACCESS_KEY, S3_SECRET_KEY = setup_keys()
    return tinys3.Connection(S3_ACCESS_KEY, S3_SECRET_KEY, endpoint=ENDPOINT)


def parse_images(fname, safe_title):
    lines = open(fname, encoding='utf-8').readlines()
    inline = re.compile(r'!\[.*?\]\((?P<cap>.*?)(?: |\))')
    ref = re.compile(r'^\[.*?\]: (?P<cap>.*?)(?: |$)')
    conn = None
    for idx in range(len(lines)):
        line = lines[idx]
        group = inline.search(line)
        if group is None:
            group = ref.search(line)
            if group is None:
                continue

        image_fname = group.group('cap')

        if not os.path.exists(image_fname):
            print("%s does not exist!" % image_fname)
            return

        f = open(image_fname, 'rb')
        nname = os.path.basename(image_fname)
        dest = "%s/%s" % (safe_title, nname)
        if conn is None:
            conn = connect_to_s3()
        conn.upload(dest, f, BUCKET, expires='max')
        target = 'https://%s/%s/%s' % (ENDPOINT, BUCKET, dest)
        lines[idx] = lines[idx].replace(image_fname, target)

    return "".join(lines)


def setup_keys():
    try:
        S3_ACCESS_KEY = os.environ['S3_ACCESS_KEY'].strip()
        S3_SECRET_KEY = os.environ['S3_SECRET_KEY'].strip()
    except KeyError as e:
        print('KeyError', e)
        sys.exit(1)
    return S3_ACCESS_KEY, S3_SECRET_KEY


def parse_metadata(target):
    data = open(target, 'r', encoding='utf-8').read()
    j = json.loads(data)
    j['date'] = datetime.strptime(j['date'], "%Y-%m-%d").date()
    return j


def generate_header(metadata):
    template = Template('<h5>{{ date }}</h5><h1>{{ title }}</h1>')
    return template.render(metadata)


def generate_post(header, body):
    template = Template(open('template/body.html', 'r').read())
    rendered = template.render(header=header, post=body)
    return rendered


def sanitize_title(title):
    tmp_title = title.replace(' ', '-').lower().strip('-')
    return valid_title_chars.sub('', tmp_title).strip('-')


def main():
    targets = os.environ['TARGET'].strip()
    for target in targets.split(';'):
        target = os.path.join('raw/', target)
        if not os.path.exists(target):
            print("Target path (%s) does not exist" % target)
            continue

        debug(target)
        debug('parsing metadata')
        r = parse_metadata('%s/metadata.json' % target)
        debug('generating header')
        header = generate_header(r)
        debug('sanitizing title')
        safe_title = sanitize_title(r['title'])
        debug('parsing images')
        parsed = parse_images('%s/POST.md' % target, safe_title)
        debug('generating body')
        body = markdown2.markdown(parsed, extras=["fenced-code-blocks"])
        debug('generating post')
        blog_post = generate_post(header, body)
        html_fname = 'html/%s.html' % safe_title
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
    # fg.logo('')
    fg.language('en')
    return fg


def generate_index():
    items = []
    feed = generate_feed()
    last_update = None
    for f in glob.glob("raw/*/metadata.json"):
        item = parse_metadata(f)
        item['path'] = "/%s.html" % sanitize_title(item['title'])
        items.append(item)

    s_items = sorted(items, key=lambda k: k['date'], reverse=True)
    for item in s_items[::-1]:
        fe = feed.add_entry()
        url = '%s%s' % (BLOG_URL, item['path'][1:])
        fe.id(url)
        tstamp = datetime.combine(item['date'], datetime.min.time())
        tstamp = pytz.timezone("America/Buenos_Aires").localize(tstamp)
        fe.link(href=url)
        fe.author({'name': 'David Ventura',
                   'email': 'davidventura27+blog@gmail.com'})
        fe.pubdate(tstamp)
        fe.title(item['title'])

        if last_update is None:
            last_update = tstamp
        last_update = max(last_update, tstamp)

    template = Template(open('template/index.html', 'r').read())
    rendered = template.render(index=s_items)
    open('html/index.html', 'w', encoding='utf-8').write(rendered)
    feed.updated(last_update)
    feed.rss_file('html/rss.xml', pretty=True)


if __name__ == '__main__':
    main()
    generate_index()
