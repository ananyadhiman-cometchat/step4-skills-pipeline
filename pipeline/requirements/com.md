# SPEC-PIN · Community Forum (com) · req:baseline

> **Binding spec.** All platforms (web/Flutter web, mobile/Flutter v6, backend/PHP) MUST conform.  
> Last updated: 2026-07-09 · Author: req:baseline

---

## 1. Product Summary

Community Forum is a threaded discussion platform where authenticated members create topic threads inside categorised forums, reply with posts, and escalate to real-time direct messaging and audio/video calls without leaving the app.  
Moderators keep content healthy by pinning, closing, or removing threads and posts; admins govern the full platform including user management and forum structure.

---

## 2. RBAC Roles

| Role | UID prefix | Permissions |
|---|---|---|
| `admin` | `com-adm-` | Full platform access: manage users, forums, threads, posts; pin/close/delete any content; view audit logs |
| `moderator` | `com-mod-` | Pin/close/delete any thread or post; cannot manage users or forum structure |
| `member` | `com-mem-` | Create threads and posts; edit/delete own content; send DMs; initiate and receive calls |
| `guest` | `com-gst-` | Read-only access to public forums, threads, and posts; cannot post, DM, or call |
| `smoke` *(login-smoke)* | `com-smk-` | Minimal read-only access for automated login health checks; no write operations permitted |

---

## 3. Core Entities + Data Model

### users
| Field | Type | Notes |
|---|---|---|
| `uid` | `VARCHAR(64)` PK | CometChat UID, prefixed per role |
| `name` | `VARCHAR(128)` | Display name |
| `email` | `VARCHAR(256)` UNIQUE | Auth credential |
| `password_hash` | `VARCHAR(256)` | bcrypt |
| `role` | `ENUM(admin,moderator,member,guest,smoke)` | |
| `avatar_url` | `TEXT` | Nullable |
| `status` | `ENUM(active,banned,pending)` DEFAULT `active` | |
| `created_at` | `TIMESTAMPTZ` | |

### forums
| Field | Type | Notes |
|---|---|---|
| `id` | `UUID` PK | |
| `name` | `VARCHAR(128)` | Forum category name |
| `description` | `TEXT` | |
| `slug` | `VARCHAR(128)` UNIQUE | URL-safe identifier |
| `created_by_uid` | `VARCHAR(64)` FK→users | Admin who created it |
| `thread_count` | `INT` DEFAULT `0` | Denormalised counter |
| `created_at` | `TIMESTAMPTZ` | |

### threads
| Field | Type | Notes |
|---|---|---|
| `id` | `UUID` PK | |
| `forum_id` | `UUID` FK→forums | |
| `author_uid` | `VARCHAR(64)` FK→users | |
| `title` | `VARCHAR(256)` | |
| `body` | `TEXT` | Opening post body |
| `status` | `ENUM(open,closed,pinned,removed)` DEFAULT `open` | |
| `view_count` | `INT` DEFAULT `0` | |
| `post_count` | `INT` DEFAULT `0` | Denormalised counter |
| `created_at` | `TIMESTAMPTZ` | |
| `updated_at` | `TIMESTAMPTZ` | |

### posts
| Field | Type | Notes |
|---|---|---|
| `id` | `UUID` PK | |
| `thread_id` | `UUID` FK→threads | |
| `author_uid` | `VARCHAR(64)` FK→users | |
| `body` | `TEXT` | |
| `parent_post_id` | `UUID` FK→posts | Nullable; for nested replies |
| `status` | `ENUM(visible,removed)` DEFAULT `visible` | |
| `created_at` | `TIMESTAMPTZ` | |
| `updated_at` | `TIMESTAMPTZ` | |

### conversations *(DMs — CometChat is source of truth)*
| Field | Type | Notes |
|---|---|---|
| `id` | `VARCHAR(64)` PK | CometChat conversation ID |
| `initiator_uid` | `VARCHAR(64)` FK→users | |
| `recipient_uid` | `VARCHAR(64)` FK→users | |
| `status` | `ENUM(open,closed)` DEFAULT `open` | |
| `created_at` | `TIMESTAMPTZ` | |

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
1. **Login** — User submits email + password → backend validates → returns JWT + CometChat auth token → client initialises CometChat SDK with the auth token.
2. **Open a conversation** — Member navigates to another user's profile or clicks "Message" in a thread → `POST /api/conversations` (if new) or `GET /api/conversations/{id}` (existing) → CometChat SDK opens the 1-to-1 conversation channel.
3. **Send a message** — User types in the message composer and submits → CometChat SDK sends the message → UI appends message optimistically.
4. **Start a call** — User taps the call button inside an open conversation → client invokes CometChat Call SDK `initiateCall(type)` → recipient receives incoming call UI → on accept, call session begins; on end, duration is recorded.

### 4.2 Browse & Post Flow
Member logs in → navigates forum list (`GET /api/forums`) → opens a forum (`GET /api/forums/{id}`) → browses threads (`GET /api/threads?forum_id=`) → opens a thread (`GET /api/threads/{id}`) → reads posts (`GET /api/posts?thread_id=`) → submits a reply (`POST /api/posts`).

### 4.3 Create Thread Flow
Member logs in → opens a forum → taps "New Thread" → fills in title + body → `POST /api/threads` → thread appears in forum list.

### 4.4 Moderation Flow
Moderator or admin logs in → opens thread or post → selects "Pin", "Close", or "Remove" → `PATCH /api/threads/{id}` or `PATCH /api/posts/{id}` with updated `status` field.

### 4.5 Smoke Login Flow *(automated health check)*
smoke user hits `POST /api/auth/login` → receives `200` + valid JWT → hits `GET /api/health` → expects `{"status":"ok"}` → session ends (no writes performed).

---

## 5. REST API Contract

> Base path: `/api`  
> Auth header: `Authorization: Bearer <JWT>` (all endpoints except `/api/auth/*` and `/api/health`)  
> Content-Type: `application/json`

### Health

#### `GET /api/health`
No auth required.  
Response `200`:
```json
{ "status": "ok" }
```

---

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
Errors: `401 {"detail":"Invalid credentials"}` · `422 {"detail":"Validation error"}`

#### `POST /api/auth/signup`
Request:
```json
{ "name": "string", "email": "string", "password": "string" }
```
Response `201`: same shape as login `200`.  
Errors: `409 {"detail":"Email already registered"}` · `422 {"detail":"Validation error"}`

---

### Forums

#### `GET /api/forums?page=1&limit=20`
Response `200`:
```json
{
  "data": [{ "id": "uuid", "name": "string", "slug": "string", "description": "string",
             "thread_count": 0, "created_at": "ISO8601" }],
  "pagination": { "page": 1, "limit": 20, "total": 0 }
}
```

#### `GET /api/forums/{id}`
Response `200`: bare forum object (same fields as list item).  
Errors: `404 {"detail":"Not found"}`

#### `POST /api/forums` *(admin only)*
Request:
```json
{ "name": "string", "description": "string", "slug": "string" }
```
Response `201`: created forum object.  
Errors: `403 {"detail":"Forbidden"}` · `409 {"detail":"Slug already exists"}`

---

### Threads

#### `GET /api/threads?forum_id=&status=open&page=1&limit=20`
Response `200`:
```json
{
  "data": [{ "id": "uuid", "forum_id": "uuid", "title": "string", "status": "open",
             "view_count": 0, "post_count": 0,
             "author": { "uid": "string", "name": "string" }, "created_at": "ISO8601" }],
  "pagination": { "page": 1, "limit": 20, "total": 0 }
}
```

#### `GET /api/threads/{id}`
Response `200`: thread object including `body`.  
Errors: `404 {"detail":"Not found"}`

#### `POST /api/threads` *(member, admin)*
Request:
```json
{ "forum_id": "uuid", "title": "string", "body": "string" }
```
Response `201`: created thread object.  
Errors: `403 {"detail":"Forbidden"}`

#### `PATCH /api/threads/{id}` *(owner member for own content; mod/admin for status)*
Request: partial — any of `{ "title", "body", "status" }`.  
Response `200`: updated thread object.  
Errors: `403 {"detail":"Forbidden"}` · `404 {"detail":"Not found"}`

#### `DELETE /api/threads/{id}` *(owner or admin)*
Response `204`

---

### Posts

#### `GET /api/posts?thread_id=&page=1&limit=50`
Response `200`:
```json
{
  "data": [{ "id": "uuid", "thread_id": "uuid", "parent_post_id": "uuid|null",
             "body": "string", "status": "visible",
             "author": { "uid": "string", "name": "string", "avatar_url": "string|null" },
             "created_at": "ISO8601", "updated_at": "ISO8601" }],
  "pagination": { "page": 1, "limit": 50, "total": 0 }
}
```

#### `GET /api/posts/{id}`
Response `200`: bare post object.  
Errors: `404 {"detail":"Not found"}`

#### `POST /api/posts` *(member, admin)*
Request:
```json
{ "thread_id": "uuid", "body": "string", "parent_post_id": "uuid|null" }
```
Response `201`: created post object.  
Errors: `403 {"detail":"Forbidden"}` · `422 {"detail":"Thread is closed"}`

#### `PATCH /api/posts/{id}` *(owner for body; mod/admin for status)*
Request: partial — any of `{ "body", "status" }`.  
Response `200`: updated post object.

#### `DELETE /api/posts/{id}` *(owner or admin)*
Response `204`

---

### Conversations *(DMs)*

#### `GET /api/conversations?page=1&limit=20`
Returns only conversations where the caller is initiator or recipient (admin sees all).  
Response `200`:
```json
{
  "data": [{ "id": "string", "initiator": { "uid": "string", "name": "string" },
             "recipient": { "uid": "string", "name": "string" },
             "status": "open", "created_at": "ISO8601" }],
  "pagination": { "page": 1, "limit": 20, "total": 0 }
}
```

#### `GET /api/conversations/{id}`
Response `200`: conversation object + `cometchat_conversation_id`.  
Errors: `403 {"detail":"Forbidden"}` · `404 {"detail":"Not found"}`

#### `POST /api/conversations` *(member, admin)*
Request:
```json
{ "recipient_uid": "string" }
```
Response `201`:
```json
{ "id": "string", "cometchat_conversation_id": "string", "recipient_uid": "string" }
```
Errors: `403 {"detail":"Forbidden"}` · `409 {"detail":"Conversation already exists"}`

---

### Users *(admin only)*

#### `GET /api/users?page=1&limit=20`
Response `200`: paginated user list (uid, name, email, role, status, created_at).

#### `GET /api/users/{uid}`
Response `200`: bare user object.  
Errors: `404 {"detail":"Not found"}`

#### `PATCH /api/users/{uid}` *(admin only)*
Request: `{ "status": "active|banned" }`  
Response `200`: updated user object.

---

## 6. Namespaced Seed

All UIDs prefixed `com-`. Emails use domain `com.io`.

| UID | Name | Email | Role |
|---|---|---|---|
| `com-adm-001` | Alice Admin | `alice.admin@com.io` | `admin` |
| `com-mod-001` | Marco Mod | `marco.mod@com.io` | `moderator` |
| `com-mem-001` | Jamie Member | `jamie.member@com.io` | `member` |
| `com-mem-002` | Priya Member | `priya.member@com.io` | `member` |
| `com-gst-001` | Guest User | `guest@com.io` | `guest` |
| `com-smk-001` | Smoke Bot | `smoke@com.io` | `smoke` |

Seed password (all): `Com@seed2026!`  
Seed forum: `"General Discussion"` · slug `general` · created by `com-adm-001`.  
Seed thread: `com-mem-001` created `"Welcome to the community!"` in `general` · status `pinned`.  
Seed post: `com-mem-002` replied `"Thanks, happy to be here!"` on the seed thread.  
Seed conversation: `com-mem-001` ↔ `com-mem-002` · status `open`.

---

## 7. Screen / Component Map

### 7.1 Web (Flutter Web)

| Route | Widget / Page | Key Widgets |
|---|---|---|
| `/login` | `LoginPage` | `LoginForm`, `LogoWidget`, `ElevatedButton` |
| `/` | `ForumListPage` | `ForumListView`, `ForumCard`, `SearchBar` |
| `/forums/:id` | `ThreadListPage` | `ThreadListView`, `ThreadCard`, `NewThreadFAB`, `StatusFilterChips` |
| `/threads/:id` | `ThreadDetailPage` | `ThreadHeader`, `PostListView`, `PostCard`, `ReplyComposer`, `ModerationMenu` |
| `/conversations` | `ConversationListPage` | `ConversationListView`, `ConversationTile` |
| `/conversations/:id` | `ConversationThreadPage` | `MessageListView`, `MessageBubble`, `MessageComposer`, `CallButton` |
| `/profile/:uid` | `UserProfilePage` | `AvatarWidget`, `RoleBadge`, `MessageUserButton`, `PostHistoryList` |
| `/admin/forums` | `AdminForumsPage` | `ForumManagementTable`, `CreateForumDialog` |
| `/admin/users` | `AdminUsersPage` | `UserDataTable`, `BanToggleButton` |
| `*` | `NotFoundPage` | `NotFoundWidget` |

Shared layout: `AppShell` (role-aware `NavigationRail` on desktop, `Drawer` on narrow), `CometChatInitWidget` (SDK init after login), `SnackbarProvider`.

---

### 7.2 Mobile / Native (Flutter v6)

| Screen | Navigator | Key Widgets |
|---|---|---|
| `LoginScreen` | `AuthNavigator` | `TextFormField`, `ElevatedButton`, `LogoImage` |
| `ForumListScreen` | `BottomNavBar`: Forums | `ForumListView`, `ForumCard`, `SearchDelegate` |
| `ThreadListScreen` | `Navigator` (push from Forums) | `ThreadListView`, `ThreadCard`, `FloatingActionButton` (new thread) |
| `ThreadDetailScreen` | `Navigator` (push from ThreadList) | `ThreadHeader`, `PostListView`, `PostCard`, `ReplyTextField`, `ModerationBottomSheet` |
| `ConversationListScreen` | `BottomNavBar`: Messages | `ConversationListView`, `ConversationTile`, `UnreadBadge` |
| `ConversationThreadScreen` | `Navigator` (push from ConvList or Profile) | `CometChatMessageList`, `CometChatMessageComposer`, `CallIconButton` |
| `CallScreen` | `FullScreenRoute` (modal) | `CometChatCallScreen`, `EndCallButton`, `MuteButton`, `FlipCameraButton` |
| `UserProfileScreen` | `Navigator` (push from any post/thread) | `AvatarWidget`, `RoleBadge`, `MessageButton`, `PostHistoryList` |
| `AdminDashboardScreen` | `DrawerNavigator` (admin/mod only) | `StatCard`, `ForumManagerList`, `UserManagerList` |
| `SettingsScreen` | `BottomNavBar`: Profile | `AvatarUpload`, `DisplayNameField`, `LogoutButton` |

Navigation root: `MaterialApp.router` → `AuthNavigator` (pre-login) or `AppShell` with `BottomNavigationBar` (post-login, role-gated).  
Global providers: `CometChatProvider` (mounted after JWT received), `ThemeProvider`, `GoRouter`.

---

*End of SPEC-PIN · com · req:baseline*
