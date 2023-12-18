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
      const [exists, record] = await checkHashExistsOnServer(hash);
      console.log("xx", record)
      if (!exists) {
        // Hash not found, send the ArrayBuffer and hash to the server
        sendBytesToServer(buffer, tabUrl, sendResponse);
      } else {
        if (record.statements > 0) {
          sendResponse({ 'serverResponse': record });
        }
        const [exists, records] = await checkSimilarExistsOnServer(record.iscc);
        if (exists) {
          sendResponse({ 'serverResponse': records[0] });
          console.log("I'm new", records)
        } else {
          sendResponse({ error: 'Error fetching metadata' });
        }
      }
    })
    .catch(error => {
      sendResponse({ error: 'Error fetching image:' + error.toString() });
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
      return [responseData.exists, responseData.data]
    }
    return [false, null];
  } catch {
    return [false, null];
  }
}

// Function to check if hash exists on the server
async function checkSimilarExistsOnServer(iscc) {
  const serverEndpoint = `http://207.154.225.251:8003/v4/records?iscc=${iscc}&similarity=0.000001`;
  try {
    const response = await fetch(serverEndpoint);
    if (response.ok) {
      let responseData = await response.json()
      return [responseData.exists, responseData.records]
    }
    return [false, null];
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
    .then(response => {
      console.log(response);
      return response.json()
    }
    )
    .then(serverResponse => {
      // Use the serverResponse as needed
      console.log('server response', serverResponse)

      // Call checkSimilarExistsOnServer with the desired parameter (for example, serverResponse.iscc)
      return checkSimilarExistsOnServer(serverResponse.iscc);
    })
    .then(([exists, records]) => {
      // Process the result of checkSimilarExistsOnServer
      console.log('Exists on server:', exists);
      console.log('Records:', records);
      // Continue with the rest of your code if needed
      if (exists) {
        sendResponse({ 'serverResponse': records[0] });
        console.log("I'm new", records)
      } else {
        sendResponse({ error: 'Error fetching metadata!' });
      }
    })
    .catch(error => {
      console.log("I'm new error", error.toString())
      // Handle any errors in the chain
      sendResponse({ error: error.toString() });
    });

  /*
  fetch(serverEndpoint, {
    method: 'POST',
    body: formData,
  })
    .then(response => response.json())
    .then(serverResponse => {
      sendResponse({ 'serverResponse': serverResponse });
    })
    .catch(error => {
      sendResponse({ error: error.toString() });
    });
    */
}