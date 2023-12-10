#!/bin/bash

## This script generates 1000 random pngs. Approx size 500-600 Mb

# Set image dimensions
width=640
height=480

# Set output filename
output_dir="test-pics"

mkdir -p ${output_dir}

# Generate 1000 random images
for ((i = 1; i <= 1000; i++)); do
    # Set output filename
    output_file="${output_dir}/random_image_${RANDOM}-${RANDOM}.png"

    # Generate random pixel data
    convert -size ${width}x${height} xc:gray +noise Random -compress none "${output_file}"

    echo "Generated ${output_file}"
done

