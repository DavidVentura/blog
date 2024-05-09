#!/bin/bash
[ -z "$VIRTUAL_ENV" ] && source venv/bin/activate
set -e
echo 'Generating..'
venv/bin/python generate.py >/dev/null

grep -r live.js blog/html/ && echo -e "Dev mode found in blogs, aborting - run \ngrep -rl live.js blog/html/\n to check" && exit 1
dot blog/raw/bookworm/architecture.dot -Tpng > blog/html/images/bookworm-architecture.png

echo 'syncing'
rsync -ar blog/html/ root@blog.davidv.dev:/var/www/blog-devops
echo 'synced'
