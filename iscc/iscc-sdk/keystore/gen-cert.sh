#!/bin/bash

rm *pem *srl *csr

# Define variables
ROOT_CA_KEY=root_ca.key.pem
ROOT_CA_CERT=root_ca.crt.pem
INTERMEDIATE_CA_KEY=intermediate_ca.key.pem
INTERMEDIATE_CA_CSR=intermediate_ca.csr
INTERMEDIATE_CA_CERT=intermediate_ca.crt.pem
SERVER_KEY=server.key.pem
SERVER_CSR=server.csr
SERVER_CERT=server.crt.pem
SIGNING_CERT_CHAIN=server.chain.pem

# Generate Root CA key and self-signed certificate
ROOT_CA_SUBJECT="/C=SI/ST=SI/L=Ljubljana/O=C2PA Root CA/OU=FOR TESTING_ONLY/CN=C2PA Root Signer"
openssl ecparam -name secp256r1 -genkey -out "$ROOT_CA_KEY"
openssl req -new -x509 -key "$ROOT_CA_KEY" -out "$ROOT_CA_CERT" -days 365 -subj "${ROOT_CA_SUBJECT}"

# Generate Intermediate CA key
openssl ecparam -name secp256r1 -genkey -out "$INTERMEDIATE_CA_KEY"

# Generate Intermediate CA CSR
INT_CA_SUBJECT="/C=SI/ST=SI/L=Ljubljana/O=C2PA Intermediate CA/OU=FOR TESTING_ONLY/CN=C2PA Intermediate Signer"
openssl req -new -key "$INTERMEDIATE_CA_KEY" -out "$INTERMEDIATE_CA_CSR" -subj "${INT_CA_SUBJECT}"

# Sign Intermediate CA CSR with Root CA
openssl x509 -req -in "$INTERMEDIATE_CA_CSR" -CA "$ROOT_CA_CERT" -CAkey "$ROOT_CA_KEY" -CAcreateserial -out "$INTERMEDIATE_CA_CERT" -days 365

# Generate Server key
openssl ecparam -name secp256r1 -genkey -out "$SERVER_KEY"

# Generate Server CSR
ISSUER_CA_SUBJECT="/C=SI/ST=SI/L=Ljubljana/O=C2PA Issuer/OU=FOR TESTING_ONLY/CN=C2PA Issuer"
openssl req -new -key "$SERVER_KEY" -out "$SERVER_CSR" -subj "${ISSUER_CA_SUBJECT}" -extensions usr_cert -addext "keyUsage = digitalSignature" -addext "extendedKeyUsage = emailProtection"

# openssl req -new -newkey rsa:4096 -sigopt rsa_padding_mode:pss -days 3650 -extensions usr_cert -addext "keyUsage = digitalSignature" -addext "extendedKeyUsage = emailProtection" -nodes -x509 -sha256 -keyout private3.key -out certs3.pem
# Sign Server CSR with Intermediate CA
openssl x509 -req -in "$SERVER_CSR" -CA "$INTERMEDIATE_CA_CERT" -CAkey "$INTERMEDIATE_CA_KEY" -CAcreateserial -out "$SERVER_CERT" -days 365

# Create PEM certificate chain
cat "$SERVER_CERT" "$INTERMEDIATE_CA_CERT" "$ROOT_CA_CERT" > "$SIGNING_CERT_CHAIN"

echo "Certificate chain generated successfully."

