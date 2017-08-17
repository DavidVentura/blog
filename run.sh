#!/bin/bash
set -eu

source credentials
COMMIT=$(git rev-parse HEAD)
COMMIT_MSG=$(git log --format=%B -n 1)
COMMIT_MSG="deploy everything"

TARGET=$(echo "$COMMIT_MSG" | grep -oP "^deploy \K([a-zA-Z0-9._-]+)" || true)

if [[ "$COMMIT_MSG" != "deploy"* ]]; then
    echo 'No need to deploy'
    exit 0
fi

if [[ -z "${TARGET// }" ]]; then
    echo "Invalid target"
    exit 1
fi

function run {
    TARGET="$1"
    echo "$TARGET"
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
}
docker build -t blogging .

if [ "$TARGET" == "everything" ]; then
    find blog/raw -maxdepth 1 -mindepth 1 -type d |\

    while read -r post; do
        run "$(basename "$post")"
    done
else
    if [ ! -d "$PWD/blog/raw/$TARGET" ]; then
        echo "Target path does not exist"
        exit 1
    fi
    run "$TARGET"
fi
