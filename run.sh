#!/bin/bash
set -eu

COMMIT=$(git rev-parse HEAD)

docker build -t blogging .
docker run \
           -v "$PWD/scripts":/root/scripts/ \
           -v "$PWD/blog/raw/":/root/raw \
           -v "$PWD/blog/images":/root/images \
           -v "$PWD/blog/videos":/root/videos \
           -v "$PWD/blog/template":/root/template \
           -v "$PWD/blog/html":/root/html \
           -v "$PWD/blog/tags":/root/tags \
           -e COMMIT="$COMMIT" \
           blogging:latest
