# Decentralised identifiers

## did:web for the Issuer Portal

The IP MUST support did:web.

- Generate a DID Document with public keys of the IP
- [DID Document example](./examples/issuer-portal-did.json) of an IP
  - DID Document MUST contain at least one public key: in this version we'll have only 1 public key
  - DID Document MAY contain authentication
  - DID Document MUST contain assertionMethod
    - MUST reference the key that's used to sign VCs (email/wallet/domain verification)
- DID Document MUST be stored in did.json file under: creatorcredentials.dev/.well-known/did.json
  - Response header: content-type: application/did+ld+json

## did:web for Issuers

- WIP

## Legal entity decentralised identifiers

Legal entities MUST set up their Decentralised Identifier (DID). Supported DID:

- did:web

DID can be self-hosted or hosted by the platform. We're using the following convention

- did:web:{domain.name} for self-hosted DIDs
- did:web:creatorcredentials.cc:{domain.name.issuer} - specific to {creatorcredentials.cc}
- did:web:{domain.name.host}:{domain.name.issuer} - generic schema

If DID is hosted, it is recommended to include the alsoKnownAs property in the DID document that is referencing the website of the entity. If entity is owner of multiple domains, all of them can be listed under the alsoKnownAs.

To create a reciprocal relationship, at least TXT DNS record should be set:

- did:web:{domain.name}?challenge={random.challenge}

If the relationship is not reciprocal, the relationship should not be trusted.

### Resolution

did:web is resolved at

- did:web:{domain.name} resolves to: <https://domain.name/.well-known/did.json>
- did:web:{domain.name}:{path} resolves to: <https://domain.name/path/did.json>

## Policies

- Keys in the DID Document MUST be considered valid
- Key rotation is performed by updating the DID Document
- Historical key resolutions must be possible using `versionTime` [DID query parameter](https://w3c.github.io/did-core/#did-parameters)
- [advanced] Key rotation with logs
- [advanced] DID Document update logs/proofs
- [advanced] Keys can be suspended or revoked by suspending/revoking the public key attestations

## Public key attestations (advanced)

Public key attestation is a verifiable credential attesting the quality and security of a given public-private key pair.

TODO: Data model

## References

- [w3c did:web](https://w3c-ccg.github.io/did-method-web/)

## Experimental

### w3id.org

Proposal

- {https://w3id.org/PROJECT-ID/SUB-ID} -> {DID}
