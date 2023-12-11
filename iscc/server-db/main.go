package main

import (
	"database/sql"
	"fmt"
	"log"
	"math"
	"math/big"
	"net/http"

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

func init() {
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

	router.POST("/store", storeHandler)
	router.GET("/retrieve/:iscc", retrieveHandler)
	// router.GET("/range", rangeHandler)

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
