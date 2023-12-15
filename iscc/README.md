# Configurations

## Global

ROOT_DIR=./
DB_DIR=${ROOT_DIR}/storage
DB_NAME=database-v1.db
ASSETS_DIR=${ROOT_DIR}/assets
ASSETS_CSS_DIR=${ASSETS_DIR}/css
ASSETS_C2PA_DIR=${ASSETS_DIR}/c2pa
ASSETS_THUMBNAILS_DIR=${ASSETS_DIR}/images

STORAGE_API=localhost:8000
  - post_store=/v1/store
C2PA_API=localhost:8001
  - post_c2pa=/v1/c2pa
ISCC_API=localhost:8002
  - post_explain=/v2/explain
  - post_iscc=/v3/iscc
REGISTRY_API=localhost:8003
  - index=/
  - assets=/assets
  - records=/v3/records

Each service comes with .well-known


## backend -> storage-api

**Offers**

- ./database.db
- POST localhost:8080/v1/store -> storage-api.store-endpoint = localhost:8080/v1/store

## c2pa-api

**Offers**

- ./c2pa-store -> should be available under /assets/c2pa-store
- POST localhost:3000/v1/c2pa

## iscc-sdk -> iscc-api

Offers: 

- IMG_PATH = "/home/alen/repo-iscc/server-db/static/img/" -> should be under /assets/thumbnails
- DECIMAL_PLACES = 20
- POST /v2/explain
- POST /v3/iscc -> POST images?

Requires:

- DB_URL = "http://localhost:8080/store" -> should match storage-api.store-endpoint

## server-db -> registry-api

offers:

- GET / (index.html)
- GET /assets
- GET /v3/records

requires:

- iscc-api.explain