# Setup and configuration

The CC application consists of two main components

- issuer portal
- creator hub

## Issuer portal (IP)

Issuer portal must be support the following capabilities

- [User authentication](./issuer-portal-user-authentication.md) with organisational email
- User verification
  - Email
  - Domain name
  - Wallet
- Credential issuance

### Initialisation

The IP MUST have

- private-public key pair to issue VCs
- did:web

Before deploying the solution, the user must configure

- hostname

#### Key generation and storage

The solution must generate an EC secp256r1 (alternative names: P-256, prime256v1) key pair. Any library supporting ES256 signature should be generate such key pair. The key pair must be accessible to the IP component for the purpose of issuing VCs.

Key can be stored

- plaintext local file with limited access rights
- encrypted local file with limited access rights
  - not recommended at this stage of the project as restarting the service requires manual intervention
- ENV variable
- keystore (google/azure/...)

Suggestion: begin with plaintext local file with limited access rights or .env/ENV

Example using OpenSSL: see the `../examples/gen-unencrypted.sh`

#### did:web