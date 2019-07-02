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
           -e S3_ACCESS_KEY="$S3_ACCESS_KEY" \
           -e S3_SECRET_KEY="$S3_SECRET_KEY" \
           -e COMMIT="$COMMIT" \
           blogging:latest
