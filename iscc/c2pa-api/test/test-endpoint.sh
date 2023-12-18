#!/bin/bash

# curl -X POST \
#   -H "Content-Type: multipart/form-data" \
#   -F "image=@$1" \
#   http://localhost:8080/upload

# which sha2
file_path=$1
echo $file_path
# sha2 -256 $file_path
sha256sum $file_path

# Set the server URL
server_url="http://localhost:8001/v1/c2pa"

# Use curl to send the file as binary data in a POST request
# curl -X POST -H "Content-Type: multipart/form-data" --data-raw "@$1" "$server_url"

curl -i -X POST ${server_url} \
  -H "content-type: image/jpeg" \
  -T "$file_path"
