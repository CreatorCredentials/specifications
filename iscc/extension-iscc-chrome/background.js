chrome.runtime.onInstalled.addListener(() => {
  console.log('Extension Installed');
});

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'sendImageUrls' && request.imgUrl) {
    // Process image URLs here
    // console.log(request)
    // console.log('Received image URLs:', request.imgUrl);
    fetchImageBytes(request.imgUrl, request.tabUrl, sendResponse)
    return true;
  }
//   if (request.action === 'fetchImageBytes') {
// 	console.log("hi1")
//     chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
// 	console.log("hi2")
//       const activeTab = tabs[0];
//       if (activeTab) {
// 	console.log("hi3", activeTab.id)
//         chrome.tabs.sendMessage(activeTab.id, { action: 'getActiveTabUrl' }, (response) => {
// 	console.log("hi4", response)
//           if (response && response.url) {
// 	console.log("hi5")
//             console.log(fetchImageBytes(response.url, sendResponse));
//           } else {
//             sendResponse({ error: 'Unable to get active tab URL' });
//           }
//         });
//       } else {
//         sendResponse({ error: 'No active tab found' });
//       }
//     });
//     return true; // Keeps the message channel open for asynchronous responses
//   } else {
//     sendResponse({ error: 'Invalid message' });
//   }
});

function fetchImageBytes(url, tabUrl, sendResponse) {
  fetch(url)
    .then(response => response.arrayBuffer())
    .then(buffer => {
      imageb64 = arrayBufferToBase64(buffer)
      // console.log(imageb64)
      sendBase64ToServer(imageb64, tabUrl, sendResponse)
      // sendResponse({ imageBytes });
    })
    .catch(error => {
      console.error('Error fetching image:', error);
      sendResponse({ error: 'Error fetching image' });
    });
}

function arrayBufferToBase64(arrayBuffer) {
  const binaryString = String.fromCharCode.apply(null, new Uint8Array(arrayBuffer));
  return btoa(binaryString);
}

function sendBase64ToServer(base64Image, tabUrl, sendResponse) {
  // const serverEndpoint = 'http://207.154.225.251:3000/metadata';
  // const serverEndpoint = 'http://207.154.225.251:3000/v1/iscc';
  const serverEndpoint = 'http://207.154.225.251:3000/v2/iscc';

  fetch(serverEndpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ 'image': base64Image, "site_url": tabUrl }),
  })
    .then(response => response.json())
    .then(serverResponse => {
      console.log('rerver Response:', serverResponse);
      sendResponse({ 'serverResponse': serverResponse['iscc'] });
    })
    .catch(error => {
      console.error('Error sending base64 image to server:', error);
      // sendResponse({ error: 'Error sending base64 image to server' });
    });
}
