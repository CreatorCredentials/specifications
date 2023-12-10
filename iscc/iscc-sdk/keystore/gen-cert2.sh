#!/bin/bash

# openssl req -new -newkey rsa:4096 -sigopt rsa_padding_mode:pss -days 3650 -extensions usr_cert -addext "keyUsage = digitalSignature" -addext "extendedKeyUsage = emailProtection" -nodes -x509 -sha256 -keyout private3.key -out certs3.pem

# Generate EC parameters
openssl ecparam -name secp256r1 -out ec_params.pem

SUBJECT="/C=SI/ST=SI/L=Ljubljana/O=Alen Horvat/OU=FOR TESTING_ONLY/CN=C2PA Issuer"
# Generate EC key and self-signed certificate
openssl req -new -newkey ec:ec_params.pem -nodes -x509 -sha256 -keyout private3.key -out certs3.pem -days 3650 -subj "${SUBJECT}" -extensions usr_cert -addext "keyUsage = digitalSignature" -addext "extendedKeyUsage = emailProtection"

