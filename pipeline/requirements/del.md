# SPEC-PIN · Delivery (del) · req:baseline

> **Binding spec.** All platforms (web/Angular, mobile/Android Compose v6, iOS/Swift, backend/Node) MUST conform.  
> Last updated: 2026-07-14 · Author: req:baseline

---

## 1. Product Summary

Delivery is a last-mile logistics coordination platform where dispatchers assign parcels to couriers, customers track their shipments in real time, and all parties communicate via in-app messaging and audio/video calls.  
Admins manage the fleet and customer base; dispatchers orchestrate order fulfilment; couriers update parcel status on the go; customers follow their delivery and contact support.

---

## 2. RBAC Roles

| Role | UID prefix | Permissions |
|---|---|---|
| `admin` | `del-adm-` | Full platform access: manage users, parcels, routes; view all conversations; access audit logs |
| `dispatcher` | `del-dsp-` | Assign/reassign parcels to couriers; view all active deliveries; message any courier or customer |
| `courier` | `del-cur-` | View own assigned parcels; update parcel status; message assigned customers and dispatchers |
| `customer` | `del-cus-` | View own parcel(s) and delivery status; message the assigned courier or support; initiate calls |
| `smoke` *(login-smoke)* | `del-smk-` | Minimal read-only access for automated login health checks; no write operations permitted |

---

## 3. Core Entities + Data Model

### users
| Field | Type | Notes |
|---|---|---|
| `uid` | `VARCHAR(64)` PK | CometChat UID, prefixed per role |
| `name` | `VARCHAR(128)` | Display name |
| `email` | `VARCHAR(256)` UNIQUE | Auth credential |
| `password_hash` | `VARCHAR(256)` | bcrypt |
| `role` | `ENUM(admin,dispatcher,courier,customer,smoke)` | |
| `avatar_url` | `TEXT` | Nullable |
| `phone` | `VARCHAR(32)` | Nullable; used for courier contact |
| `status` | `ENUM(active,inactive,suspended)` DEFAULT `active` | |
| `created_at` | `TIMESTAMPTZ` | |

### parcels
| Field | Type | Notes |
|---|---|---|
| `id` | `UUID` PK | |
| `tracking_number` | `VARCHAR(32)` UNIQUE | Human-readable, e.g. `DEL-20260714-001` |
| `customer_uid` | `VARCHAR(64)` FK→users | Recipient |
| `courier_uid` | `VARCHAR(64)` FK→users | Nullable until assigned |
| `dispatcher_uid` | `VARCHAR(64)` FK→users | Assigned dispatcher |
| `status` | `ENUM(pending,assigned,in_transit,out_for_delivery,delivered,failed)` DEFAULT `pending` | |
| `description` | `TEXT` | Package description |
| `declared_value` | `VARCHAR(32)` | Money as STRING, e.g. `"19.99"` |
| `pickup_address` | `TEXT` | |
| `delivery_address` | `TEXT` | |
| `estimated_delivery` | `TIMESTAMPTZ` | ISO-8601 UTC |
| `delivered_at` | `TIMESTAMPTZ` | Nullable |
| `created_at` | `TIMESTAMPTZ` | |

### parcel_events
| Field | Type | Notes |
|---|---|---|
| `id` | `UUID` PK | |
| `parcel_id` | `UUID` FK→parcels | |
| `actor_uid` | `VARCHAR(64)` FK→users | Who triggered the event |
| `event_type` | `ENUM(created,assigned,picked_up,in_transit,out_for_delivery,delivered,failed,note_added)` | |
| `note` | `TEXT` | Nullable |
| `occurred_at` | `TIMESTAMPTZ` | |

### routes
| Field | Type | Notes |
|---|---|---|
| `id` | `UUID` PK | |
| `courier_uid` | `VARCHAR(64)` FK→users | |
| `date` | `DATE` | Scheduled delivery date |
| `parcel_ids` | `UUID[]` | Ordered list of parcel IDs |
| `status` | `ENUM(planned,active,completed)` DEFAULT `planned` | |
| `created_by_uid` | `VARCHAR(64)` FK→users | Dispatcher who built the route |
| `created_at` | `TIMESTAMPTZ` | |

---

## 4. Key User Flows

### 4.1 Login → Conversation → Message → Call (fixed harness flow)
1. User opens the app and lands on the **Login** screen.
2. User enters email + password (or taps a role quick-fill button) and submits.
3. Backend returns a JWT + CometChat auth token; client logs into CometChat SDK with the auth token.
4. User navigates to the **Conversations** screen and opens a 1:1 conversation with another user.
5. User types and sends a text message; it is delivered in real time via CometChat.
6. User taps the call button to initiate an audio/video call; the callee receives a call notification and answers.

### 4.2 Dispatcher assigns a parcel
1. Dispatcher logs in → opens the **Parcels** list → filters by `status=pending`.
2. Selects a parcel → taps **Assign** → picks a courier from the active-courier list.
3. Backend updates parcel `status→assigned`, `courier_uid`, logs a `parcel_events` row.
4. Dispatcher can open the parcel's linked conversation to message the courier directly.

### 4.3 Courier updates delivery status
1. Courier logs in → sees **My Route** with assigned parcels.
2. Taps a parcel → selects new status (e.g. `out_for_delivery`) → optionally adds a note.
3. Backend updates parcel + appends `parcel_events` row.
4. Customer sees status change on the **Track My Delivery** screen.

### 4.4 Customer tracks and contacts courier
1. Customer logs in → **My Parcel** screen shows current status, ETA, and event timeline.
2. Taps **Message Courier** → opens a CometChat 1:1 conversation with the assigned courier.
3. Taps **Call Courier** → initiates an audio call.

---

## 5. REST API Contract

### Shared skeleton (CANONICAL — do not reinvent)

**Base path:** `/api`  
**Client `API_URL` convention:** scheme://host:port with NO path suffix. The client appends the full route itself (`{API_URL}/api/auth/login`). Never bake `/api` into `API_URL` — a base ending in `/api` yields a fatal double `/api/api/...` 404. For Angular served behind the nginx `/api` proxy, `API_URL` is EMPTY so calls are relative (`/api/...`).

```
GET  /api/health
→ 200  {"status":"ok"}

POST /api/auth/login
Body: {"email":"<str>","password":"<str>"}
→ 200  {"token":"<jwt>","cometchat_auth_token":"<str>","user":{"uid":"<str>","name":"<str>","role":"<str>","avatar_url":"<str|null>"}}

POST /api/auth/signup
Body: {"email":"<str>","password":"<str>","name":"<str>","role":"<str>"}
→ 201  (same shape as login)

Authorization: Bearer <jwt>   // all authenticated endpoints
Subject claim = user uid

GET  /api/<resource>?page=1&limit=20
→ 200  {"data":[...],"pagination":{"page":1,"limit":20,"total":<int>}}

GET  /api/<resource>/{id}
→ 200  <bare object>

Errors (non-2xx):
→ {"detail":"<message>"}
  401 unauthenticated · 403 forbidden · 404 not found · 422 validation error
```

Money fields serialized as JSON STRINGS (`"19.99"`). Timestamps as ISO-8601 UTC. UIDs prefixed `del-`.

---

### Delivery-specific endpoints

```
# Parcels
GET    /api/parcels?page&limit&status&courier_uid&customer_uid
→ paginated list; each item: full parcel object (declared_value as STRING)

GET    /api/parcels/{id}
→ bare parcel object

POST   /api/parcels
Body: {description, declared_value (STRING), pickup_address, delivery_address, customer_uid, estimated_delivery (ISO-8601)}
→ 201 bare parcel object; status defaults to "pending"
Auth: admin, dispatcher

PATCH  /api/parcels/{id}
Body (partial): {status, courier_uid, note}
→ 200 updated parcel; side-effect: appends parcel_events row
Auth: admin, dispatcher (all fields); courier (status + note only for own parcel)

# Parcel events (timeline)
GET    /api/parcels/{id}/events?page&limit
→ paginated list of parcel_event objects

# Routes
GET    /api/routes?page&limit&courier_uid&date
→ paginated list

GET    /api/routes/{id}
→ bare route object with parcel_ids array

POST   /api/routes
Body: {courier_uid, date (YYYY-MM-DD), parcel_ids: [uuid, ...]}
→ 201 bare route object
Auth: admin, dispatcher

PATCH  /api/routes/{id}
Body (partial): {status, parcel_ids}
→ 200 updated route
Auth: admin, dispatcher; courier (status only for own route)
```

---

## 6. Namespaced Seed

**Shared seed password:** `Seed1234!`

| uid | email | name | role |
|---|---|---|---|
| `del-adm-001` | `admin@del.io` | Priya Admins | admin |
| `del-dsp-001` | `dispatch@del.io` | Omar Dispatch | dispatcher |
| `del-cur-001` | `courier@del.io` | Lena Courier | courier |
| `del-cus-001` | `customer@del.io` | Sam Customer | customer |
| `del-smk-001` | `smoke@del.io` | Smoke User | smoke |
| `del-cha-001` | `chat-a@del.io` | Chat User A | customer |
| `del-chb-001` | `chat-b@del.io` | Chat User B | customer |

**Automated-call-test users (harness-fixed, all use cases):**
- `chat-a@del.io` / uid `del-cha-001` — ordinary customer; password = `Seed1234!`
- `chat-b@del.io` / uid `del-chb-001` — ordinary customer; password = `Seed1234!`

Both can open a 1:1 CometChat conversation with each other. Include a seed parcel assigned between them so the conversation context is meaningful.

---

## 7. Screen / Component Map

### 7.1 Web — Angular

| Screen | Route | Key components | Notes |
|---|---|---|---|
| Login | `/login` | `LoginComponent` | `data-testid="email-input"`, `data-testid="password-input"`, `data-testid="login-submit"`; quick-fill buttons with visible text `Admin`, `Dispatcher`, `Courier`, `Customer` |
| Dashboard | `/dashboard` | `DashboardComponent` | Role-aware summary cards (parcel counts by status, active routes) |
| Parcels list | `/parcels` | `ParcelListComponent` | Paginated table; filter by status/role; Admin+Dispatcher see all; Courier sees own; Customer sees own |
| Parcel detail | `/parcels/:id` | `ParcelDetailComponent` | Status badge, event timeline, assign/status-update actions per role |
| Routes | `/routes` | `RouteListComponent` | Dispatcher+Admin only; create/edit routes |
| Conversations | `/chat` | `CometChatConversationsComponent` | CometChat Angular UIKit v6; 1:1 and group chats |
| Track parcel | `/track/:id` | `TrackComponent` | Customer-facing; status + ETA + event feed; **Message Courier** and **Call Courier** buttons |
| Profile | `/profile` | `ProfileComponent` | Edit name, avatar |

### 7.2 Mobile — Android Compose (v6)

| Screen | Composable | Key semantics / testTags | Notes |
|---|---|---|---|
| Login | `LoginScreen` | `testTag("email-input")`, `testTag("password-input")`, `testTag("login-submit")` | Quick-fill buttons labelled `Admin`, `Dispatcher`, `Courier`, `Customer` |
| Home / Dashboard | `HomeScreen` | — | Role-filtered summary cards |
| Parcel list | `ParcelListScreen` | — | RecyclerView-style lazy column; pull-to-refresh |
| Parcel detail | `ParcelDetailScreen` | — | Status stepper + event timeline; PATCH actions |
| Route list | `RouteListScreen` | — | Dispatcher+Admin only |
| Conversations | `ChatScreen` | — | CometChat Android UIKit v6 `CometChatConversations` |
| Track parcel | `TrackScreen` | — | Customer view; CTA buttons to message/call courier |
| Profile | `ProfileScreen` | — | |

### 7.3 Mobile — iOS (Swift / UIKit/SwiftUI)

| Screen | Controller / View | Accessibility IDs | Notes |
|---|---|---|---|
| Login | `LoginViewController` | `accessibilityIdentifier = "email-input"` / `"password-input"` / `"login-submit"` | Quick-fill buttons: `Admin`, `Dispatcher`, `Courier`, `Customer` |
| Dashboard | `DashboardViewController` | — | Role-gated tiles |
| Parcel list | `ParcelListViewController` | — | UITableView; role-filtered |
| Parcel detail | `ParcelDetailViewController` | — | Status stepper + timeline |
| Route list | `RouteListViewController` | — | Dispatcher+Admin only |
| Conversations | `ChatViewController` | — | CometChat iOS UIKit v5 `CometChatConversations` |
| Track parcel | `TrackViewController` | — | Customer view |
| Profile | `ProfileViewController` | — | |

---

*End of SPEC-PIN for use case `del`.*
