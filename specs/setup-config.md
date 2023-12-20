# Setup and configuration

- [Setup and configuration](#setup-and-configuration)
  - [Host](#host)
  - [Initialisation](#initialisation)
  - [Host private-public key generation and storage](#host-private-public-key-generation-and-storage)
  - [Instructions for hosts](#instructions-for-hosts)
    - [How to configure](#how-to-configure)
    - [How to deploy](#how-to-deploy)

In CC we have three roles

- Host - entity that hosts the application
  - Signs/issues Verification VCs to Issuers and Creators
  - Owns host.com (for creatorcredential.dev replace host.com with creatorcredentials.dev)
  - Has did:web hosted at: host.com/.well-known/did.json
    - did:web contains information about all host public keys: can be simple JWK key, or a Q-Cert

- Issuer - entity that uses the Issuer Portal
  - Requests/Receives VCs from the Host
  - Owns issuer.com
  - Signs/Issues VCs to Creators
  - Has did:web hosted at: issuer.com/.well-known/did.json
    - did:web contains information about all host public keys: can be simple JWK key, or a Q-Cert

    - DNS TXT record/Domain Verification is NOT required

- Creator - entity that uses the Creator Hub
  - Requests/Receives VCs from the Host
  - Requests/Receives VCs from Issuers
  - Has did:key (did:ethr/...)

## Host

Host must be support the following capabilities

- [Issuer Authentication](./host-issuer-authenticaiton.md) with organisational email
- Perform Issuer verification
  - did:web
- Issue Verification VC to issuers

## Initialisation

The Host MUST

- have private-public key pair to sign and issue Verification VCs

Host did:web is set up automatically with the service.

Before deploying the solution, the host must configure

- hostname (host.com)
- key storage location
- database location
- other (to be updated)

TODO: define how to configure the solution

## Host private-public key generation and storage

The host application must generate an EC secp256r1 (alternative names: P-256, prime256v1) key pair. Any [library](https://jwt.io/libraries) supporting ES256 signature should be capable of generating such a key pair. The key pair must be accessible to the host application for the purpose of issuing Verification VCs.

The private key can be stored

- plaintext local file with limited access rights
- ENV variable
- secure keystore (AWS/Google/Azure/...)

- encrypted local file with limited access rights
  - not recommended at this stage of the project as restarting the service requires manual intervention

Suggestion: begin with plaintext local file with limited access rights or .env/ENV

Example using OpenSSL: see the [examples/gen-unencrypted.sh](./examples/gen-unencrypted.sh)

## Instructions for hosts

### How to configure

TBD

### How to deploy

TBD
