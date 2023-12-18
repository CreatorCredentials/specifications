package main

import (
	"bytes"
	"database/sql"
	"encoding/json"
	"fmt"
	"io/ioutil"
	"log"
	"net/http"
	"net/url"
	"os"
	"path/filepath"
	"strconv"
	"strings"

	"github.com/gin-gonic/gin"
	"github.com/joho/godotenv"
	_ "github.com/mattn/go-sqlite3"
)

// Record represents the structure of the JSON data
type Record struct {
	Iscc            string `json:"iscc"`
	Hash            string `json:"hash"`
	InstanceCodeHex string `json:"instance-code-hex"`
	ContentCodeHex  string `json:"content-code-hex"`
	DataCodeHex     string `json:"data-code-hex"`
	InstanceCodeLog string `json:"instance-code-log"`
	ContentCodeLog  string `json:"content-code-log"`
	DataCodeLog     string `json:"data-code-log"`
	Source          string `json:"source"`
	Statements      int    `json:"statements"`
}

var db *sql.DB
var vDb *sql.DB
var explainEndpoint string

func init() {
	// Load env
	err := godotenv.Load("../.env")
	if err != nil {
		log.Fatal("Error loading .env file")
	}
	schema := os.Getenv("ISCC_SCHEMA")
	hostPort := os.Getenv("ISCC_HOST_PORT")
	endpoint := os.Getenv("ISCC_API_POST_EXPLAIN")

	explainEndpoint, err = joinURL(schema, hostPort, endpoint)
	if err != nil {
		log.Fatal(err)
	}

}

func main() {

	// Load DB info
	dbDir := os.Getenv("DB_DIR")
	dbName := os.Getenv("DB_NAME")
	dbPath := filepath.Join(dbDir, dbName)
	log.Println("dbPath:", dbPath)

	vDbName := os.Getenv("V_DB_NAME")
	vDbPath := filepath.Join(dbDir, vDbName)

	// Connection URL for SQLite in read-only mode
	// connectionURL := fmt.Sprintf("file:%s?mode=ro", dbPath)

	// Open a connection to the SQLite database
	var err error
	db, err = sql.Open("sqlite3", dbPath)
	if err != nil {
		fmt.Println("Error opening the database:", err)
		return
	}
	defer db.Close()
	vDb, err = sql.Open("sqlite3", vDbPath)
	if err != nil {
		fmt.Println("Error opening the database:", err)
		return
	}
	defer vDb.Close()

	// Set GIN to release/debug mode
	debug := os.Getenv("DEBUG")
	if debug == "False" {
		gin.SetMode(gin.ReleaseMode)
	}

	hostPort := os.Getenv("REGISTRY_HOST_PORT")

	router := gin.Default()
	router.LoadHTMLGlob("template/*")

	// Serve static files (styles.css in this case)
	// TODO: get ./static from a config file
	assetsDir := os.Getenv("ASSETS_DIR")
	router.Static("/assets", assetsDir)

	// Serve the HTML website
	router.GET("/", func(c *gin.Context) {
		c.HTML(http.StatusOK, "index.html", nil)
	})

	// Handle /v3/records/:iscc
	router.GET("/v3/records/:iscc", getRecordsIsccV3)

	// Handle /records?digest={hex sha256 digest-value}
	router.GET("/v3/records", getRecordsFilterV3)

	// Handle /records?digest={hex sha256 digest-value}
	router.GET("/v4/records", getRecordsFilterV4)

	log.Printf("Server listening on :%s...\n", hostPort)
	log.Fatal(router.Run(hostPort))
}

func getRecordsFilterV3(c *gin.Context) {
	hash := c.Query("hash")
	isccValue := c.Query("iscc")
	similarity := c.Query("similarity")

	switch {
	case hash != "":
		// Case: /records?hash={hash-value}
		getRecordsByDigestV3(c)
	case isccValue != "" && similarity != "":
		// Case: /records?iscc={iscc-value}&similarity={similarity-factor}
		getRecordsBySimilarityV3(c)
	default:
		c.JSON(http.StatusBadRequest, gin.H{"error": "Invalid request"})
	}
}

func getRecordsFilterV4(c *gin.Context) {
	getSimilarByIsccV1(c)
}

func getSimilarByIsccV1(c *gin.Context) {
	iscc := c.Query("iscc")
	similarity := c.Query("similarity")
	records, err := getSimilar(iscc, similarity)
	// Check for errors from iterating over rows
	if err != nil {
		log.Println(err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Internal Server Error"})
		return
	}
	c.JSON(http.StatusOK, gin.H{"exists": true, "records": records})
}

func getRecordsByDigestV3(c *gin.Context) {
	hash := c.Query("hash")
	log.Println(hash)

	var record Record
	err := db.QueryRow(`
		SELECT iscc, hash, statements
		FROM records
		WHERE hash = ?
	`, hash).Scan(&record.Iscc, &record.Hash, &record.Statements)

	if err != nil {
		if err == sql.ErrNoRows {
			// Hash does not exist
			c.JSON(http.StatusNotFound, gin.H{"exists": false, "error": "Not Found"})
		} else {
			// Handle other errors
			fmt.Println(err)
			c.JSON(http.StatusInternalServerError, gin.H{"exists": false, "error": "Internal Server Error"})
		}
		return
	}

	// Hash exists
	c.JSON(http.StatusOK, gin.H{"exists": true, "data": record})
}

func getRecordsIsccV3(c *gin.Context) {
	iscc := c.Param("iscc")
	fmt.Println(iscc)

	var record Record
	err := db.QueryRow(`
		SELECT iscc, hash, instance_code_hex, content_code_hex, data_code_hex,instance_code, content_code, data_code, source, statements
		FROM records
		WHERE iscc = ?
	`, iscc).Scan(&record.Iscc, &record.Hash, &record.InstanceCodeHex, &record.ContentCodeHex, &record.DataCodeHex, &record.InstanceCodeLog, &record.ContentCodeLog, &record.DataCodeLog, &record.Source, &record.Statements)

	if err != nil {
		fmt.Println(err)
		c.JSON(http.StatusNotFound, gin.H{"error": "Record not found"})
		return
	}

	c.JSON(http.StatusOK, record)
}

type ExplainRequest struct {
	Iscc string `json:"iscc"`
}

type ExplainResponse struct {
	Readble string `json:"readable"`
	Iscc    string `json:"iscc"`
	Hex     string `json:"hex"`
	Log     string `json:"log"`
}

func joinURL(schema, hostPort, endpoint string) (string, error) {
	// Construct the base URL
	baseURL := &url.URL{
		Scheme: schema,
		Host:   hostPort,
	}

	// Parse the endpoint and resolve it against the base URL
	endpointURL, err := url.Parse(endpoint)
	if err != nil {
		return "", err
	}

	// Join the base URL and the resolved endpoint
	completeURL := baseURL.ResolveReference(endpointURL)

	return completeURL.String(), nil
}

func ExplainISCC(isccCode string) ([]ExplainResponse, error) {
	// Create an ExplainRequest struct
	explainRequest := ExplainRequest{
		Iscc: isccCode,
	}

	// Convert ExplainRequest to JSON
	jsonBody, err := json.Marshal(explainRequest)
	if err != nil {
		fmt.Println("Error marshalling JSON:", err)
		return nil, err
	}

	// Make POST request
	resp, err := http.Post(explainEndpoint, "application/json", bytes.NewBuffer(jsonBody))
	if err != nil {
		fmt.Println("Error making POST request:", err)
		return nil, err
	}
	defer resp.Body.Close()

	// Read the response body
	body, err := ioutil.ReadAll(resp.Body)
	if err != nil {
		fmt.Println("Error reading response body:", err)
		return nil, err
	}

	// Parse the JSON response
	var explainResponses []ExplainResponse
	if err := json.Unmarshal(body, &explainResponses); err != nil {
		fmt.Println("Error parsing JSON response:", err)
		return nil, err
	}
	return explainResponses, nil

}

func getRecordsBySimilarityV3(c *gin.Context) {
	isccCode := c.Query("iscc")
	similarityFactor := c.Query("similarity")

	records, err := getSimilar(isccCode, similarityFactor)

	// Check for errors from iterating over rows
	if err != nil {
		log.Println(err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Internal Server Error"})
		return
	}

	c.JSON(http.StatusOK, records)
}
func getSimilar(isccCode, similarityFactor string) ([]Record, error) {
	fmt.Println(isccCode, similarityFactor)
	targetValue, err := strconv.ParseFloat(similarityFactor, 64)
	if err != nil {
		log.Println(err)
		return nil, err
	}
	isccExplained, err := ExplainISCC(isccCode)
	if err != nil {
		log.Println(err)
		return nil, err
	}
	// Loop through the ExplainResponse slice
	var contentCode string
	for _, response := range isccExplained {
		// Check if Readable starts with "CONTENT"
		if strings.HasPrefix(response.Readble, "CONTENT") {
			contentCode = response.Log
		}
	}

	query := `
	    SELECT iscc, hash, instance_code_hex, content_code_hex, data_code_hex, instance_code, content_code, data_code, source, statements
	    FROM records
	    WHERE ABS(content_code-?)/? < ?
	    LIMIT 11
	`
	rows, err := vDb.Query(query, contentCode, contentCode, targetValue)
	if err != nil {
		log.Println(err)
		return nil, err
	}
	defer rows.Close()

	var records []Record

	// Process the result set
	for rows.Next() {
		var record Record
		err := rows.Scan(&record.Iscc, &record.Hash, &record.InstanceCodeHex, &record.ContentCodeHex, &record.DataCodeHex, &record.InstanceCodeLog, &record.ContentCodeLog, &record.DataCodeLog, &record.Source, &record.Statements)
		if err != nil {
			log.Println(err)
			return nil, err
		}
		records = append(records, record)
	}

	return records, err
}
