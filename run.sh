#!/bin/bash
[ -z "$VIRTUAL_ENV" ] && source .venv/bin/activate
set -e
python scripts/test.py
rsync -ar blog/html/ root@web.labs:/var/www/blog-devops
