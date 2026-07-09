# SPEC-PIN · Marketplace (mkt) · req:baseline

> **Binding spec.** All platforms (web/Next.js, mobile/React Native+Expo, backend/Python) MUST conform.  
> Last updated: 2026-07-08 · Author: req:baseline

---

## 1. Product Summary

Marketplace is a buyer-seller communication platform where users discover product listings, negotiate pricing, and complete transactions through real-time chat and audio/video calls — all within a single authenticated session.  
Sellers post listings, buyers browse and initiate conversations, and admins moderate the platform; every interaction is backed by CometChat messaging and calling infrastructure.

---

## 2. RBAC Roles

| Role | UID prefix | Permissions |
|---|---|---|
| `admin` | `mkt-adm-` | Full platform access: manage users, listings, conversations, and calls; ban/unban accounts; view audit logs |
| `seller` | `mkt-sel-` | Create/edit/delete own listings; accept or reject buyer conversations; initiate and receive calls |
| `buyer` | `mkt-buy-` | Browse listings; start conversations with sellers; send messages; initiate calls |
| `moderator` | `mkt-mod-` | Read all conversations and listings; flag/remove content; cannot post listings or initiate calls |
| `smoke` *(login-smoke)* | `mkt-smk-` | Minimal read-only access used for automated login health checks; no write operations permitted |

---

## 3. Core Entities + Data Model

### users
| Field | Type | Notes |
|---|---|---|
| `uid` | `VARCHAR(64)` PK | CometChat UID, prefixed per role |
| `name` | `VARCHAR(128)` | Display name |
| `email` | `VARCHAR(256)` UNIQUE | Auth credential |
| `password_hash` | `VARCHAR(256)` | bcrypt |
| `role` | `ENUM(admin,seller,buyer,moderator,smoke)` | |
| `avatar_url` | `TEXT` | Optional |
| `status` | `ENUM(active,banned,pending)` DEFAULT `active` | |
| `created_at` | `TIMESTAMPTZ` | |

### listings
| Field | Type | Notes |
|---|---|---|
| `id` | `UUID` PK | |
| `seller_uid` | `VARCHAR(64)` FK→users | |
| `title` | `VARCHAR(256)` | |
| `description` | `TEXT` | |
| `price` | `NUMERIC(12,2)` | |
| `currency` | `CHAR(3)` DEFAULT `USD` | |
| `category` | `VARCHAR(64)` | |
| `images` | `TEXT[]` | Array of URLs |
| `status` | `ENUM(active,sold,removed)` DEFAULT `active` | |
| `created_at` | `TIMESTAMPTZ` | |
| `updated_at` | `TIMESTAMPTZ` | |

### conversations
| Field | Type | Notes |
|---|---|---|
| `id` | `VARCHAR(64)` PK | CometChat conversation ID |
| `listing_id` | `UUID` FK→listings | The listing context |
| `buyer_uid` | `VARCHAR(64)` FK→users | |
| `seller_uid` | `VARCHAR(64)` FK→users | |
| `status` | `ENUM(open,closed,flagged)` DEFAULT `open` | |
| `created_at` | `TIMESTAMPTZ` | |

### messages *(shadow log — CometChat is source of truth)*
| Field | Type | Notes |
|---|---|---|
| `id` | `BIGINT` PK | CometChat message ID |
| `conversation_id` | `VARCHAR(64)` FK→conversations | |
| `sender_uid` | `VARCHAR(64)` FK→users | |
| `text` | `TEXT` | |
| `type` | `ENUM(text,image,file,call)` | |
| `sent_at` | `TIMESTAMPTZ` | |

### calls
| Field | Type | Notes |
|---|---|---|
| `id` | `VARCHAR(64)` PK | CometChat session ID |
| `conversation_id` | `VARCHAR(64)` FK→conversations | |
| `initiator_uid` | `VARCHAR(64)` FK→users | |
| `receiver_uid` | `VARCHAR(64)` FK→users | |
| `type` | `ENUM(audio,video)` | |
| `status` | `ENUM(initiated,accepted,rejected,ended)` | |
| `started_at` | `TIMESTAMPTZ` | |
| `ended_at` | `TIMESTAMPTZ` | Nullable |
| `duration_seconds` | `INT` | Nullable |

---

## 4. Key User Flows

### 4.1 Fixed Flow (all clients MUST implement in this order)
1. **Login** — User submits email + password → backend returns JWT + CometChat auth token → client initialises CometChat SDK with the auth token.
2. **Open a conversation** — User navigates to a listing → taps/clicks "Message Seller" (buyer) or opens an existing thread (seller/admin) → `GET /api/conversations/{id}` loads metadata → CometChat SDK opens the conversation channel.
3. **Send a message** — User types in the message composer and submits → CometChat SDK sends the message → shadow log webhook records it → UI appends message optimistically.
4. **Start a call** — User taps the call button in an open conversation → client invokes CometChat Call SDK `initiateCall(type)` → other party receives incoming call UI → on accept, call session begins; on end, duration is recorded.

### 4.2 Seller Listing Flow
Seller logs in → navigates to "My Listings" → creates a listing (title, price, images, category) → `POST /api/listings` → listing appears in marketplace feed.

### 4.3 Buyer Browse & Contact Flow
Buyer logs in → browses listing feed (`GET /api/listings`) → opens listing detail (`GET /api/listings/{id}`) → initiates conversation → proceeds to Fixed Flow step 2.

### 4.4 Admin Moderation Flow
Admin logs in → opens moderation dashboard → views flagged conversations (`GET /api/conversations?status=flagged`) → removes listing or bans user (`PATCH /api/users/{uid}`).

### 4.5 Smoke Login Flow *(automated health check)*
smoke user hits `POST /api/auth/login` → receives 200 + valid JWT → hits `GET /api/health` → expects `{"status":"ok"}` → session ends (no writes performed).

---

## 5. REST API Contract

> Base path: `/api`  
> Auth header: `Authorization: Bearer <JWT>` (all endpoints except `/auth/login` and `/health`)  
> Content-Type: `application/json`

### Auth

#### `POST /api/auth/login`
Request:
```json
{ "email": "string", "password": "string" }
```
Response `200`:
```json
{
  "token": "<JWT>",
  "cometchat_auth_token": "<string>",
  "user": { "uid": "string", "name": "string", "role": "string", "avatar_url": "string|null" }
}
```
Errors: `401 Invalid credentials` · `400 Validation error`

---

### Health

#### `GET /api/health`
No auth required.  
Response `200`:
```json
{ "status": "ok", "timestamp": "<ISO8601>" }
```

---

### Listings

#### `GET /api/listings`
Query params: `?category=&min_price=&max_price=&status=active&page=1&limit=20`  
Response `200`:
```json
{
  "data": [{ "id": "uuid", "title": "string", "price": 0.0, "currency": "USD",
             "category": "string", "images": ["url"], "seller": { "uid": "string", "name": "string" },
             "status": "active", "created_at": "ISO8601" }],
  "pagination": { "page": 1, "limit": 20, "total": 0 }
}
```

#### `GET /api/listings/{id}`
Response `200`: single listing object (same shape as above, includes `description`).  
Errors: `404 Not found`

#### `POST /api/listings` *(seller, admin only)*
Request:
```json
{ "title": "string", "description": "string", "price": 0.0, "currency": "USD",
  "category": "string", "images": ["url"] }
```
Response `201`: created listing object.

#### `PATCH /api/listings/{id}` *(owner seller or admin)*
Request: partial listing fields.  
Response `200`: updated listing object.

#### `DELETE /api/listings/{id}` *(owner seller or admin)*
Response `204`

---

### Conversations

#### `GET /api/conversations`
Query params: `?status=open|closed|flagged&page=1&limit=20` (admin/mod see all; seller/buyer see own)  
Response `200`: paginated list with `id, listing_id, buyer, seller, status, created_at`.

#### `GET /api/conversations/{id}`
Response `200`: conversation detail + CometChat conversation ID.  
Errors: `403 Forbidden` · `404 Not found`

#### `POST /api/conversations` *(buyer only)*
Request:
```json
{ "listing_id": "uuid" }
```
Response `201`:
```json
{ "id": "string", "cometchat_conversation_id": "string", "listing_id": "uuid" }
```

#### `PATCH /api/conversations/{id}` *(admin/mod)*
Request: `{ "status": "flagged|closed" }`  
Response `200`: updated conversation object.

---

### Users *(admin only)*

#### `GET /api/users`
Response `200`: paginated user list.

#### `PATCH /api/users/{uid}`
Request: `{ "status": "active|banned" }`  
Response `200`: updated user object.

---

## 6. Namespaced Seed

All UIDs prefixed `mkt-`.

| UID | Name | Email | Role |
|---|---|---|---|
| `mkt-adm-001` | Alex Admin | `alex.admin@mkt.test` | `admin` |
| `mkt-sel-001` | Sara Seller | `sara.seller@mkt.test` | `seller` |
| `mkt-buy-001` | Bob Buyer | `bob.buyer@mkt.test` | `buyer` |
| `mkt-mod-001` | Maya Mod | `maya.mod@mkt.test` | `moderator` |
| `mkt-buy-002` | Carlos Buyer | `carlos.buyer@mkt.test` | `buyer` |
| `mkt-smk-001` | Smoke Bot | `smoke@mkt.test` | `smoke` |

Seed password (all): `Mkt@seed2026!`  
Seed listing: `mkt-sel-001` owns listing `"Vintage Camera"` · $149.99 · category `"Electronics"` · status `active`.  
Seed conversation: `mkt-buy-001` ↔ `mkt-sel-001` on the seed listing, status `open`.

---

## 7. Screen / Component Map

### 7.1 Web (Next.js)

| Route | Screen / Page | Key Components |
|---|---|---|
| `/login` | LoginPage | `<LoginForm>`, `<LogoHeader>` |
| `/` | MarketplaceFeed | `<ListingGrid>`, `<CategoryFilter>`, `<SearchBar>`, `<PriceRangeSlider>` |
| `/listings/[id]` | ListingDetail | `<ListingImages>`, `<ListingInfo>`, `<SellerCard>`, `<ContactButton>` |
| `/conversations` | ConversationList | `<ConversationItem>`, `<ConversationStatusBadge>` |
| `/conversations/[id]` | ConversationThread | `<MessageList>`, `<MessageComposer>`, `<CallButton>`, `<ListingContextCard>` |
| `/listings/new` | CreateListing | `<ListingForm>`, `<ImageUploader>` |
| `/listings/[id]/edit` | EditListing | `<ListingForm>` (pre-populated) |
| `/admin/users` | AdminUsers | `<UserTable>`, `<BanToggle>` |
| `/admin/moderation` | AdminModeration | `<FlaggedConversations>`, `<RemoveListingButton>` |
| `*` | 404Page | `<NotFound>` |

Shared layout: `<Navbar>` (role-aware nav links), `<ToastProvider>`, `<CometChatProvider>` (SDK init wrapper).

---

### 7.2 Mobile / Native (React Native + Expo)

| Screen | Navigator | Key Components |
|---|---|---|
| `LoginScreen` | AuthStack | `<TextInput>`, `<PrimaryButton>`, `<LogoImage>` |
| `FeedScreen` | BottomTab: Marketplace | `<ListingFlatList>`, `<CategoryChips>`, `<SearchInput>` |
| `ListingDetailScreen` | Stack (from Feed) | `<ImageCarousel>`, `<PriceLabel>`, `<SellerRow>`, `<ContactFAB>` |
| `ConversationListScreen` | BottomTab: Messages | `<ConversationRow>`, `<UnreadBadge>` |
| `ConversationThreadScreen` | Stack (from ConvList or ListingDetail) | `<MessageBubble>`, `<ComposerBar>`, `<CallIconButton>` |
| `CallScreen` | Modal (over any screen) | `<CometChatCallUI>`, `<EndCallButton>`, `<MuteButton>` |
| `CreateListingScreen` | BottomTab: Sell (seller only) | `<TextInput fields>`, `<ImagePickerGrid>`, `<SubmitButton>` |
| `ProfileScreen` | BottomTab: Profile | `<AvatarUpload>`, `<RoleBadge>`, `<LogoutButton>` |
| `AdminDashboardScreen` | Admin drawer (admin/mod only) | `<StatCard>`, `<QuickActionList>` |

Navigation root: `<NavigationContainer>` → `AuthStack` (pre-login) or `AppTabs` (post-login, role-gated).  
Global providers: `<CometChatProvider>` (mounted after login token received), `<ThemeProvider>`.

---

*End of SPEC-PIN · mkt · req:baseline*
