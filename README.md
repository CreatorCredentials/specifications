# CreatorCredentials <!-- omit in toc -->

- [Getting started (wip)](#getting-started-wip)
  - [Build](#build)
  - [Configure](#configure)
  - [Deploy](#deploy)
- [Profile](#profile)
- [Technical Specifications (wip)](#technical-specifications-wip)
  - [Host](#host)
  - [Issuer](#issuer)
  - [Creator](#creator)
  - [Data models and schemas](#data-models-and-schemas)
  - [Advanced topics](#advanced-topics)
- [Reference](#reference)


CreatorCredentials is an application for media organisations to issue Verifiable
Credentials to creators.

## Getting started (wip)

### Build

In this section, we summarise how to build the CreatorCredentials app.

### Configure

In this section, we summarise how to configure the CreatorCredentials app.

### Deploy

In this section, we summarise how to deploy the CreatorCredentials app.

## Profile

The Creator Credentials (CC) Verifiable Credentials (VC) profile follows the [EBSI](https://ebsi.eu) specifications. Details of the profile are defined [here](specs/profile.md).

## Technical Specifications (wip)

### Host

- How to set up and configure the CC app?: [specs/host-setup-config.md](specs/host-setup-config.md)
- How to configure host's DID (did:web)?: [specs/host-did.md](specs/host-did.md)
- How to authenticate the issuers?: [specs/host-issuer-authentication.md](specs/host-issuer-authentication.md)

### Issuer

- [How to configure and verify issuer's did:web?](specs/issuer-did.md)

### Creator

- [Creator email Verification](specs/creator-email-verification.md)

### Data models and schemas

- [JSON Schema and examples of Verification VCs](json-schema/verification-credentials/)

### Advanced topics

- [Creator logs in using its Creator Credentials](specs/advanced/log-in-with-cc.md)

## Reference

- <https://w3c-ccg.github.io/did-method-web/#example-creating-the-did-with-optional-path>
- <https://aws.amazon.com/kms/>
- <https://jwt.io/>
