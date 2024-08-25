#!/bin/bash
set -xeu

current_date=$1
new_date=$1
sed -i "s/$current_date/$new_date/g" $(git grep -l "$current_date")
