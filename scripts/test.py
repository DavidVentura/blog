#!/usr/bin/env python3
import json
import markdown2
import re
import os
import tinys3
import sys

from datetime import datetime
from jinja2 import Template

BUCKET = 'blog-davidventura'
ENDPOINT = 's3-sa-east-1.amazonaws.com'


def parse_images(fname, conn, safe_title):
    lines = open(fname).readlines()
    inline = re.compile(r'!\[.*?\]\((?P<cap>.*?)(?: |\))')
    ref = re.compile(r'^\[.*?\]: (?P<cap>.*?)(?: |$)')
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
    j['date'] = datetime.strptime(j['date'], "%Y-%m-%dT%H:%M:%SZ")
    return j


def generate_header(metadata):
    template = Template(open('template/header.html', 'r').read())
    return template.render(metadata)


def generate_post(header, body):
    template = Template(open('template/body.html', 'r').read())
    rendered = template.render(header=header, post=body)
    return rendered


def sanitize_title(title):
    valid_title_chars = re.compile(r'[^a-zA-Z0-9._-]')
    tmp_title = title.replace(' ', '-').lower().strip('-')
    return valid_title_chars.sub('', tmp_title).strip('-')


def main():
    S3_ACCESS_KEY, S3_SECRET_KEY = setup_keys()
    conn = tinys3.Connection(S3_ACCESS_KEY, S3_SECRET_KEY,
                             endpoint=ENDPOINT)
    r = parse_metadata('target/metadata.json')
    header = generate_header(r)
    safe_title = sanitize_title(r['title'])
    parsed = parse_images('target/POST.md', conn, safe_title)
    body = markdown2.markdown(parsed, extras=["fenced-code-blocks"])
    blog_post = generate_post(header, body)
    html_fname = 'html/%s.html' % safe_title
    open(html_fname, 'w', encoding='utf-8').write(blog_post)


if __name__ == '__main__':
    main()
