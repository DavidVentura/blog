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
from bs4 import BeautifulSoup

BLOG_URL = 'https://blog-devops.davidventura.com.ar/'
BUCKET = 'blog-davidventura'
ENDPOINT = 's3-sa-east-1.amazonaws.com'
DEBUG = False
valid_title_chars = re.compile(r'[^a-zA-Z0-9._-]')

os.environ['HTTP_PROXY'] = 'http://proxies.labs:3128'
os.environ['HTTPS_PROXY'] = 'http://proxies.labs:3128'

def debug(*msg):
    if DEBUG:
        print(*msg)


def connect_to_s3():
    S3_ACCESS_KEY, S3_SECRET_KEY = setup_keys()
    return tinys3.Connection(S3_ACCESS_KEY, S3_SECRET_KEY, endpoint=ENDPOINT)


def upload_file_to_s3(filename, safe_title, conn=None):
    if not os.path.exists(filename):
        print("%s does not exist!" % filename)
        return None

    f = open(filename, 'rb')
    bname = os.path.basename(filename)
    dest = "%s/%s" % (safe_title, bname)
    if conn is None:
        conn = connect_to_s3()
    conn.upload(dest, f, BUCKET, expires='max')
    target = 'https://%s/%s/%s' % (ENDPOINT, BUCKET, dest)
    return target

def is_valid_image_fname(image_fname):
    if not image_fname.startswith('images/'):
        return False
    if not image_fname[-3:].lower() in ['png', 'gif', 'jpg']:
        return False
    return True

def parse_images(html, safe_title):
    uploaded = []
    tags = []
    for anchor in html.find_all('a'):
        image_fname = anchor.attrs['href']
        if not is_valid_image_fname(image_fname) or image_fname in uploaded:
            continue
        uploaded.append(image_fname)
        tags.append(anchor)

    for image in html.find_all('img'):
        image_fname = image.attrs['src']
        if not is_valid_image_fname(image_fname) or image_fname in uploaded:
            continue
        uploaded.append(image_fname)
        tags.append(image)

    for tag in tags:
        attr = 'src'
        if 'href' in tag.attrs:
            attr = 'href'

        image_fname = tag.attrs[attr]
        image_link = upload_file_to_s3(image_fname, safe_title)

        if image_link is None:
            print("Issue uploading %s to S3" % image_fname)
            continue
        tag.attrs[attr] = image_link

    return html


def parse_videos(html, title):
    conn = None
    for video in html.find_all('video'):
        for source in video.find_all('source'):
            if conn is None:
                conn = connect_to_s3()
            video_file = source.attrs['src']
            video_link = upload_file_to_s3(video_file, title, conn)
            if video_file is None:
                print("Issue uploading %s to S3" % video_file)
                continue
            source.attrs['src'] = video_link

    return html

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
    template = Template('<small>{{ date }}</small><h1>{{ title }}</h1>')
    return template.render(metadata)


def generate_post(header, body, title):
    template = Template(open('template/body.html', 'r').read())
    rendered = template.render(header=header, post=body, title=title)
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
        debug('generating body')
        md_str = open("%s/POST.md" % target, encoding='utf-8').read()
        body_str = markdown2.markdown(md_str, extras=["fenced-code-blocks"])
        debug('generating text post')
        html_str = generate_post(header, body_str, r['title'])
        html = BeautifulSoup(html_str, features='html5lib')
        debug('parsing images')
        html = parse_images(html, safe_title)
        debug('parsing videos')
        html = parse_videos(html, safe_title)
        blog_post = html.prettify()
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
        tstamp = pytz.timezone("Europe/Amsterdam").localize(tstamp)
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
