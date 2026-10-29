# Planned changes (change requests, October 2026)

This document tracks change requests raised against the system described in
`specs/01`–`10`. Those documents describe the code **as it is**; nothing here
is implemented unless its status says so. Each request records the problem,
the decision (or the open questions), the design, and the acceptance
criteria. When a request ships, fold its design into the reference docs and
mark it *Shipped* here.

| ID | Title | Status | Decided |
|---|---|---|---|
| [CR-1](#cr-1-revocation-of-issuer-issued-credentials) | Revocation of issuer-issued credentials (status instead of deletion) | **Decided** | 2026-10-28 |
| [CR-2](#cr-2-issued-credentials-page-search-and-creator-identity) | Issued-credentials page: search, full e-mail, creator identity in the API | **Decided** (assumed defaults) | 2026-10-28 |
| [CR-3](#cr-3-e-mail-notifications) | E-mail notifications (sign-ups, connection requests, VC requests) | **Decided** (assumed defaults) | 2026-10-28 |
| [CR-4](#cr-4-verifiablecreator-credential) | `VerifiableCreator` credential | **Decided** (assumed defaults) | 2026-10-28 |
| [CR-5](#cr-5-security-and-hygiene-fixes) | Security and hygiene fixes found during the audit | **Decided** | 2026-10-28 |
| [CR-6](#cr-6-admin-role-and-admin-panel) | Admin role and admin panel (view, download, revoke; never sign) | **Decided** | 2026-10-29 |
| [CR-7](#cr-7-revocation-list-and-credential-verification) | Revocation list (W3C Bitstring Status List) and `POST /credentials/verify` | **Decided** | 2026-10-29 |

Source of CR-1–CR-4: client notes received 2026-10-28. Source of CR-5: code
audit of `creator-credentials-backend` and `creator-credentials-ui` on the
same date. "Assumed defaults" marks decisions taken by the maintainer on
2026-10-28 to unblock implementation; each lists what to confirm with the
client and what changes if the answer differs. The [test plan](#test-plan)
and the [implementation status](#implementation-status) are at the end.

---

## CR-1 Revocation of issuer-issued credentials

**Status: Decided 2026-10-28.** Issued credentials are revoked by status, not
by deleting the row.

### Problem

Today an issuer "deletes" an issued VC with `DELETE /v1/credentials/:id`
(`credentials.controller.ts:534`) or `POST /v1/credentials/:id/reject`
(`:521`). Both call `credentialsRepository.delete({ id })`
(`credentials.service.ts:114-120`). Consequences reported by the client and
confirmed in code:

- The creator's credential disappears without explanation; `reject` and
  `delete` are indistinguishable, and there is no audit trail.
- The issuer UI reports an error after a successful deletion: the mutation is
  not awaited and has no error handler, and any failed refetch of the issued
  list replaces the whole grid with the untranslated key
  `errors.fetching-creators` (`IssuerIssuedCredentials.tsx:54-56`).
- The creator's page keeps the stale card until the next 60 s poll; polling
  pauses in background tabs and focus refetch is disabled
  (`useCreatorCredentials.ts`, `queryClient.ts`).
- No ownership check: any issuer can delete **any** credential by id, including
  creators' self-issued EMAIL / CONNECT / EKVC rows and other issuers'
  credentials.
- Deleting a `DATASUPPLIER` / `LICCIUM_DATASUPPLIER` request leaves its EKVC
  supporting credential in place and the keypair challenge consumed, so a
  re-request fails with 400 until the creator redoes the challenge.

### Decision

1. Add `REVOKED` to `CredentialVerificationStatus` (DB enum
   `credential_credential_status_enum`). A `SUCCESS` credential moves to
   `REVOKED`; the row is kept.
2. Add to `credential`: `revoked_at timestamptz NULL`,
   `revoked_reason varchar(500) NULL`. The revoking party is the row's
   `issuer_id`; no extra column.
3. New endpoint `POST /v1/credentials/:credentialId/revoke`
   (body `{ "reason"?: string }`, issuer role). Replaces `DELETE` for issued
   credentials in the UI.
4. `POST /v1/credentials/:credentialId/reject` keeps its meaning (a `PENDING`
   request is removed) and gains the same ownership and status guards.
5. `DELETE /v1/credentials/:credentialId` is deprecated: it behaves exactly
   like `reject` (owned `PENDING` rows only) and is removed from the UI. It can
   be dropped in a later release once no client calls it.

### API contract

| Endpoint | Guard | Allowed from | Result |
|---|---|---|---|
| `POST credentials/:id/revoke` `{ reason? }` | issuer; `credential.issuerId === caller.id`, otherwise `404` | `SUCCESS` → `REVOKED`; `REVOKED` → `200` unchanged (idempotent); `PENDING` → `409 Use reject` | formatted credential with `status: 'REVOKED'`, `revokedAt`, `revokedReason` |
| `POST credentials/:id/reject` | issuer; ownership, otherwise `404` | `PENDING` → row deleted; `SUCCESS` / `REVOKED` → `409 Use revoke` | `204` |
| `DELETE credentials/:id` (deprecated) | as `reject` | as `reject` | `204` |

`404` rather than `403` for a foreign credential follows the existing
convention (`NotFoundException` for role violations) and avoids confirming
that an id exists.

Reads:

- `GET /v1/credentials/issuers?status=` accepts `REVOKED` in addition to
  `PENDING` / `SUCCESS` (upper-case enum values, parsed case-sensitively).
- `GET /v1/credentials/creator` returns revoked credentials with
  `status: 'REVOKED'`, `revokedAt`, `revokedReason`, so the creator UI can show
  them instead of silently losing them.
- `POST /v1/credentials/export` (Liccium import) returns `SUCCESS` credentials
  only, as today.
- Supporting-credential lookups (`findMembershipSupportingCredential`, EKVC
  lookups) consider `SUCCESS` only.
- The partial unique index `idx_credential_unique_pending` covers `PENDING`
  rows only, so a creator may request the same type again after a revocation.

### Data model

Migration `<timestamp>-add-revoked-credential-status.ts`, following
`1779268347314-add-liccium-datasupplier-credential-type.ts`:

```sql
ALTER TYPE "public"."credential_credential_status_enum" ADD VALUE IF NOT EXISTS 'REVOKED';
ALTER TABLE "credential" ADD COLUMN "revoked_at" TIMESTAMPTZ NULL;
ALTER TABLE "credential" ADD COLUMN "revoked_reason" VARCHAR(500) NULL;
```

`ADD VALUE` cannot be used by a statement in the same transaction; keep the
enum change in its own migration or run it as the migration's first statement,
as the existing type migrations do. `down` recreates the enum without
`REVOKED` (rows in that status must be deleted or re-mapped first) and drops
the two columns.

Entity (`credential.entity.ts`): `revokedAt?: Date`, `revokedReason?: string`.
Formatters (`credentials.formatters.ts`): expose both fields on the member and
data-supplier shapes; strip them when null.

### Backend structure

- `CredentialsService.revokeIssuedCredential(credentialId, issuer, reason)`
  owns the state transition; the controller only parses input and maps
  errors. `rejectPendingCredential(credentialId, issuer)` replaces
  `removeMemberCredential` and carries the same guards.
- A single private `loadOwnedCredential(credentialId, issuerId)` resolves the
  row and applies the ownership rule for revoke, reject and the deprecated
  delete.
- When a `DATASUPPLIER` / `LICCIUM_DATASUPPLIER` **request** is rejected, the
  EKVC credential created with it (`credentials.service.ts:688-707`) is removed
  in the same transaction. Revoking an **issued** data-supplier credential
  leaves the EKVC in place: it attests key control, not supplier status.

### What revocation does *not* do yet

- The VC object is unchanged: no `credentialStatus` entry, so a holder's
  downloaded JSON/JWT copy stays cryptographically valid. Revocation is visible
  through the Creator Credentials API only. The W3C Bitstring Status List
  (`future/revocation-bitstring-status-list.md`) remains the path to
  verifier-visible revocation; when it lands, `revoke` additionally flips the
  status bit and the `REVOKED` status becomes its source of truth.
- Revoking a **connection** (`POST /v1/users/creators/:id/revoke`) does not
  cascade to credentials. Whether the issuer UI should offer "also revoke
  issued credentials" is open.
- Rejected `PENDING` requests are still deleted, not kept as `REJECTED`. A
  `REJECTED` status with a reason is a natural follow-up but is out of scope
  here.

### UI

Issuer (`/issuer/credentials/issued`):

- "Delete credential" becomes "Revoke credential"; the confirmation modal
  gains an optional reason field.
- The mutation is awaited; success and failure show a toast; both
  `issuersCredentials` and `issuerCreators` queries are invalidated.
- A failed refetch keeps the cached grid and shows an inline error banner
  instead of replacing the page; the message key is added to the loaded
  namespace.
- Revoked credentials are reachable through the status filter.

Creator (`/creator/credentials`):

- Revoked credentials appear in a "Revoked" section with "Revoked by
  *issuer* on *date*" and the reason; download stays available, marked as
  revoked.
- `useCreatorCredentials` enables `refetchOnWindowFocus`, so returning to the
  tab reflects the issuer's action without waiting for the poll.

### Acceptance criteria

1. An issuer revoking its own `SUCCESS` credential gets `200`, the row shows
   `REVOKED` with `revoked_at` set, and the creator's `GET /credentials/creator`
   returns it with `status: 'REVOKED'` and the reason.
2. Revoking a credential issued by another issuer returns `404` and changes
   nothing. Revoking a `PENDING` row returns `409`. Repeating a revoke returns
   `200` and does not change `revoked_at`.
3. Rejecting a data-supplier request removes its EKVC row; the creator can
   start a new keypair challenge and request again.
4. After a revoke, the issuer page shows a success toast and the card
   disappears from the `success` filter without an error message; the
   creator's tab shows the revoked card on focus.
5. `POST /credentials/export` never returns `REVOKED` credentials.
6. Unit tests cover the ownership rule, each state transition and idempotency;
   one e2e test covers the endpoint; the UI revoke dialog has a component test.

---

## CR-2 Issued-credentials page: search and creator identity

**Status: Decided 2026-10-28 (assumed defaults).** The client asked for search
and for e-mails on `/issuer/credentials/issued`. Until the client says
otherwise, "display e-mails" is read as: the full address inline, plus a
compact table view. Changing this later is a UI-only change.

### Current behaviour

- `src/pages/issuer/credentials/issued` lists `GET /v1/credentials/issuers?status=SUCCESS`
  and joins each credential to a creator from
  `GET /v1/users/creators?status=accepted` on the client
  (`IssuerIssuedCredentials.tsx:25-46`). Credentials whose creator is not in
  the *accepted* list (e.g. the connection was revoked) are silently dropped.
- The creator e-mail is shown truncated with the full address in a tooltip
  and click-to-copy (`CreatorCredentialDetailsCard.tsx:50-93`).
- The search box and the sorting dropdown are placeholders without state or
  handlers (`CreatorsFilters.tsx`, `SortingDropdown.tsx`); the backend has no
  search parameter.
- `GET /v1/credentials/issuers` already loads the `user` relation but the
  formatter drops it (`credentials.service.ts:43-53`,
  `credentials.formatters.ts:137-158`); the payload also leaks the internal
  `__keypairSnapshot` / `__acceptanceChallenge` fields of `credentialObject`.

### API contract

`GET /v1/credentials/issuers?status=<PENDING|SUCCESS|REVOKED>` keeps every
existing field and adds, per credential:

```jsonc
{
  "id": "42",                     // string, as today
  "status": "SUCCESS",            // or REVOKED / PENDING
  "type": "MEMBER",
  "issuedAt": "2026-09-01T10:00:00.000Z",   // credential.created_at
  "updatedAt": "2026-09-01T10:05:00.000Z",
  "revokedAt": null,              // CR-1
  "revokedReason": null,          // CR-1
  "connectionStatus": "ACCEPTED", // ACCEPTED | REQUESTED | REJECTED | REVOKED | null
  "creator": {
    "id": 7,
    "name": "Alice Example",      // user.name, may be null
    "email": "alice@example.org", // the creator's SUCCESS EMAIL credential, may be null
    "didKey": "did:key:zDna…"
  },
  "data": { /* unchanged, credentialObject without __* keys */ }
}
```

The creator e-mail comes from the creator's `SUCCESS` `EMAIL` credential
(`credential.email`), the same source `users.formatters.ts` already uses; the
service loads `user` + `user.credentials` and the issuer↔creator connection in
one query per request (no N+1).

### UI

- `IssuerIssuedCredentials` renders from the payload's `creator`; the
  client-side join with `useIssuerCreators` and the silent drop are removed.
  A credential whose `connectionStatus` is not `ACCEPTED` shows a
  "connection revoked" marker.
- `CreatorsFilters` becomes a controlled component:
  `{ query, onQueryChange, sort, onSortChange, view, onViewChange }`.
  Search is client-side, case-insensitive, trimmed, and matches creator name,
  e-mail, `didKey` and the credential type label. Sort options: name A–Z,
  name Z–A, newest first, oldest first (by `issuedAt`). `SortingDropdown`
  takes `{ value, options, onChange }`.
- Status chips above the grid: Issued (`SUCCESS`) | Revoked (`REVOKED`).
- The full e-mail is shown untruncated (wraps) with the existing copy action.
- View toggle: cards (today's design) | table (creator, e-mail, type,
  issued on, status, actions). The table shares the same data and actions.
- Duplicate React keys fixed (`key={credential.id}`), the `issuer-creators`
  namespace is loaded on the page, empty states for "no credentials" and
  "nothing matches".

### Acceptance criteria

1. Typing part of an e-mail, a name, a DID or "Member" narrows the grid;
   clearing the box restores it.
2. Every card and every table row shows the complete e-mail.
3. A credential whose connection was revoked is still listed, with the marker.
4. Sorting changes order without refetching; the status chips switch the
   `status` query parameter.

---

## CR-3 E-mail notifications

**Status: Decided 2026-10-28 (assumed defaults).** Assumptions to confirm
with the client: operator recipients come from configuration
(`NOTIFY_ADMIN_EMAILS`); issuers are notified at their primary Clerk e-mail;
the provider is AWS SES (the stack already runs in AWS) with a log-only
transport for development; creators are additionally notified when a
credential of theirs is revoked (CR-1). No mail infrastructure exists today:
SES is in sandbox with no verified identity, and the production EC2 instance
has no instance profile, so the infrastructure steps below are part of the
rollout, not of the code change.

### Events and recipients

| Event | Emitted from | Payload | Recipient | Subject |
|---|---|---|---|---|
| `user.created` | `WebhooksService.handleUserCreated` after a **new** user row is created (the `user.updated` fallback and the "already exists" path must not emit) | `{ userId, role, name, email }` | operators (`NOTIFY_ADMIN_EMAILS`) | `New sign-up on Creator Credentials: <name> (<role>)` |
| `connection.requested` | `UsersService.createConnection` (`POST /v1/users/issuers/:issuerId/confirm-request`) | `{ connectionId, issuerId, creatorId }` | the issuer | `New connection request from <creator name>` |
| `credential.requested` | the three `createPending…Credential` service methods (`POST /v1/credentials/request`) | `{ credentialId, issuerId, creatorId, credentialType }` | the issuer | `New <type label> credential request from <creator name>` |
| `credential.revoked` | `CredentialsService.revokeIssuedCredential` (CR-1) | `{ credentialId, issuerId, creatorId, credentialType, reason }` | the creator | `Your <type label> credential was revoked by <issuer name>` |

Each message carries one link into the app (`APP_BASE_URL` +
`/issuer/creators`, `/issuer/credentials/requested` or `/creator/credentials`)
and a plain-text and a minimal HTML body. No personal data beyond name and
e-mail of the counterpart.

### Design

- `src/notifications/` module: `NotificationsService` subscribes to the
  events with `@OnEvent(name, { async: true })`, resolves recipients, renders a
  template and calls the mailer. Nothing else imports a mailer.
- Events are published with `@nestjs/event-emitter`
  (`EventEmitterModule.forRoot()` in `AppModule`); names and payload types
  live in `src/notifications/notification-events.ts`.
- `MailerPort` (`send(message: MailMessage): Promise<void>`, injection token
  `MAILER`) with three adapters: `LogMailer` (development default: logs
  recipients and subject at `log`, body at `debug`), `SesMailer`
  (`@aws-sdk/client-sesv2` `SendEmailCommand`, credentials from the default
  provider chain, region from `AWS_REGION`), and an in-memory `FakeMailer`
  for tests.
- `RecipientsService`: issuer and creator e-mail = primary Clerk e-mail
  (`clerkClient.users.getUser(clerkId)`), falling back to the user's
  `SUCCESS` `EMAIL` credential; operators = `NOTIFY_ADMIN_EMAILS` split on
  commas. A missing recipient skips the message with a warning.
- Failures are caught and logged with the event name and ids; a notification
  can never fail or slow down the originating request.
- Configuration (names only; values live in the deployment secrets):
  `NOTIFY_PROVIDER` (`log` | `ses`, default `log`), `NOTIFY_FROM`,
  `NOTIFY_ADMIN_EMAILS`, `APP_BASE_URL`, `AWS_REGION`. Added to
  `.env.example` and to the compose files' environment lists.

### Rollout (infrastructure, outside the code change)

1. Verify the sender domain in SES (DKIM CNAME records in the domain's DNS),
   request production access, set `NOTIFY_FROM` to an address on that domain.
2. Give the production instance an IAM role (or scoped keys) with
   `ses:SendEmail` on the identity.
3. Set `NOTIFY_PROVIDER=ses`, `NOTIFY_ADMIN_EMAILS`, `APP_BASE_URL`.
4. Until then the service runs with `NOTIFY_PROVIDER=log`.

### Acceptance criteria

1. With the fake mailer, each of the four events produces exactly one message
   to the expected recipient with the expected subject and link.
2. A mailer failure is logged and the HTTP request that triggered the event
   still succeeds.
3. Re-delivering the Clerk `user.created` webhook for an existing user does not
   produce a second sign-up message.

---

## CR-4 `VerifiableCreator` credential

**Status: Decided 2026-10-28 (assumed defaults).** Requested shape:

```json
{
  "type": ["VerifiableCredential", "VerifiableAttestation", "VerifiableCreator"],
  "credentialSubject": {
    "id": "did:key:zDnaey3e1ief3tTdayKafvN7ax6XkU6utX9VEBcVTZNKmBz94",
    "verifiedBy": "liccium.com"
  }
}
```

### Decision (assumptions to confirm with the client)

- **Platform-issued**, like the Email credential: `issuer: did:web:liccium.com`,
  signing path 1, no issuer request/accept flow. `verifiedBy` is the platform
  host (`liccium.com`); the builder takes it as a parameter so an issuer-issued
  variant (option B in the earlier analysis) would only add a request/accept
  branch.
- **Trigger:** the creator's Liccium account is linked, i.e. whenever the
  Connect credential is (re)issued: `POST /v1/users/did-liccium/connect` and
  `POST /v1/credentials/export`. The credential is **idempotent**: one
  `SUCCESS` row per user, returned as is when it already exists.
- **Subject:** `resolveDidKey(user)`, the same did:key the other self-issued
  credentials use. No PII in the subject, so `termsOfUse` is
  `{ type: 'PresentationPolicy', confidentialityLevel: 'public', pii: 'none' }`.
- Not offered by issuers, not requestable by creators, not shown in the
  request flow.

### Changes

- Backend: `CredentialType.Creator = 'CREATOR'`; migration
  `ADD VALUE IF NOT EXISTS 'CREATOR'` on `credential_credential_type_enum`
  plus the partial unique index `idx_credential_unique_creator`
  (`user_id` where `credential_type = 'CREATOR'`);
  `generateCreatorCredentialObjectAndJWS(user, verifiedBy)` in
  `credentials.helpers.ts` (type marker `VerifiableCreator`, schema id
  `…/verification-credentials/creator/schema.json`);
  `CredentialsService.ensureCreatorCredential(user)` called from the two
  trigger points; formatter case `formatCreatorCredential` →
  `{ id, status, type: 'CREATOR', data: { verifiedBy, credentialObject } }`;
  the `Credentials.ts` union; `verifiableCreator` bucket in
  `GET /v1/credentials/creator` and in the `/export` response.
- UI: enum value, union, the three icon maps, `cards.json`
  `credential.types.creator.{title: "Verified Creator", description}`,
  `CredentialDetailsCard` shows `verifiedBy`, the creator's issued list shows
  the card, download file name. No template, no request-flow entry.
- Schema repo: `json-schema/verification-credentials/creator/schema.json` +
  `example.json` (envelope copied from `email/`, subject `id` + `verifiedBy`),
  a row in `json-schema/README.md`, a section in
  `03-verifiable-credentials-catalog.md` when shipped.

### Acceptance criteria

1. After `POST /v1/users/did-liccium/connect` the creator's bundle contains
   exactly one `CREATOR` credential whose object validates against
   `creator/schema.json`; calling connect again does not create a second row.
2. `POST /v1/credentials/export` returns it under `verifiableCreator`.
3. The creator's credentials page shows a "Verified Creator" card with
   `verifiedBy`.

---

## CR-5 Security and hygiene fixes

**Status: Decided 2026-10-28.** Items 1–5 and 8 ship with CR-1; item 7 is
deferred to the next dependency pass.

1. **Ownership on delete / reject.** Any issuer can delete any credential by
   id (`credentials.controller.ts:521-544`). Fixed by CR-1's ownership guard.
2. **Entity fields leak.** `GET /v1/users` and `GET /v1/users/check` return
   the `User` entity as is. Without a global `ClassSerializerInterceptor`
   the `@Exclude()` decorators do nothing, so `certificatePrivateKey`,
   `certificate509Buffer`, `nonce`, `domainRecord` and `didWebWellKnown` reach
   the browser. Fix: `app.useGlobalInterceptors(new ClassSerializerInterceptor(app.get(Reflector)))`
   in `main.ts`, and a test asserting that a serialized `User` never contains
   those fields.
3. **Clerk webhook raw body.** `NestFactory.create` is called without
   `rawBody: true` (`main.ts`), so `req.rawBody` is undefined and svix
   verification (`webhooks.controller.ts:42`) should fail. Production
   sign-ups work, so the deployed build may differ from `develop`; confirm
   against production logs during rollout. Fix: `rawBody: true`, the
   controller typed with Nest's `RawBodyRequest<Request>`, and a test that
   verifies a fixture signed with the svix library.
4. **ES256 signature encoding.** For EC issuer certificates the `openssl`
   command returns a DER-encoded ECDSA signature, but a JWS `ES256` signature
   is the raw `r || s` concatenation. Fix in `executeSignatureVerification`:
   accept DER or raw, verify, and store the token with the raw form so
   standard JOSE verifiers accept it; existing tokens are left as they are
   and documented.
5. **Transient fields in responses.** `credentialObject` returned by the
   issuer and creator endpoints includes `__keypairSnapshot` and
   `__acceptanceChallenge`. Fix: one `stripTransientFields()` used by every
   formatter.
6. **Orphaned EKVC after a rejected data-supplier request.** Covered by CR-1.
7. **Runtime.** Backend Docker images use `node:18-alpine` (Node 18 is end
   of life); move to Node 22 LTS together with the next dependency pass.
   *Deferred.*
8. **UI.** Duplicate React keys on the issued page, the missing
   `errors.fetching-creators` key and the search placeholder namespace,
   hard-coded English in `ConfirmationModal` moved to the `common` namespace.

---

## CR-6 Admin role and admin panel

**Status: Decided 2026-10-29.** A third role, `admin`, operated by the
platform. It can see everything, download any credential, and revoke issued
credentials. It can never request, accept or sign a credential and it owns no
issuer identity.

### Role model

- Clerk `publicMetadata.role = 'ADMIN'` (set by hand in the Clerk dashboard;
  there is no admin sign-up). The webhook maps it to `ClerkRole.Admin = 'admin'`
  (`user_clerk_role_enum` gains `admin`; migration `ADD VALUE IF NOT EXISTS`).
  Provisioning stays as for other users (cert + did:key are minted but unused).
- Backend guard `RolesGuard` + `@Roles(ClerkRole.Admin)` on every `/v1/admin/*`
  route (the existing `AuthGuard` loads the user). All existing issuer and
  creator routes keep their role checks, so an admin is rejected by
  `request`, `accept`, `verify-signature`, `create/email` and the connection
  endpoints by construction; a test asserts `403` for each.
- Revocation by an admin is recorded: `credential.revoked_by_user_id`
  (nullable FK → `user.id`) is set for every revoke (issuer or admin), so the
  creator-side text can say who revoked.

### API (`/v1/admin`, admin only)

| Method + path | Purpose | Response |
|---|---|---|
| `GET admin/credentials?status=&type=&issuerId=&q=&page=&pageSize=` | every credential across issuers and creators; `q` matches creator/issuer name, e-mail and did:key; `pageSize` ≤ 100 | `{ items: AdminCredential[], total, page, pageSize }` |
| `GET admin/credentials/:id` | one credential with the full object and proof (for download) | `AdminCredential` |
| `POST admin/credentials/:id/revoke` `{ reason? }` | revoke any `SUCCESS` credential; same state rules as CR-1, no ownership rule | `AdminCredential` |
| `GET admin/users?role=&q=&page=` | issuers and creators with identity and counts | paged list |
| `GET admin/stats` | counts by role, by credential type and status, revocations in the last 30 days | object |

`AdminCredential` = the CR-2 issued shape plus `issuer: { id, name, domain }`,
`revokedBy: { id, name, role } | null`, `statusList: { credential, index } | null`
(CR-7).

Events: an admin revoke emits `credential.revoked` with `revokedByRole`;
the creator **and** the issuer are notified.

### UI (`/admin`, admin only)

- `src/proxy.ts` protects `/admin(.*)`; the sidebar shows the admin
  navigation for `publicMetadata.role === 'ADMIN'`; other roles get 404 on
  `/admin`.
- `/admin/credentials`: table with status chips (Issued | Pending | Revoked),
  type and issuer filters, search, pagination; row actions: view (drawer with
  the credential object, issuer, creator, status-list entry), download JSON,
  revoke (modal with reason, confirm). No accept / sign controls exist.
- `/admin/users`: issuers and creators with counts, link to their credentials.
- `/admin/verify`: paste a JWT or credential JSON → calls
  `POST /v1/credentials/verify` and shows the three checks (CR-7).
- Test ids: `admin-credentials-table`, `admin-row`, `admin-filter-status-*`,
  `admin-search`, `admin-view`, `admin-download`, `admin-revoke`,
  `admin-revoke-reason`, `admin-revoke-confirm`, `admin-verify-input`,
  `admin-verify-submit`, `admin-verify-result`.

### Acceptance criteria

1. A Clerk user with `role = ADMIN` sees `/admin/*`, lists credentials of
   every issuer, downloads one, revokes one (creator and issuer notified,
   `revoked_by_user_id` set).
2. The same user gets `403`/`404` on every issuer and creator mutation
   endpoint and sees none of their pages.
3. Issuer and creator behaviour is unchanged (existing tests still pass).

---

## CR-7 Revocation list and credential verification

**Status: Decided 2026-10-29.** Today revocation exists only as a database
status (CR-1); a downloaded VC cannot be checked. This adds a W3C **Bitstring
Status List v1.0** served by the platform and a public verification endpoint.

### Status list

- One list per environment, id `1`, 131 072 entries, `statusPurpose:
  "revocation"` (profile from `future/revocation-bitstring-status-list.md`).
- `credential.status_list_index integer UNIQUE NULL` is drawn **at random**
  from the free entries (spec §6.5: sequential indices would reveal issuance
  volume) when a credential becomes `SUCCESS` (self-issued at creation,
  issuer-issued at `verify-signature`, `CREATOR` at creation). Every index
  ever handed out is recorded in `credential_status_list_slot`, so none is
  reused (§6.7), including those of rejected pending requests; the service
  logs a warning above 90 % occupancy. Credentials issued before this change
  have no index and stay uncheckable; the admin list shows them as "no
  status entry".
- Every newly issued VC object carries
  `credentialStatus: { id: "<APP_BASE_URL>/v1/status-lists/1#<index>", type: "BitstringStatusListEntry", statusPurpose: "revocation", statusListIndex: "<index>", statusListCredential: "<APP_BASE_URL>/v1/status-lists/1" }`
  (added before signing, so it is covered by the proof).
- `GET /v1/status-lists/1` (public, excluded from the Clerk gate) returns the
  `BitstringStatusListCredential` (`@context` v2, `type: ["VerifiableCredential","BitstringStatusListCredential"]`,
  `issuer: did:web:liccium.com`, `validFrom` now, `validUntil` +24 h,
  `credentialSubject: { type: "BitstringStatusList", statusPurpose: "revocation", encodedList, ttl: 60000 }`)
  where `encodedList` is the multibase (`u` + base64url) GZIP of the bitstring
  with a `1` at every index whose credential is `REVOKED`. It is signed with
  signing path 1 (JOSE header `typ: "vc+jwt"`) and served as JSON with
  `proof.jwt` (and raw JWT with `Accept: application/vc+jwt` or `?format=jwt`). The list is rebuilt from the
  database at most every 60 s (in-memory cache); `revoke` invalidates it.
- `Cache-Control: public, max-age=60`.

### Verification endpoint

`POST /v1/credentials/verify` (public, rate-limited by the proxy as `/export`
is) with body `{ "jwt": "<compact JWS>" }` or `{ "credential": { …, "proof": { "jwt" } } }`:

| Check | How | Result field |
|---|---|---|
| signature | the JWS `x5c` leaf certificate's public key verifies the compact JWS (`RS256` / `ES256`, raw and legacy DER ECDSA both accepted); the payload equals the credential object | `signature: { valid, issuerDid, certificateSubject }` |
| validity | `validFrom <= now <= validUntil` | `validity: { valid, validFrom, validUntil }` |
| revocation | the validate algorithm of Bitstring Status List §3.2: the entry must have a base-10 string `statusListIndex`, a URL `statusListCredential` and `statusSize` 1 (else `MALFORMED_VALUE_ERROR` / `UNSUPPORTED_STATUS_SIZE`); the list is read locally when it is this platform's URL, otherwise fetched over **https only** from a public address (no redirects, 2 MB cap, 5 s), **its JWS signature verified** against its `x5c` leaf (`STATUS_VERIFICATION_ERROR` otherwise, also when it is not a `BitstringStatusListCredential`, its purpose does not include `revocation`, or it is outside `validFrom`/`validUntil`), expanded (GZIP bomb cap 16 MB), checked for at least 131 072 entries (`STATUS_LIST_LENGTH_ERROR`) and for the index being inside it (`RANGE_ERROR`); then the bit is read. No entry at all → `unknown` | `revocation: { status: "valid" \| "revoked" \| "unknown" \| "error", checkedAt, reason? }` |

Response `{ valid: boolean, checks: {…}, credential: <object without proof> }`;
`valid` is true only when signature and validity pass and revocation is
`valid` or `unknown` (no entry to check); `revoked` and `error` make it
false, `reason` names the failed step. Malformed input → `400`. No
authentication, no persistence.

### Acceptance criteria

1. A newly issued Member credential carries `credentialStatus` with a unique
   index; `GET /v1/status-lists/1` validates against the W3C shape and its
   `encodedList` decodes to a bitstring with that bit `0`.
2. After `revoke`, within 60 s the bit is `1` and
   `POST /v1/credentials/verify` returns `revocation.status = "revoked"`,
   `valid = false`, while `signature.valid` stays `true`.
3. A tampered JWT → `signature.valid = false`; an expired one →
   `validity.valid = false`; a pre-change credential → `revocation.status = "unknown"`
   with `valid = true`; a foreign list with a bad signature, a wrong purpose,
   fewer than 131 072 entries or an out-of-range index → `revocation.status = "error"`
   with the spec's error name and `valid = false`.
4. Unit tests cover the bitstring encoding round trip (GZIP + base64url,
   index placement, 131 072 bits), random index allocation with retry and
   full-list failure, the three checks, every error of the validate algorithm,
   the https/private-address refusal and the cache invalidation on revoke.

Reviewed against the W3C Bitstring Status List v1.0 text on 2026-10-29;
not implemented, all optional: `statusSize > 1` with `statusMessage`,
`statusReference`, point-in-time (`timestamp`) queries, RFC 9457 problem
details, `415` on unsupported `Accept`.

---

## Test plan

### Backend (Jest)

Baseline on 2026-10-28: 7 unit suites, 6 of them failing scaffolds unrelated
to this work; they stay as they are, new suites must pass. New unit tests with
mocked repositories and a fake mailer:

- `credentials.service.spec.ts`: revoke (owner, foreign, pending, repeated),
  reject (owner, foreign, success), EKVC cleanup on rejected data-supplier
  request, `ensureCreatorCredential` idempotency, transient-field stripping.
- `notifications.service.spec.ts`: one message per event, recipient
  resolution and fallback, swallowed mailer failure, no duplicate sign-up.
- `webhooks.controller.spec.ts`: svix-signed fixture accepted, tampered body
  rejected.
- `signature-encoding.spec.ts`: DER → raw conversion for a generated P-256
  key; raw input accepted unchanged.
- `user-serialization.spec.ts`: excluded fields absent after
  `instanceToPlain`.

### UI (Vitest + Testing Library)

- `CreatorsFilters`: controlled input and sort emit changes; `filterCredentials`
  and `sortCredentials` helpers cover name / e-mail / DID / type matching and
  the four sort orders.
- `RevokeCredentialModal`: reason optional, confirm calls the mutation with
  `{ credentialId, reason }`, cancel does not.
- `CreatorRevokedCredentials`: renders issuer, date and reason.

### End-to-end (Playwright, UI repo `e2e/`)

Two modes selected by environment:

- **Mocked API (default):** Playwright intercepts `**/v1/**` with fixtures
  under `e2e/fixtures/`, so scenarios are deterministic and need no backend.
- **Real API:** `E2E_API=real` lets requests through to `NEXT_PUBLIC_NEST_API_URL`.

Authentication: Clerk protects `/issuer/*` and `/creator/*`. The suite signs
in once per role in a global setup with `@clerk/testing/playwright`
(`clerkSetup()` + `clerk.signIn()`) against the Clerk **development**
instance, using `E2E_ISSUER_EMAIL` / `E2E_ISSUER_PASSWORD` and
`E2E_CREATOR_EMAIL` / `E2E_CREATOR_PASSWORD`, and stores one storage state
per role. When those variables are absent, role scenarios are skipped with a
message and only the public scenarios run. Required variables are listed in
`e2e/README.md`; no credentials are committed.

Scenarios:

| ID | Role | Scenario |
|---|---|---|
| P1 | public | `/` and `/welcome` render; `/issuer` and `/creator` redirect an anonymous visitor to `/welcome` |
| P2 | public | sign-in page renders the Clerk form |
| I1 | issuer | issued page lists credentials with the full creator e-mail on every card |
| I2 | issuer | search narrows by e-mail, by name, by DID fragment and by type label; clearing restores |
| I3 | issuer | sort A–Z / Z–A / newest / oldest reorders the grid |
| I4 | issuer | table view shows one row per credential with e-mail, type, issued date, status |
| I5 | issuer | revoke: confirm with a reason → success toast → card leaves the Issued filter → appears under Revoked with the reason |
| I6 | issuer | revoke failure (API 500) → error toast, grid unchanged |
| I7 | issuer | a failing list refetch keeps the cached grid and shows an inline banner instead of an empty page |
| I8 | issuer | a credential whose connection is revoked is listed with the marker |
| I9 | issuer | requested page: accept flow smoke (challenge displayed) |
| I10 | issuer | creators page: a pending connection request is visible with accept / reject |
| C1 | creator | credentials page lists issued credentials and the Verified Creator card with `verifiedBy` |
| C2 | creator | revoked section shows issuer, date and reason for a revoked credential |
| C3 | creator | after the issuer revokes (fixture switch), refocusing the tab refreshes the list |
| C4 | creator | request flow smoke: select issuer and credential type, reach the confirmation step |
| C5 | creator | issuers page: send a connection request |
| N1 | creator | the "Verified Creator" card downloads a JSON whose `type` contains `VerifiableCreator` |

Notifications are not exercised end to end (no mailbox); they are covered by
the backend unit tests and, during rollout, by a manual check of the log
transport.

Test hooks: the UI exposes stable `data-testid` attributes for the suite:
`issued-search`, `issued-sort`, `issued-view-cards`, `issued-view-table`,
`issued-status-success`, `issued-status-revoked`, `credential-card`,
`credential-row`, `credential-email`, `credential-menu`, `credential-revoke`,
`revoke-modal`, `revoke-reason`, `revoke-confirm`, `revoke-cancel`,
`issued-error-banner`, `issued-empty`, `connection-revoked-marker`,
`creator-revoked-section`, `creator-revoked-card`, `verified-creator-card`,
`credential-download`. Scenarios select by these ids, never by text or CSS.

---

## Implementation status

Committed 2026-10-28 to `creator-credentials-backend` `develop` (1a444b9, 2145aff,
9c405b8) and `creator-credentials-ui` `main` (5667c3c). Backend deployed to the
dev environment (`cc-backend.liccium.network`, image `creator-credentials-dev:20261028-9c405b8`)
with the three migrations applied. The UI repo deploys to production from
`main` on Vercel: build `b8d86b7` (Node 24, React 19, Clerk 7.9, TanStack
Query 5) is live on creatorcredentials.app since 2026-10-28, and the production
backend followed the same day (image `creator-credentials-prod:20261028-9c405b8`,
migrations applied at boot). CR-1, CR-2, CR-4 and CR-5 are therefore live in
production; CR-3 runs with the log transport until SES is configured. Verification: backend 68 unit tests green (5
pre-existing scaffold suites still fail as before), `tsc` at baseline;
migrations applied, reverted and re-applied on a fresh PostgreSQL 15 and the
`CREATOR` unique index proven; UI 48 unit tests, lint, `tsc` and `next build`
green; Playwright 25 scenarios, public ones passing, role scenarios skipped
until Clerk test users exist (`e2e/README.md`).

| CR | Backend | UI | Spec / schema | Notes |
|---|---|---|---|---|
| CR-1 | ☑ | ☑ | ☑ | `DELETE` kept as a deprecated alias of reject |
| CR-2 | ☑ | ☑ | ☑ | issuer list via a scoped QueryBuilder join |
| CR-3 | ☑ | – | ☑ | log transport by default; SES rollout steps pending |
| CR-4 | ☑ | ☑ | ☑ | schema `creator/` + index row |
| CR-5 | ☑ items 1–5 | ☑ item 8 | ☑ | item 7 (Node 22) deferred |
| CR-6 | ☑ (`develop` ec39863, deployed to dev and prod 2026-10-29) | ☑ (`main` 7fddcc3) | ☑ | admin Clerk users still to be created |
| CR-7 | ☑ live: `GET /v1/status-lists/1` and `POST /v1/credentials/verify` on dev and prod; ◐ spec-compliance pass of 2026-10-29 (random indices, slot table, `ttl`, `typ`, verified foreign lists, error reasons) committed, not deployed | ☑ verify page (+ `error` reasons, not deployed) | ☑ | `API_BASE_URL` set on both hosts; pre-existing VCs have no status entry (`revocation: unknown`) |
| Tests | ☑ Jest | ☑ Vitest | – | Playwright suite in `e2e/` |

Decisions taken during implementation, to confirm at review:

- `migrationsTransactionMode: 'each'` in `typeorm.config.ts` and
  `app.module.ts`: PostgreSQL refuses to use an enum value added in the same
  transaction, and a partial-index predicate on the enum column is not
  immutable, so each migration now runs in its own transaction. This changes
  the behaviour of every future migration; CR-4's migration was split into the
  enum change and the unique index.
- Enum `down()` migrations drop and recreate the partial indexes whose
  predicates pin the old type; older type migrations have the same latent
  problem and were left untouched.
- Status values are upper-case enum strings (`?status=REVOKED`), credential
  ids stay strings.
- `GET /credentials/issuers` items without a `creator` (legacy rows) render a
  placeholder in the UI instead of being dropped.
- Found during the dev rollout: the runtime DataSource had `migrationsRun: true`
  but no `migrations` list, so boot never applied migrations (the README's
  claim was wrong); fixed in 9c405b8. The images' `pnpm approve-builds` step
  broke `pnpm install` with current pnpm; removed, pnpm pinned (2145aff).
