chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "getActiveTabUrl") {
    const url = window.location.href;
    sendResponse({ url });
  }
});

// content.js
console.log("Image Metadata Checker Extension Loaded!");

const PROCESSED_CLASS = "image-metadata-processed";
const TAG_CLASS = "tag-set";
const iconPath = chrome.runtime.getURL("info.svg");
const currentTabUrl = window.location.href;

const EXISTS = '\u{2714}';
const NOT_EXISTS = '\u{2718}';
const UNDER_CONSTRUCTION = '\u{1F6A7}';

// Function to check if image has metadata
function checkImageMetadata(image) {
  // Skip images that have already been processed
  if (image.classList.contains(PROCESSED_CLASS)) {
    return;
  }

  // Skip images smaller than 100x100
  if (image.width < 100 || image.height < 100) {
    image.classList.add(PROCESSED_CLASS);
    return;
  }

  url = image.src;
  chrome.runtime.sendMessage(
    { action: "sendImageUrls", imgUrl: url, tabUrl: currentTabUrl },
    function (response) {
      image.classList.add(PROCESSED_CLASS);
      if (chrome.runtime.lastError) {
        // Handle the error
        addTextOverImage(image, "Runtime Error");
        console.error("Error:", chrome.runtime.lastError);
        // Add logic for error handling, e.g., display an error message
      } else {
        // Process the response from the background script

        if (response.error) {
          // Handle the error returned by the background script
          addTextOverImage(image, "Response Error");
          console.error("Background script error:", response.error);
          // Add logic for error handling, e.g., display an error message
        } else {
          // No error, process the successful response
          addTextOverImage(image, response.serverResponse);
        }
      }
    }
  );
}

function addTextOverImage(image, record, type) {
  console.log(record)
  // Check whether c2pa exists
  let state_c2pa = NOT_EXISTS;
  if (record['statements'] == 8) {
    state_c2pa = EXISTS;
  }
  // TODO: same for AI and ISCC
  let state_iscc = UNDER_CONSTRUCTION;
  let state_ai = UNDER_CONSTRUCTION;

  // Check if the image already has the TAG_CLASS
  if (image.classList.contains(TAG_CLASS)) {
    return;
  }

  // Add TAG_CLASS to the image
  image.classList.add(TAG_CLASS);

  // Create text element
  const textElement = document.createElement("div");
  textElement.style.position = "absolute";
  textElement.style.top = "6%";
  textElement.style.left = "6%";
  textElement.style.maxWidth = "-webkit-fill-available";
  textElement.style.lineHeight = "18px";
  textElement.style.marginRight = "4%";
  textElement.style.fontFamily = "Roboto, Arial, sans-serif";
  textElement.style.color = "rgba(255, 255, 255, 0.9)";
  textElement.style.fontSize = "14px";
  textElement.style.background = "rgba(32, 33, 36, 0.6)";
  textElement.style.padding = "4px 8px 4px 8px";
  textElement.style.borderRadius = "4px";
  textElement.style.boxShadow = "0 0 6px rgba(0, 0, 0, .12)";
  textElement.style.textAlign = "center";
  textElement.style.overflowWrap = "break-word";
  textElement.style.zIndex = "100000";

  // Add event listeners
  textElement.addEventListener("mouseenter", showTag);
  image.addEventListener("mouseover", showTag);
  image.parentElement.addEventListener("mouseover", showTag);
  textElement.addEventListener("click", handleClick);

  // Set initial content
  textElement.innerHTML = "\u{2139}";
  textElement.setAttribute("iscc", record['iscc']);

  // Functions
  function showTag() {
    textElement.style.textAlign = "left";
    textElement.innerHTML = `\u{2139} Content Information<br><hr><b>ISCC:</b> ${state_iscc}<br><b>C2PA:</b> ${state_c2pa}<br><b>AI:</b> ${state_ai}<br>`;
  }

  function handleClick() {
    const iscc = textElement.getAttribute("iscc");
    const url = `http://207.154.225.251:8003/?iscc=${encodeURIComponent(iscc)}&similarity=0.000001`;
    window.open(url, '_blank');
  }

  function hideTag() {
    textElement.innerHTML = "\u{2139}";
    textElement.style.textAlign = "center";
  }

  // Add event listeners for mouseout
  image.addEventListener("mouseout", hideTag);
  image.parentElement.addEventListener("mouseout", hideTag);

  // Append the text element to the image's parent element
  image.parentElement.appendChild(textElement);

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
function handleIntersection(entries, observer) {
  entries.forEach((entry) => {
    if (entry.isIntersecting) {
      const target = entry.target;
      if (target.tagName.toLowerCase() === "img" && !target.classList.contains(PROCESSED_CLASS)) {
        checkImageMetadata(target);
        observer.unobserve(target);
      }
    }
  });
}

// Set up an IntersectionObserver to detect when images become visible as you scroll
const intersectionObserver = new IntersectionObserver((entries, observer) => {
  handleIntersection(entries, observer);
}, {
  threshold: 0.9,
});

// Function to observe images
function observeImages(images) {
  images.forEach((image) => {
    intersectionObserver.observe(image);
  });
}

// Function to find and observe new images on the page
function observeNewImages() {
  const images = document.querySelectorAll("img:not(.image-metadata-processed)");
  observeImages(images);
}

// Initial observation for existing images
observeImages(document.querySelectorAll("img"));

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