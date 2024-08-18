#!/bin/bash
[ -z "$VIRTUAL_ENV" ] && source venv/bin/activate
set -e
echo 'Generating blog'
venv/bin/python generate.py >/dev/null
if [[ $(find "blog/html/blogs-i-follow.html" -mtime +1 -print) ]]; then
    echo 'Re-generating webring'
    venv/bin/python webring-generator.py >/dev/null
fi
pnpm run tailwind

grep -r live.js blog/html/ && echo -e "Dev mode found in blogs, aborting - run \ngrep -rl live.js blog/html/\n to check" && exit 1
dot blog/raw/bookworm/architecture.dot -Tpng > blog/html/images/bookworm-architecture.png

echo 'syncing'
rsync -ar blog/html/ root@blog.davidv.dev:/var/www/blog-devops
echo 'synced'
