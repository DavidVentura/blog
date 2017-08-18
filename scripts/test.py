#!/usr/bin/env python3
import glob
import json
import markdown2
import os
import re
import sys
import tinys3

from datetime import datetime
from jinja2 import Template

BUCKET = 'blog-davidventura'
ENDPOINT = 's3-sa-east-1.amazonaws.com'
valid_title_chars = re.compile(r'[^a-zA-Z0-9._-]')


def connect_to_s3():
    S3_ACCESS_KEY, S3_SECRET_KEY = setup_keys()
    return tinys3.Connection(S3_ACCESS_KEY, S3_SECRET_KEY, endpoint=ENDPOINT)


def parse_images(fname, safe_title):
    lines = open(fname).readlines()
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
    template = Template('<h1>{{ title }}</h1><h4>{{ date }}</h4>')
    return template.render(metadata)


def generate_post(header, body):
    template = Template(open('template/body.html', 'r').read())
    rendered = template.render(header=header, post=body)
    return rendered


def sanitize_title(title):
    tmp_title = title.replace(' ', '-').lower().strip('-')
    return valid_title_chars.sub('', tmp_title).strip('-')


def main():
    r = parse_metadata('target/metadata.json')
    header = generate_header(r)
    safe_title = sanitize_title(r['title'])
    parsed = parse_images('target/POST.md', safe_title)
    body = markdown2.markdown(parsed, extras=["fenced-code-blocks"])
    blog_post = generate_post(header, body)
    html_fname = 'html/%s.html' % safe_title
    open(html_fname, 'w', encoding='utf-8').write(blog_post)


def generate_index():
    items = []
    for f in glob.glob("raw/*/metadata.json"):
        item = parse_metadata(f)
        item['path'] = "/%s.html" % sanitize_title(item['title'])
        items.append(item)

    s_items = sorted(items, key=lambda k: k['date'], reverse=True)
    template = Template(open('template/index.html', 'r').read())
    rendered = template.render(index=s_items)
    open('html/index.html', 'w', encoding='utf-8').write(rendered)


if __name__ == '__main__':
    main()
    generate_index()
