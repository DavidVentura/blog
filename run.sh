#!/bin/bash
set -eu

COMMIT=$(git rev-parse HEAD)

docker build -t blogging .
docker run \
           -v "$PWD/scripts":/root/scripts/ \
           -v "$PWD/blog/raw/":/root/raw \
           -v "$PWD/blog/html/images":/root/images \
           -v "$PWD/blog/html/videos":/root/videos \
           -v "$PWD/blog/template":/root/template \
           -v "$PWD/blog/html":/root/html \
           -e COMMIT="$COMMIT" \
           blogging:latest
