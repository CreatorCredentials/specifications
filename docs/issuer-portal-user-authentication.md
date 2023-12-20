# Issuer Portal - User Authentication

Organisation representatives must be able to authenticate using their organisational email addresses.

Proposed solution: use a 3rd party IDP and user management system

```mermaid
sequenceDiagram
  actor a as Alice
  participant ip as Issuer Portal
  participant idp as IDP

  title Organisation Member authentication

  autonumber

  a ->> ip: Visit the portal (creatorcredentials.dev)
  a ->> ip: Select "Issuer Portal/Log In"
  ip ->> idp: HTTP 302 with Authorization Request
  a ->> idp: Login with email/password
  idp ->> ip: HTTP 302 state/code
  ip ->> idp: GET /token
  idp ->> ip: ID Token (user info, email, ...)
```

The sequence diagram presents a simple OIDC-based authentication flow. Implementation may differ, depending on the IDP capabilities.

Only email login should be supported since we want users to authenticate with their organisational email addresses. Login with google/twitter/... is not applicable.

After the user is authenticated, it needs to perform domain verification, else we cannot assure the user belongs to the given organisation.

Note: Whether the user has the right to represent the organisation is out of
scope for this version.
