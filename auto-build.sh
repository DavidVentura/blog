#!/bin/bash
if [ $# -ne 1 ]; then 
    echo 1 arg -- directory to watch 
    exit 1
fi

if [ ! -d $1 ]; then
    echo $1 does not exist/is not a dir
    exit 1
fi

function _exit {
	echo updating timestamps so next non-dev builds will process this post
	find "$DIR_TO_WATCH" -type f -exec touch {} \;
}

DIR_TO_WATCH="$1"
trap _exit INT
inotifywait -m -e CLOSE_WRITE $DIR_TO_WATCH | grep --line-buffered POST.md | while read -r line; do .venv/bin/python generate.py dev >/dev/null; echo build | ts ; done
