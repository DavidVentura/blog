#!/bin/bash
[ -z "$VIRTUAL_ENV" ] && source venv/bin/activate
set -e
echo 'Generating blog'
venv/bin/python generate.py >/dev/null
if [[ $(find "blog/html/blogs-i-follow.html" -mtime +1 -print) ]]; then
    echo 'Re-generating webring'
    venv/bin/python webring-generator.py >/dev/null
fi
if [[ "./blog/html/css/style-input.css" -nt "./blog/html/css/style-2025-09-19.css" ]]; then
    echo "Regenerating css"
    pnpm run tailwind
fi

grep -r live.js blog/html/ && echo -e "Dev mode found in blogs, aborting - run \ngrep -rl live.js blog/html/\n to check" && exit 1

if [[ "blog/raw/bookworm/architecture.dot" -nt "blog/html/images/bookworm-architecture.png" ]]; then
    dot blog/raw/bookworm/architecture.dot -Tpng > blog/html/images/bookworm-architecture.png
fi

bash sync.sh
