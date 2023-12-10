chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  console.log("Hi!!!");
  if (request.action === "getActiveTabUrl") {
    console.log("Hi!!!");
    const url = window.location.href;
    sendResponse({ url });
  }
});

// content.js
console.log("Image Metadata Checker Extension Loaded!");

const PROCESSED_CLASS = "image-metadata-processed";

// Function to check if image has metadata
function checkImageMetadata(image) {
  // Skip images that have already been processed
  if (image.classList.contains(PROCESSED_CLASS)) {
    return;
  }

  // Skip images smaller than 100x100
  if (image.width < 100 || image.height < 100) {
    return;
  }

  url = image.src;
  chrome.runtime.sendMessage(
    { action: "sendImageUrls", imgUrl: url },
    function (response) {
      if (chrome.runtime.lastError) {
        // Handle the error
        addTextOverImage(image, "X");
        console.error("Error:", chrome.runtime.lastError);
          image.classList.add(PROCESSED_CLASS);
        // Add logic for error handling, e.g., display an error message
      } else {
        // Process the response from the background script

        if (response.error) {
          // Handle the error returned by the background script
          addTextOverImage(image, "XX");
          console.error("Background script error:", response.error);
          image.classList.add(PROCESSED_CLASS);
          // Add logic for error handling, e.g., display an error message
        } else {
          // No error, process the successful response
          addTextOverImage(image, response.serverResponse);
          image.classList.add(PROCESSED_CLASS);
        }
      }
    }
  );
  // Mark the image as processed to avoid duplicates

  // Convert the image to base64
  // getBase64Image(image).then((base64Image) => {
  //   // Assuming you have the server URL
  //   const serverUrl = 'http://localhost:3000/metadata';

  //   // Make a POST request to the server
  //   fetch(serverUrl, {
  //     method: 'POST',
  //     headers: {
  //       'Content-Type': 'application/json',
  //     },
  //     body: JSON.stringify({
  //       image: base64Image,
  //     }),
  //   })
  //     .then((response) => response.json())
  //     .then((metadata) => {
  //       if (metadata) {
  // 	   addTextOverImage(image, "hello", "world");
  //         // addTextOverImage(image);

  //         // Mark the image as processed to avoid duplicates
  //         image.classList.add(PROCESSED_CLASS);
  //       }
  //     })
  //     .catch((error) => {
  //       console.error('Error fetching metadata:', error);
  //     });
  // });
}

// Function to add "OK" text over the image
// V1
// function addTextOverImage(image) {
//   const textElement = document.createElement('div');
//   textElement.textContent = 'OK';
//   textElement.style.position = 'absolute';
//   textElement.style.top = '0';
//   textElement.style.right = '0';
//   textElement.style.background = 'rgba(255, 255, 255, 0.7)';
//   textElement.style.padding = '2px';
//   textElement.style.fontSize = '12px';
//   image.parentElement.appendChild(textElement);
// }

// Function to add "OK" text over the image
function addTextOverImage(image, name, type) {
  const textElement = document.createElement("div");
  textElement.textContent = "ISCC Code";
  textElement.style.position = "absolute";
  textElement.style.top = "0";
  textElement.style.right = "0";
  textElement.style.background = "rgba(255, 255, 255, 0.7)";
  textElement.style.padding = "2px";
  textElement.style.fontSize = "16px";

  // Add basic information for the tag
  textElement.setAttribute("data-name", name);

  // Add event listener for mouseover
  textElement.addEventListener("mouseover", showTag);

  // Append the text element to the parent of the image
  image.parentElement.appendChild(textElement);

  // Function to show the tag
  function showTag() {
    const tag = document.createElement("div");
    tag.textContent = `${name}`;
    tag.style.position = "absolute";
    tag.style.top = "20px"; // Adjust the position of the tag
    tag.style.left = "0";
    tag.style.background = "rgba(255, 255, 255, 0.9)";
    tag.style.padding = "8px";
    tag.style.borderRadius = "4px";
    tag.style.fontSize = "14px";
    tag.style.zIndex = "1000";

    // Add a click event listener
    tag.addEventListener("click", handleClick);

    // Append the tag next to the text element
    textElement.parentNode.insertBefore(tag, textElement.nextSibling);

    // Remove the tag when mouseout
    tag.addEventListener("mouseout", () => {
      tag.remove();
    });

    // Function to handle click
    function handleClick() {
      // Extract the text content of the tag
      const tagText = tag.textContent.trim(); // Trim to remove any leading/trailing whitespace

      // Define the URL based on the extracted text content
      const url = `https://iscc.io/api/v1/explain/${encodeURIComponent(tagText)}`;

      // Open a new tab with the specified URL
      window.open(url, '_blank');
    }
  }
}

// Function to convert image to base64
function getBase64Image(img) {
  return new Promise((resolve, reject) => {
    const canvas = document.createElement("canvas");
    const ctx = canvas.getContext("2d");
    canvas.width = img.width;
    canvas.height = img.height;

    ctx.drawImage(img, 0, 0, img.width, img.height);

    canvas.toBlob(
      (blob) => {
        const reader = new FileReader();
        reader.readAsDataURL(blob);
        reader.onloadend = () => {
          const base64data = reader.result.split(",")[1];
          resolve(base64data);
        };
      },
      "image/jpeg", // Adjust the format based on your image type
      1.0 // Adjust the quality if needed
    );
  });
}

// Function to handle intersection (scroll) events
// function handleIntersection(entries) {
//   entries.forEach((entry) => {
//     if (entry.isIntersecting) {
//       // The target is now in the viewport, check if it's an image
//       const target = entry.target;
//       if (target.tagName.toLowerCase() === 'img') {
//         checkImageMetadata(target);
//       }
//     }
//   });
// }

// Set up an IntersectionObserver to detect when images become visible as you scroll
// const intersectionObserver = new IntersectionObserver(handleIntersection, {
//   threshold: 0.5, // Adjust as needed
// });

// // Find all images on the page and observe them
// const images = document.getElementsByTagName('img');
// for (const image of images) {
//   checkImageMetadata(image);
//   intersectionObserver.observe(image);
// }

// Function to handle intersection (scroll) events
function handleIntersection(entries) {
  entries.forEach((entry) => {
    if (entry.isIntersecting) {
      // The target is now in the viewport, check if it's an image
      const target = entry.target;
      if (target.tagName.toLowerCase() === "img") {
        checkImageMetadata(target);
        // Stop observing the target after processing it (optional)
        intersectionObserver.unobserve(target);
      }
    }
  });
}

// Set up an IntersectionObserver to detect when images become visible as you scroll
const intersectionObserver = new IntersectionObserver(handleIntersection, {
  threshold: 0.5, // Adjust as needed
});

// Function to find and observe new images on the page
function observeNewImages() {
  const images = document.querySelectorAll(
    "img:not(.image-metadata-processed)"
  );
  for (const image of images) {
    intersectionObserver.observe(image);
  }
}

// Initial observation for existing images
const existingImages = document.querySelectorAll("img");
for (const image of existingImages) {
  checkImageMetadata(image);
  intersectionObserver.observe(image);
}

// Observe new images when the page loads
observeNewImages();

// Set up a MutationObserver to detect changes in the DOM
const mutationObserver = new MutationObserver(() => {
  observeNewImages();
});

mutationObserver.observe(document.body, {
  childList: true,
  subtree: true,
});
