package main

import (
	"database/sql"
	"log"
	"math/big"
	"net/http"
	"os"
	"path/filepath"

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

func init() {
	var err error
	// Load env
	err = godotenv.Load("../.env")
	if err != nil {
		log.Fatal("Error loading .env file")
	}

	// Create DB Directory
	dbDir := os.Getenv("DB_DIR")
	err = createDirectoryIfNotExist(dbDir)
	if err != nil {
		log.Fatal("Failed to create a directory", err)
	}

	// Create DB
	dbName := os.Getenv("DB_NAME")
	dbPath := filepath.Join(dbDir, dbName)
	log.Println("dbPath:", dbPath)

	// Open DB
	db, err = sql.Open("sqlite3", dbPath)
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
			source TEXT,
			statements INTEGER
		)
	`)
	if err != nil {
		log.Fatal(err)
	}

	// Create Verifiable DB
	vDbName := os.Getenv("V_DB_NAME")
	vDbPath := filepath.Join(dbDir, vDbName)
	log.Println("vDbPath:", vDbPath)

	// Open DB
	vDb, err = sql.Open("sqlite3", vDbPath)
	if err != nil {
		log.Fatal(err)
	}

	// Create the table if it doesn't exist
	_, err = vDb.Exec(`
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
			source TEXT,
			statements INTEGER
		)
	`)
	if err != nil {
		log.Fatal(err)
	}
}

func main() {
	// Set GIN to release/debug mode
	debug := os.Getenv("DEBUG")
	if debug == "False" {
		gin.SetMode(gin.ReleaseMode)
	}

	// Set GIN
	router := gin.Default()
	router.SetTrustedProxies([]string{"localhost"})

	// Endpoints accessible via localhost
	router.POST("/v1/store", storeHandler)

	host := os.Getenv("STORAGE_HOST_PORT")
	log.Printf("Server listening on: %s...\n", host)
	log.Fatal(router.Run(host))
}

func storeHandler(c *gin.Context) {
	var record Record
	if err := c.ShouldBindJSON(&record); err != nil {
		c.JSON(http.StatusBadRequest, gin.H{"error": "Failed to decode JSON"})
		return
	}

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
	if record.Statements > 0 {
		_, err := vDb.Exec(`
		INSERT INTO records (iscc, hash, instance_code_hex, content_code_hex, data_code_hex, instance_code, content_code, data_code, source, statements)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
	`, record.Iscc, record.Hash, record.InstanceCodeHex, record.ContentCodeHex, record.DataCodeHex, instanceCode, contentCode, dataCode, record.Source, record.Statements)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to store data in the database"})
			log.Println(err)
			return
		}
	}
	result, err := db.Exec(`
		INSERT INTO records (iscc, hash, instance_code_hex, content_code_hex, data_code_hex, instance_code, content_code, data_code, source, statements)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
	`, record.Iscc, record.Hash, record.InstanceCodeHex, record.ContentCodeHex, record.DataCodeHex, instanceCode, contentCode, dataCode, record.Source, record.Statements)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": "Failed to store data in the database"})
		log.Println(err)
		return
	}
	id, _ := result.LastInsertId()

	c.JSON(http.StatusCreated, gin.H{"message": "Data stored", "id": id})
}

func createDirectoryIfNotExist(dirPath string) error {
	// Check if the directory already exists
	_, err := os.Stat(dirPath)
	if os.IsNotExist(err) {
		// Directory doesn't exist, create it
		err := os.MkdirAll(dirPath, os.ModePerm)
		if err != nil {
			return err
		}
		log.Println("Directory created:", dirPath)
	} else if err != nil {
		// Some other error occurred
		return err
	} else {
		// Directory already exists
		log.Println("Directory already exists:", dirPath)
	}
	return nil
}
