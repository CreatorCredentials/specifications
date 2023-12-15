chrome.runtime.onInstalled.addListener(() => {
  console.log('Extension Installed');
});

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'sendImageUrls' && request.imgUrl) {
    // Process image URLs here
    fetchImageBytes(request.imgUrl, request.tabUrl, sendResponse)
    return true;
  }
});

// v3
function fetchImageBytes(url, tabUrl, sendResponse) {
  fetch(url)
    .then(response => response.arrayBuffer())
    .then(async buffer => {
      // Compute SHA-256 hash of the ArrayBuffer
      const hash = await computeArrayBufferSha256(buffer);
      const [ exists, iscc ] = await checkHashExistsOnServer(hash);
      // console.log(hash, exists, iscc);
      if (!exists) {
        // Hash not found, send the ArrayBuffer and hash to the server
        sendBytesToServer(buffer, tabUrl, sendResponse);
      } else {
        // console.log('Hash already exists on the server. Skipping upload.');
        sendResponse({ 'serverResponse': iscc });
      }
    })
    .catch(error => {
      // console.error('Error fetching image:', error);
      sendResponse({ error: 'Error fetching image' });
    });
}

// Function to compute SHA-256 hash of an ArrayBuffer
async function computeArrayBufferSha256(arrayBuffer) {
  const hashBuffer = await crypto.subtle.digest('SHA-256', arrayBuffer);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  const hashHex = hashArray.map(byte => byte.toString(16).padStart(2, '0')).join('');
  return hashHex;
}

// Function to check if hash exists on the server
async function checkHashExistsOnServer(hash) {
  const serverEndpoint = `http://207.154.225.251:8003/v3/records?hash=${hash}`;

  try {
    const response = await fetch(serverEndpoint);
    if (response.ok) {
      let responseData = await response.json()
      // console.log(responseData)
      return [response.ok, responseData.data.iscc]
    }
    return [response.ok, null];
  } catch {
    return [false, null];
  }
}

function arrayBufferToBase64(arrayBuffer) {
  const binaryString = String.fromCharCode.apply(null, new Uint8Array(arrayBuffer));
  return btoa(binaryString);
}

function sendBytesToServer(buffer, tabUrl, sendResponse) {
  const serverEndpoint = 'http://207.154.225.251:8002/v3/iscc';

  // Assuming you have a function or API to send the ArrayBuffer to the server
  // Adjust this function according to your server communication method
  // For example, using fetch to send the ArrayBuffer as FormData
  const formData = new FormData();
  formData.append('url', tabUrl);
  formData.append('image', new Blob([buffer]));

  fetch(serverEndpoint, {
    method: 'POST',
    body: formData,
  })
    .then(response => response.json())
    .then(serverResponse => {
      // console.log('rerver Response:', serverResponse);
      sendResponse({ 'serverResponse': serverResponse['iscc'] });
    })
    .catch(error => {
      // console.error('Error sending base64 image to server:', error);
      sendResponse({ error: error.toString() });
    });
}