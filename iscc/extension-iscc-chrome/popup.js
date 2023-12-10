document.addEventListener('DOMContentLoaded', function () {

  // Function to handle selector change
  function handleSelectorChange() {
    console.log('handle change')
    // Get the selected value from the selector
    const selectedOption = document.getElementById('endpointSelector').value;

    // Update the current server endpoint display
    document.getElementById('currentEndpoint').textContent = getServerEndpoint(selectedOption);
  }

  // Add an event listener to the selector
  document.getElementById('endpointSelector').addEventListener('change', handleSelectorChange);

  // Function to get the server endpoint based on the selected option
  function getServerEndpoint(selectedOption) {
    if (selectedOption === 'original') {
      return 'http://207.154.225.251:3000/v1/iscc';
    } else if (selectedOption === 'new') {
      // Change this URL to the desired endpoint for "new"
      return 'http://207.154.225.251:3000/metadata';
    }

    // Default to the original endpoint if the option is not recognized
    return 'http://207.154.225.251:3000/v1/iscc';
  }

  // Initialize the current server endpoint display on extension startup
  document.getElementById('currentEndpoint').textContent = getServerEndpoint('original');


  document.getElementById('fetchImage').addEventListener('click', function () {
    chrome.runtime.sendMessage({ action: 'fetchImageBytes' }, function (response) {
      if (response && response.imageBytes) {
        console.log('Fetched Image Bytes:', response.imageBytes);
        // Handle the image bytes as needed
      } else {
        console.error('Error fetching image bytes');
      }
    });
  });
});

