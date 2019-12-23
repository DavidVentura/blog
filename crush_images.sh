#!/bin/bash
find blog/html/images -name '*png' -exec pngcrush -ow -reduce {} \;
