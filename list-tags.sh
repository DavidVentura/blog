#!/bin/bash
git grep -wh ^tags blog/raw/ | sort | cut -d: -f2  | xargs | tr -d , | tr ' ' '\n'| sort | uniq -c | sort -n
