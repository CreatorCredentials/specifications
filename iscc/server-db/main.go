package main

import (
	"bytes"
	"database/sql"
	"encoding/json"
	"fmt"
	"io/ioutil"
	"log"
	"math"
	"math/big"
	"net/http"
	"text/template"
	"strconv"
	"strings"

	"github.com/gin-gonic/gin"
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
}

var db *sql.DB

var tpl *template.Template

func init() {
	tpl = template.Must(template.ParseFiles("template/index.html"))
	var err error
	db, err = sql.Open("sqlite3", "./database.db")
	if err != nil {
		log.Fatal(err)
	}

	// Create the table if it doesn't exist
	_, err = db.Exec(`
		CREATE TABLE IF NOT EXISTS records (
			id INTEGER PRIMARY KEY AUTOINCREMENT,
			iscc TEXT,
			hash TEXT,
			instance_code_hex TEXT,
			content_code_hex TEXT,
			data_code_hex TEXT,
			instance_code REAL,
			content_code REAL,
			data_code REAL,
			source TEXT
		)
	`)
	if err != nil {
		log.Fatal(err)
	}
}

func main() {
	router := gin.Default()
	// Serve static files (styles.css in this case)
	router.Static("/static", "./static")

	router.LoadHTMLGlob("template/*")

	router.GET("/", func(c *gin.Context) {
		c.HTML(http.StatusOK, "index.html", nil)
	})

	router.POST("/store", storeHandler)
	router.GET("/retrieve/:iscc", retrieveHandler)
	router.GET("/getInfo", getInfoHandlerV2)

	port := "8080" // Default port

	log.Printf("Server listening on :%s...\n", port)
	log.Fatal(router.Run("0.0.0.0:" + port))

}

func hexToDecimal(hexValue string) (*big.Int, bool) {
	decimalValue, success := new(big.Int).SetString(hexValue, 16)
	if !success {
		log.Fatal("Failed to convert hexadecimal to decimal")
	}

	// Check if the decimal value is within the range of a signed 64-bit integer
	minInt64 := big.NewInt(math.MinInt64)
	maxInt64 := big.NewInt(math.MaxInt64)

	if decimalValue.Cmp(minInt64) >= 0 && decimalValue.Cmp(maxInt64) <= 0 {
		fmt.Printf("The decimal value %s fits within the range of a signed 64-bit integer.\n", decimalValue.String())
	} else {
		fmt.Printf("The decimal value %s does not fit within the range of a signed 64-bit integer.\n", decimalValue.String())
	}

	return decimalValue, success
}

func storeHandler(c *gin.Context) {
	var record Record
	if err := c.ShouldBindJSON(&record); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Failed to decode JSON"})
		return
	}

	fmt.Println(record)
	_instanceCode, success := new(big.Float).SetString(record.InstanceCodeLog)
	if !success {
		log.Println("[Error] Float conversion failed")
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Float conversion failed. Instance code"})
		return
	}
	instanceCode, _ := _instanceCode.Float64()
	_contentCode, success := new(big.Float).SetString(record.ContentCodeLog)
	if !success {
		log.Println("[Error] Float conversion failed")
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Float conversion failed. Content code"})
		return
	}
	contentCode, _ := _contentCode.Float64()
	_dataCode, success := new(big.Float).SetString(record.DataCodeLog)
	if !success {
		log.Println("[Error] Float conversion failed")
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Float conversion failed. Content code"})
		return
	}
	dataCode, _ := _dataCode.Float64()
	// Insert the record into the database
	_, err := db.Exec(`
		INSERT INTO records (iscc, hash, instance_code_hex, content_code_hex, data_code_hex, instance_code, content_code, data_code, source)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
	`, record.Iscc, record.Hash, record.InstanceCodeHex, record.ContentCodeHex, record.DataCodeHex, instanceCode, contentCode, dataCode, record.Source)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to store data in the database"})
		log.Println(err)
		return
	}

	c.JSON(http.StatusCreated, gin.H{"message": "Data stored successfully"})
}

func retrieveHandler(c *gin.Context) {
	iscc := c.Param("iscc")
	fmt.Println(iscc)

	var record Record
	err := db.QueryRow(`
		SELECT iscc, hash, instance_code_hex, content_code_hex, data_code_hex,instance_code, content_code, data_code, source
		FROM records
		WHERE iscc = ?
	`, iscc).Scan(&record.Iscc, &record.Hash, &record.InstanceCodeHex, &record.ContentCodeHex, &record.DataCodeHex, &record.InstanceCodeLog, &record.ContentCodeLog, &record.DataCodeLog, &record.Source)

	if err != nil {
		fmt.Println(err)
		c.JSON(http.StatusNotFound, gin.H{"error": "Record not found"})
		return
	}

	c.JSON(http.StatusOK, record)
}

func getInfoHandler(c *gin.Context) {
	isccCode := c.Query("isccCode")
	similarityFactor := c.Query("similarityFactor")

	fmt.Println(isccCode, similarityFactor)

	var record Record
	err := db.QueryRow(`
		SELECT iscc, hash, source
		FROM records
		WHERE iscc = ?
	`, isccCode).Scan(&record.Iscc, &record.Hash, &record.Source)

	c.JSON(http.StatusOK, []Record{record})

	if err != nil {
		fmt.Println(err)
		c.JSON(http.StatusNotFound, gin.H{"error": "Record not found"})
		return
	}
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

func ExplainISCC(isccCode string) ([]ExplainResponse, error) {
	explainEndpoint := "http://localhost:3000/v2/explain" // replace with your FastAPI server URL
	
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

func getInfoHandlerV2(c *gin.Context) {
	isccCode := c.Query("isccCode")
	similarityFactor := c.Query("similarityFactor")
	fmt.Println(isccCode, similarityFactor)
	targetValue, err := strconv.ParseFloat(similarityFactor, 64)
	if err != nil {
		log.Println(err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
	}
	isccExplained, err := ExplainISCC(isccCode)
	if err != nil {
		log.Println(err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
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
	    SELECT iscc, hash, instance_code_hex, content_code_hex, data_code_hex, instance_code, content_code, data_code, source
	    FROM records
	    WHERE ABS(content_code-?)/? < ?
	    LIMIT 11
	`

	rows, err := db.Query(query, contentCode, contentCode, targetValue)
	if err != nil {
		log.Fatal(err)
	}
	defer rows.Close()

	var records []Record

	// Process the result set
	for rows.Next() {
		var record Record
		err := rows.Scan(&record.Iscc, &record.Hash, &record.InstanceCodeHex, &record.ContentCodeHex, &record.DataCodeHex, &record.InstanceCodeLog, &record.ContentCodeLog, &record.DataCodeLog, &record.Source)
		if err != nil {
			log.Fatal(err)
			c.JSON(http.StatusInternalServerError, gin.H{"error": "Internal Server Error"})
			return
		}
		records = append(records, record)
	}

	// Check for errors from iterating over rows
	if err := rows.Err(); err != nil {
		log.Fatal(err)
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Internal Server Error"})
		return
	}

	c.JSON(http.StatusOK, records)
}
