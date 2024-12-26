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
	find "$DIR_TO_WATCH" -type f -name '*md' -exec touch {} \;
}

DIR_TO_WATCH="$1"
FILTER=$(basename $DIR_TO_WATCH)
trap _exit INT
echo 'watching...'
while true; do
	inotifywait -q -e MODIFY $DIR_TO_WATCH $DIR_TO_WATCH/assets/*.drawio generate.py
	venv/bin/python generate.py dev $FILTER
	sleep 0.3 || break
done
