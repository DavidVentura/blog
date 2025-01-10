#!/bin/bash
set -eu

if [ $# -ne 1 ]; then
	echo "Usage $0 <current_date> <new_date>"
	echo "Current date is probably"
	git grep -hoP 'href="/css/style-\K\d{4}-\d{2}-\d{2}' blog/template/ | sort -u
	echo and new date is $(date +%Y-%m-%d)
	exit 1
fi
current_date=$1
new_date=$2
sed -i "s/$current_date/$new_date/g" $(git grep -l "$current_date")
