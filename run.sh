#!/bin/bash
[ -z "$VIRTUAL_ENV" ] && source .venv/bin/activate
set -e
python generate.py
rsync -ar blog/html/ root@web.labs:/var/www/blog-devops
scp _blogs-i-follow.html root@web.labs:/var/www/blog-devops/blogs-i-follow.html
