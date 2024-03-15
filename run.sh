#!/bin/bash
[ -z "$VIRTUAL_ENV" ] && source venv/bin/activate
set -e
venv/bin/python generate.py

dot blog/raw/bookworm/architecture.dot -Tpng > blog/html/images/bookworm-architecture.png

echo 'syncing'
rsync -ar blog/html/ root@blog.davidv.dev:/var/www/blog-devops
echo 'synced'
