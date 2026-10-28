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
Query 5) is live on creatorcredentials.app since 2026-10-28, while the
production backend still runs the previous release. Until the backend ships,
the production issued page shows placeholders for creator identity and the
revoke action fails with an error toast; everything else is unchanged. Verification: backend 68 unit tests green (5
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
