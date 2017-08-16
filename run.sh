#!/bin/bash
source credentials
docker run -v "$PWD/scripts":/root/scripts/ \
           -v "$PWD/blog/raw/":/root/raw \
           -v "$PWD/blog/images":/root/images \
           -v "$PWD/blog/html":/root/html \
           -e S3_ACCESS_KEY="$S3_ACCESS_KEY" \
           -e S3_SECRET_KEY="$S3_SECRET_KEY" \
           -e COMMIT="$COMMIT" \
           blogging:latest
