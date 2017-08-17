#!/bin/bash
set -eu

if [ $# -ne 1 ]; then
    echo "Usage: 1 argument, target blog root"
    exit 1
fi

source credentials
COMMIT=$(git rev-parse HEAD)
COMMIT_MSG=$(git log --format=%B -n 1)
TARGET="$1"

if [ ! -d "$PWD/blog/raw/$TARGET" ]; then
    echo "Target path does not exist"
    exit 1
fi

if [[ "$COMMIT_MSG" != *"deploy"* ]]; then
    echo 'No need to deploy'
#    exit 0
fi

docker build -t blogging .
docker run -v "$PWD/scripts":/root/scripts/ \
           -v "$PWD/blog/raw/$TARGET":/root/target \
           -v "$PWD/blog/raw/":/root/raw \
           -v "$PWD/blog/images":/root/images \
           -v "$PWD/blog/template":/root/template \
           -v "$PWD/blog/html":/root/html \
           -e S3_ACCESS_KEY="$S3_ACCESS_KEY" \
           -e S3_SECRET_KEY="$S3_SECRET_KEY" \
           -e COMMIT="$COMMIT" \
           blogging:latest
