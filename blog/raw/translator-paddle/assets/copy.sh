#!/bin/bash
set -euo pipefail

DIR=~/git/translator-rs/angle-out/

FILES=(input heatmap recognize-nodeskew recognize-deskew corners dewarp dewarp-rec bbox-strips/box-001 deskewed/box-001 dewarp-strips/box-000 boxes oriented_boxes)
for f in "${FILES[@]}"; do
	convert "$DIR/$f.png" -quality 85 -resize 600x-1\> "$(echo $f | tr '/' '_').jpg"
done


DIR=~/git/translator-rs/bendy-out/
FILES=(heatmap bbox-strips/box-001 deskewed/box-001)
for f in "${FILES[@]}"; do
	convert "$DIR/$f.png" -quality 85 -resize 600x-1\> "bendy_$(echo $f | tr '/' '_').jpg"
done
