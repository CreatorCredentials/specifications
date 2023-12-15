#!/bin/bash

# docker run idk-v3 poetry run idk
# docker run -v /home/alen/work/iscc/test-idk:/data -v /home/alen/work/iscc/config:/config  idk-v3 poetry run idk c2pabatch /config/manifest.json /data
docker run -v /home/alen/work/iscc/test-idk:/data -v /home/alen/work/iscc/config:/config  idk-v3 poetry run idk batch /data
