package main

import (
	"bytes"
	"fmt"
	"io"
	"mime/multipart"
	"net/http"
	"os"
)

func uploadFile(filePath string, endpointURL string) error {
	// Open the file
	file, err := os.Open(filePath)
	if err != nil {
		return err
	}
	defer file.Close()

	// Create a buffer to store the file content
	var bodyBuf bytes.Buffer

	// Create a multipart writer to create the form data
	writer := multipart.NewWriter(&bodyBuf)

	// Create a form file field
	part, err := writer.CreateFormFile("file", file.Name())
	if err != nil {
		return err
	}

	// Copy the file content to the form field
	_, err = io.Copy(part, file)
	if err != nil {
		return err
	}

	// Close the multipart writer to finalize the form data
	writer.Close()

	// Create a POST request to the specified endpoint
	request, err := http.NewRequest("POST", endpointURL, &bodyBuf)
	if err != nil {
		return err
	}

	// Set the content type header for the form data
	request.Header.Set("Content-Type", writer.FormDataContentType())

	// Perform the request
	client := &http.Client{}
	response, err := client.Do(request)
	if err != nil {
		return err
	}
	defer response.Body.Close()

	// Print the response status and body
	fmt.Println("Response Status:", response.Status)
	buf := new(bytes.Buffer)
	buf.ReadFrom(response.Body)
	fmt.Println("Response Body:", buf.String())

	return nil
}

func main() {
	if len(os.Args) != 3 {
		fmt.Println("Usage: go run main.go <file-path> <endpoint-url>")
		return
	}

	filePath := os.Args[1]
	endpointURL := os.Args[2]

	err := uploadFile(filePath, endpointURL)
	if err != nil {
		fmt.Println("Error:", err)
	}
}

