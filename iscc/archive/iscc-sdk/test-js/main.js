const fs = require('fs');
const sharp = require('sharp');
const crypto = require('crypto');

async function imageExifTransposeWithHash(filePath) {
    try {
        // Read the image from the file
        const imgBuffer = await fs.promises.readFile(filePath);

        // Transpose image according to EXIF Orientation tag
        const transposedImageBuffer = await sharp(imgBuffer).rotate().toBuffer();

        console.log("Image exif transpose applied");

        // Compute SHA256 hash of the transposed image buffer
        const hash = crypto.createHash('sha256');
        hash.update(transposedImageBuffer);
        const sha256Hash = hash.digest('hex');

	console.log(transposedImageBuffer.slice(0,64).toString('hex'))
        console.log("SHA256 Hash:", sha256Hash);

        return transposedImageBuffer;
    } catch (error) {
        console.error("Error reading or processing the image:", error);
        throw error;
    }
}

// Example usage
const filePath = 'random_image_11998-24992.png';
imageExifTransposeWithHash(filePath)
    .then((transposedImageBuffer) => {
        // Process the transposed image buffer as needed
    })
    .catch((error) => {
        // Handle errors
    });
