#!/bin/bash
if [ $# -ne 1 ]; then 
    echo 1 arg -- directory to watch 
    exit 1
fi

if [ ! -d $1 ]; then
    echo $1 does not exist/is not a dir
    exit 1
fi
inotifywait -m -e CLOSE_WRITE $1 | grep --line-buffered POST.md | while read -r line; do .venv/bin/python generate.py >/dev/null; echo build | ts ; done
