# fin — Fintech Support SPEC-PIN

> **Canonical marker:** `[fin]`  
> Stacks: web=Vue 3 · mobile=Android Compose (CometChat UIKit v6) / iOS Swift · backend=Java (Spring Boot)

---

## 1. Product Summary

A customer-support portal for a fintech company. Customers submit and track support tickets tied to
their financial transactions; agents triage, respond, and advance tickets through resolution; managers
oversee queues, curate data, and handle escalations; admins manage users and the full system.
All roles communicate in-app via CometChat 1:1 and group chat with voice/video call capability.

---

## 2. RBAC Roles

| Role | Permissions summary |
|------|---------------------|
| **admin** | Full CRUD on users, tickets, transactions; assign agents; manage system config |
| **manager** | Full CRUD on tickets + transactions; assign agents; view all queues; archive records |
| **agent** | List/detail assigned tickets; add notes; advance ticket status; view linked transactions |
| **customer** | Create/list/detail/edit/cancel own tickets; view own transactions; chat with support |
| **guest** | Read-only FAQ / public knowledge base; no ticket creation; login-smoke role |

**Login-smoke role:** `customer` — creates a ticket immediately after first login.

---

## 3. Core Entities + Data Model

### 3.1 SupportTicket

| Field | Type | Notes |
|-------|------|-------|
| `id` | string | UID prefix `fin-tkt-` |
| `title` | string | max 120 chars |
| `description` | string | plain text / markdown |
| `category` | enum | `account_access` · `transaction_dispute` · `fraud_report` · `product_inquiry` · `other` |
| `priority` | enum | `low` · `medium` · `high` · `critical` |
| `status` | enum | see state machine below |
| `customer_id` | FK → User | creator / owner |
| `assigned_agent_id` | FK → User | nullable; agent responsible |
| `linked_transaction_id` | FK → Transaction | nullable; transaction under dispute |
| `attachment_url` | string | screenshot / document (image_url for this entity) |
| `created_at` | ISO-8601 UTC | |
| `updated_at` | ISO-8601 UTC | |

**State machine:**
```
open ──[assign agent]──► assigned ──[agent starts]──► in_progress
     ──[customer cancels]──► cancelled

in_progress ──[agent submits]──► pending_review ──[manager approves]──► resolved ──[auto/manual]──► closed
            ──[customer cancels]──► cancelled

pending_review ──[manager rejects]──► in_progress
resolved ──[customer reopens]──► in_progress
```

Legal `status` values: `open` · `assigned` · `in_progress` · `pending_review` · `resolved` · `closed` · `cancelled`

---

### 3.2 Transaction

| Field | Type | Notes |
|-------|------|-------|
| `id` | string | UID prefix `fin-txn-` |
| `customer_id` | FK → User | account owner |
| `amount` | string | decimal as string e.g. `"149.99"` |
| `currency` | string | ISO-4217 e.g. `"USD"` |
| `type` | enum | `debit` · `credit` · `refund` · `transfer` |
| `status` | enum | see state machine below |
| `description` | string | merchant / purpose label |
| `reference_code` | string | external bank/payment ref |
| `image_url` | string | merchant logo or category icon |
| `created_at` | ISO-8601 UTC | |
| `updated_at` | ISO-8601 UTC | |

**State machine:**
```
pending ──[process]──► processing ──[settle]──► completed ──[refund]──► refunded
        ──[fail]──► failed
processing ──[fail]──► failed
```

Legal `status` values: `pending` · `processing` · `completed` · `refunded` · `failed`

---

### 3.3 CRUD Matrix

| Entity | Action | customer | agent | manager | admin |
|--------|--------|:--------:|:-----:|:-------:|:-----:|
| SupportTicket | create | own ✓ | — | ✓ | ✓ |
| SupportTicket | list | own ✓ | assigned ✓ | all ✓ | all ✓ |
| SupportTicket | detail | own ✓ | assigned ✓ | all ✓ | all ✓ |
| SupportTicket | edit | own (open/assigned only) ✓ | notes + status advance ✓ | all fields ✓ | all fields ✓ |
| SupportTicket | cancel / archive | own (open/assigned) ✓ | — | any ✓ | any ✓ |
| Transaction | create | — | — | ✓ | ✓ |
| Transaction | list | own ✓ | all ✓ | all ✓ | all ✓ |
| Transaction | detail | own ✓ | ✓ | ✓ | ✓ |
| Transaction | edit / status-advance | — | — | status only ✓ | all fields ✓ |
| Transaction | archive | — | — | ✓ | ✓ |

---

## 4. Key User Flows

### 4.1 customer — full CRUD

1. Login as `alice@fin.io` (role: customer).
2. Dashboard shows recent transactions widget + open ticket count.
3. Tap **New Ticket** → fill title, description, select `category=transaction_dispute`, `priority=high`,
   attach a screenshot image → submit → status becomes **open**.
4. Ticket appears in My Tickets list with status badge "Open".
5. Open ticket detail → edit description to add more context → save.
6. Observe status change to **assigned** (agent picked up) → comment added by agent visible in note thread.
7. Decide to cancel → tap Cancel → confirm dialog → status becomes **cancelled**; badge updates in list.

### 4.2 agent — full CRUD

1. Login as `bob.agent@fin.io` (role: agent).
2. Ticket Queue shows all assigned tickets; filter by `priority=critical`.
3. Open ticket `fin-tkt-003` (critical fraud report) → read description and linked transaction detail.
4. Add internal note: "Reviewed transaction history; escalating for manager review." (edit/note create)
5. Advance status: `assigned → in_progress` via Status menu.
6. Resolve investigation → advance: `in_progress → pending_review`.
7. Attempt to delete ticket → receive 403 Forbidden; error shown gracefully in UI.

### 4.3 manager — full CRUD

1. Login as `carol.mgr@fin.io` (role: manager).
2. Navigate to Transactions → **Create Transaction**: type=credit, amount=`"2000.00"`, currency=USD,
   customer=fin-usr-001, description="Compensation Credit", status=pending → save.
3. View all tickets; filter `status=pending_review`.
4. Open ticket detail → assign agent (edit `assigned_agent_id`).
5. Approve: advance `pending_review → resolved`.
6. Archive (soft-delete) a `resolved` ticket older than 30 days.
7. Back in Transactions → edit newly created transaction status: `pending → processing`.
8. Archive a `failed` transaction record.

### 4.4 admin — full CRUD

1. Login as `admin@fin.io` (role: admin).
2. Navigate to Users → **Create User**: name, email, role=agent → save.
3. View Users list; search by name.
4. Edit an existing customer's name/avatar.
5. Archive (disable) an inactive agent account.
6. Navigate to Tickets → hard-delete a `cancelled` ticket.
7. Advance a `completed` transaction to `refunded`.

### 4.5 automation flow (all platforms)

1. Login as `chat-a@fin.io` (password: `Fin@seed2026!`).
2. Navigate to **Chat** tab.
3. Open 1:1 conversation with `chat-b@fin.io` (uid `fin-chb-001`).
4. Send TEXT message: `"Hello from Fintech Support automation"`.
5. Send IMAGE message: attach bundled asset `assets/demo_image.png`.
6. Tap the voice/video call button → CometChat call UI renders with both participant tiles.
7. Terminate call after ~3 s.

---

## 5. REST API Contract

### Shared canonical skeleton

```
Base path : /api
Health    : GET /api/health → {"status":"ok"}

Auth:
  POST /api/auth/login   body: {email, password}
                         → {token, cometchat_auth_token, user:{uid,name,role,avatar_url}}
  POST /api/auth/signup  same response shape
  Authorization header   : Bearer <JWT>  (subject = user uid)

List (paginated + envelope):
  GET /api/<resource>?page=1&limit=20
  → {"data":[...], "pagination":{"page":1,"limit":20,"total":N}}

Detail:
  GET /api/<resource>/{id} → bare object

Errors (non-2xx):
  {"detail":"<human message>"}
  Codes: 401 unauthenticated · 403 forbidden · 404 not found · 422 validation

Serialisation rules:
  Money/decimals → JSON string ("149.99")
  Timestamps     → ISO-8601 UTC ("2026-07-20T10:30:00Z")
  UIDs           → prefixed "fin-"

API_URL convention (all clients):
  Value = scheme://host:port  — NO trailing path, NO /api suffix.
  Client always appends the full route: {API_URL}/api/auth/login
  Web behind nginx /api proxy: API_URL="" (empty); calls are relative (/api/...).
  Android emulator default  : http://10.0.2.2:8080
  iOS simulator default     : http://localhost:8080
  NEVER bake /api into API_URL (causes fatal double /api/api/... 404).
```

### fin-specific endpoints

```
Tickets:
  POST   /api/tickets                     create ticket
  GET    /api/tickets                     list (role-filtered; supports ?status=&priority=&page=&limit=)
  GET    /api/tickets/{id}                detail
  PATCH  /api/tickets/{id}                partial update (title/description/priority/assigned_agent_id/attachment_url)
  DELETE /api/tickets/{id}                soft-archive (manager/admin); hard-delete (admin only with ?hard=true)
  PATCH  /api/tickets/{id}/status         advance status; body: {status, note?}
  POST   /api/tickets/{id}/notes          add note; body: {content, is_internal}
  GET    /api/tickets/{id}/notes          list notes

Transactions:
  POST   /api/transactions                create (manager/admin); body: {customer_id,amount,currency,type,description,reference_code,image_url}
  GET    /api/transactions                list (role-filtered; supports ?status=&type=&page=&limit=)
  GET    /api/transactions/{id}           detail
  PATCH  /api/transactions/{id}           partial update (manager: status only; admin: all fields)
  DELETE /api/transactions/{id}           soft-archive (manager/admin)
  PATCH  /api/transactions/{id}/status    advance status; body: {status}

Users (admin owns; any user reads own profile):
  GET    /api/users                       list all (admin)
  GET    /api/users/{uid}                 detail (self or admin)
  PATCH  /api/users/{uid}                 edit (self or admin)
  DELETE /api/users/{uid}                 disable/archive (admin)
  POST   /api/users                       create new user (admin)
```

---

## 6. Namespaced Seed

**Seed password for ALL accounts: `Fin@seed2026!`**  
Backend env var: `SEED_PASSWORD=Fin@seed2026!`  
Stored BCrypt-hashed in DB.  
Seed script is idempotent (upsert by `id`; safe to re-run).  
Script provisions both backend DB rows and CometChat users via management API.

### Users

| uid | name | email | role | avatar_url |
|-----|------|-------|------|------------|
| fin-usr-001 | Alice Chen | alice@fin.io | customer | https://i.pravatar.cc/150?u=fin-usr-001 |
| fin-usr-002 | Bob Kapoor | bob.agent@fin.io | agent | https://i.pravatar.cc/150?u=fin-usr-002 |
| fin-usr-003 | Carol Martinez | carol.mgr@fin.io | manager | https://i.pravatar.cc/150?u=fin-usr-003 |
| fin-usr-004 | David Osei | admin@fin.io | admin | https://i.pravatar.cc/150?u=fin-usr-004 |
| fin-usr-005 | Eve Tanaka | eve.guest@fin.io | guest | https://i.pravatar.cc/150?u=fin-usr-005 |
| fin-cha-001 | Chat Alpha | chat-a@fin.io | customer | https://i.pravatar.cc/150?u=fin-cha-001 |
| fin-chb-001 | Chat Beta | chat-b@fin.io | customer | https://i.pravatar.cc/150?u=fin-chb-001 |

### Seed Transactions (5 records — all statuses covered)

| id | customer_id | amount | currency | type | status | description | reference_code | image_url |
|----|-------------|--------|----------|------|--------|-------------|----------------|-----------|
| fin-txn-001 | fin-usr-001 | "250.00" | USD | debit | completed | Netflix Subscription | REF-NF-2026-001 | https://picsum.photos/seed/fin-txn-001/64/64 |
| fin-txn-002 | fin-usr-001 | "1500.00" | USD | transfer | pending | Wire Transfer to Savings | REF-WT-2026-002 | https://picsum.photos/seed/fin-txn-002/64/64 |
| fin-txn-003 | fin-usr-001 | "89.99" | USD | debit | failed | Online Purchase – TechMart | REF-TM-2026-003 | https://picsum.photos/seed/fin-txn-003/64/64 |
| fin-txn-004 | fin-cha-001 | "300.00" | USD | credit | processing | Payroll Deposit | REF-PD-2026-004 | https://picsum.photos/seed/fin-txn-004/64/64 |
| fin-txn-005 | fin-usr-001 | "89.99" | USD | refund | refunded | Refund – TechMart dispute | REF-RF-2026-005 | https://picsum.photos/seed/fin-txn-005/64/64 |

### Seed Tickets (5 records — all statuses covered)

| id | customer_id | title | category | priority | status | assigned_agent_id | linked_transaction_id | attachment_url |
|----|-------------|-------|----------|----------|--------|-------------------|-----------------------|----------------|
| fin-tkt-001 | fin-usr-001 | Failed transaction not refunded | transaction_dispute | high | open | — | fin-txn-003 | https://picsum.photos/seed/fin-tkt-001/400/300 |
| fin-tkt-002 | fin-usr-001 | Cannot log into mobile app | account_access | medium | in_progress | fin-usr-002 | — | https://picsum.photos/seed/fin-tkt-002/400/300 |
| fin-tkt-003 | fin-cha-001 | Suspicious charge on account | fraud_report | critical | pending_review | fin-usr-002 | fin-txn-004 | https://picsum.photos/seed/fin-tkt-003/400/300 |
| fin-tkt-004 | fin-usr-001 | Wire transfer fee inquiry | product_inquiry | low | resolved | fin-usr-002 | fin-txn-002 | https://picsum.photos/seed/fin-tkt-004/400/300 |
| fin-tkt-005 | fin-cha-001 | Duplicate charge on credit card | transaction_dispute | high | cancelled | — | — | https://picsum.photos/seed/fin-tkt-005/400/300 |

Seed notes (idempotent upsert by `ticket_id + content` hash):
- fin-tkt-002: `"Investigated — password reset email sent. Monitoring."` (agent, internal=true)
- fin-tkt-003: `"Transaction log pulled. Escalated to fraud team."` (agent, internal=true)
- fin-tkt-004: `"Standard wire fee applies. No waiver criteria met. Closing."` (agent, internal=false)

---

## 7. Screen / Component Map

### Web (Vue 3)

| Screen | Route | Key components | testIDs (`data-testid`) |
|--------|-------|----------------|--------------------------|
| Login | `/login` | EmailInput, PasswordInput, LoginButton, QuickFillRow (Customer/Agent/Manager/Admin/Guest) | `email-input` · `password-input` · `login-submit` |
| Dashboard | `/` | TicketSummaryCards, RecentTransactionsList, OpenTicketCount | — |
| Ticket List | `/tickets` | TicketTable (status/priority filter, search), NewTicketButton, StatusBadge | — |
| Ticket Create | `/tickets/new` | TicketForm (title/desc/category/priority/attachment upload) | — |
| Ticket Detail | `/tickets/:id` | TicketHeader, StatusBadge, LinkedTransactionCard, NoteThread, AddNoteForm, StatusAdvanceMenu, EditButton, CancelButton | — |
| Transaction List | `/transactions` | TransactionTable (type/status filter), NewTransactionButton (manager/admin) | — |
| Transaction Detail | `/transactions/:id` | TransactionCard (amount/status/reference), LinkedTicketsList | — |
| Chat | `/chat` | CometChat UIKit conversation list + message thread, CallButton (icon, not emoji) | — |
| User List | `/admin/users` | UserTable, CreateUserButton, DisableUserAction | — |

**Icon library (Web):** `lucide-vue-next` (MIT, bundled, zero external requests).  
Import named icons only (e.g. `Ticket`, `CreditCard`, `MessageSquare`, `Home`, `User`).  
No raw Unicode emoji anywhere in UI.

### Mobile / Native — Android Compose (UIKit v6) & iOS (Swift)

| Screen | Android Compose | iOS Swift | a11y / testID |
|--------|----------------|-----------|---------------|
| Login | `LoginScreen` | `LoginViewController` | `accessibilityIdentifier`: `email-input`, `password-input`, `login-submit`; QuickFill buttons with visible text labels: "Customer" · "Agent" · "Manager" · "Admin" · "Guest" |
| Ticket List | `TicketListScreen` | `TicketListViewController` | — |
| Ticket Create | `TicketCreateScreen` | `TicketCreateViewController` | — |
| Ticket Detail | `TicketDetailScreen` | `TicketDetailViewController` | — |
| Transaction List | `TransactionListScreen` | `TransactionListViewController` | — |
| Transaction Detail | `TransactionDetailScreen` | `TransactionDetailViewController` | — |
| Chat | `ChatScreen` (CometChat UIKit v6 `CometChatConversationsWithMessages`) | `ChatViewController` | — |
| Profile | `ProfileScreen` | `ProfileViewController` | — |

**Tab bar icons — NO raw emoji:**
| Tab | Android (`Icons.Default.*`) | iOS (SF Symbol `systemName:`) |
|-----|-----------------------------|-------------------------------|
| Home | `Home` | `house` |
| Tickets | `ConfirmationNumber` | `ticket` |
| Transactions | `Receipt` | `creditcard` |
| Chat | `Chat` | `message` |
| Profile | `Person` | `person` |

Android dependency: `androidx.compose.material:material-icons-extended`  
iOS minimum: iOS 15 SF Symbols (all symbols above available in iOS 15+).

**Quick-fill demo buttons** must render visible role-name text ("Customer", "Agent", "Manager", "Admin", "Guest") — the harness taps by text, never types a password.

---

## 8. UI States + Assets

### Placeholder image sources (stable, never 404)

| Use | Service | Example |
|-----|---------|---------|
| User avatars | `https://i.pravatar.cc/150?u={uid}` | deterministic per uid |
| Entity / attachment images | `https://picsum.photos/seed/{entity-id}/400/300` | deterministic per seed string |
| Offline / error fallback | bundled `assets/placeholder.png` (400×300 grey rectangle) | shipped in app binary |
| Demo image message | bundled `assets/demo_image.png` (320×240 sample) | sent during automation flow |

### List screen UI states (mandatory)

| Screen | Empty state | Loading state | Error state |
|--------|-------------|---------------|-------------|
| Ticket List | Library icon (inbox/ticket), copy "No tickets yet — tap + to submit one", CTA button "Submit a Ticket" | 3× TicketSkeleton shimmer cards | "Couldn't load tickets." + Retry button |
| Transaction List | Library icon (credit-card), copy "No transactions found", CTA "Contact Support" | 3× TransactionSkeleton shimmer rows | "Couldn't load transactions." + Retry button |
| Chat conversation list | Library icon (message-bubble), copy "No conversations yet", CTA "Start a Chat" | Spinner centred | "Couldn't load chats." + Retry button |
| User List (admin) | Library icon (group/users), copy "No users found" | 3× UserSkeleton shimmer rows | "Couldn't load users." + Retry button |

### Detail screen UI states (mandatory)

| Screen | Loading state | Error state |
|--------|---------------|-------------|
| Ticket Detail | Full-page skeleton (header block + body block) | "Couldn't load this ticket." + Back button |
| Transaction Detail | Full-page skeleton (card block) | "Couldn't load this transaction." + Back button |

### Chat image messages

- IMAGE messages from CometChat **must render inline** in the message thread (not as a download link).
- CometChat UIKit v6 renders received image messages with a tap-to-expand lightbox by default — do not suppress this.
- The automation flow sends `assets/demo_image.png` via `CometChat.sendMediaMessage()` with `messageType = CometChatConstants.MESSAGE_TYPE_IMAGE`.

### Icon library mandate (summary)

- **Web (Vue 3):** `lucide-vue-next` — named icon imports, no CDN, no emoji.
- **Android:** `androidx.compose.material:material-icons-extended` — `Icon(Icons.Default.X)` composables.
- **iOS:** SF Symbols via `Image(systemName:)` — iOS 15+ symbols only.
- **Absolute prohibition:** raw Unicode emoji characters in tab bars, buttons, badges, status indicators, empty-state illustrations, or app logos. Emoji render as glyph boxes on iOS and cannot be tinted with active/inactive colour tokens.
