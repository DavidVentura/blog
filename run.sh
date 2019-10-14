#!/bin/bash
[ -z "$VIRTUAL_ENV" ] && source .venv/bin/activate
set -e
python generate.py

dot blog/raw/bookworm/architecture.dot -Tpng > blog/html/images/bookworm-architecture.png

rsync -ar blog/html/ root@web.labs:/var/www/blog-devops
scp _blogs-i-follow.html root@web.labs:/var/www/blog-devops/blogs-i-follow.html
