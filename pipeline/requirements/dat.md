# dat — Dating App · SPEC-PIN

## 1. Product Summary

**Dating** is a mobile-first platform where Members create rich profiles, discover other Members, and build mutual matches through a like system. Matches unlock 1:1 chat and calls via CometChat. Admins and Moderators keep content safe; Guests can browse active profiles before signing up.

---

## 2. RBAC Roles

| Role | Permissions |
|---|---|
| **admin** | Full CRUD on all entities and users; can promote roles, archive any profile, block any match |
| **moderator** | View all profiles (all statuses); pause/archive any profile; view and block any match |
| **member** | Full CRUD on own profile; send likes; list/edit/delete own matches; chat with matches |
| **guest** | Read-only list + detail of `active` profiles; no like/match/chat; redirected to login on interaction |

Login-smoke role: **member** (uid `dat-mem-001`, email `member1@dat.io`).

---

## 3. Core Entities + Data Model

### 3.1 Profile

A Member's public dating presence; the primary browsable entity.

| Field | Type | Notes |
|---|---|---|
| `id` | string | UID prefix `dat-pro-` |
| `owner_uid` | string → User | FK to owning member |
| `display_name` | string | Public name (max 60 chars) |
| `bio` | string | Free-text (max 500 chars) |
| `age` | int | 18–99 |
| `location` | string | City / region |
| `interests` | string[] | Tags e.g. `["hiking","coffee"]` |
| `image_url` | string | Primary photo URL |
| `extra_images` | string[] | 0–4 additional photo URLs |
| `status` | enum | `draft` · `active` · `paused` · `archived` |
| `created_at` | ISO-8601 UTC | |
| `updated_at` | ISO-8601 UTC | |

**State machine:**
```
draft ──► active ──► paused ──► active   (toggle pause)
     │         └──► archived             (terminal)
     └──────────────► archived           (discard draft)
```

### 3.2 Match

A mutual connection between two Members, created automatically when both have liked each other.

| Field | Type | Notes |
|---|---|---|
| `id` | string | UID prefix `dat-mat-` |
| `initiator_uid` | string → User | Who liked first |
| `receiver_uid` | string → User | Who liked back |
| `profile_a_id` | string → Profile | Initiator's profile |
| `profile_b_id` | string → Profile | Receiver's profile |
| `chat_conversation_id` | string | CometChat 1:1 conversation UID (set when status→active) |
| `match_note` | string | Optional note either party can set (max 200 chars) |
| `status` | enum | `pending` · `active` · `unmatched` · `blocked` |
| `created_at` | ISO-8601 UTC | |
| `updated_at` | ISO-8601 UTC | |

**State machine:**
```
pending ──► active ──► unmatched   (either party unmatch)
                  └──► blocked      (moderator or admin)
```
`pending` means one side liked; `active` means mutual like confirmed.

### 3.3 CRUD Matrix

| Entity | Create | List | Detail | Edit | Delete / Archive |
|---|---|---|---|---|---|
| **Profile** | member (own) · admin | member (own) · moderator · admin · guest (`active` only) | member · moderator · admin · guest (`active` only) | member (own) · admin | member (own → `archived`) · moderator → `paused`/`archived` · admin |
| **Match** | member (via like endpoint) · admin (direct) | member (own both sides) · moderator · admin | member (own) · moderator · admin | member (own: `match_note`) · admin | member (own → `unmatched`) · moderator (→ `blocked`) · admin |

---

## 4. Key User Flows

### 4.1 Member — Full CRUD on Profile + Match

1. **Create Profile**: Login → "Create My Profile" → fill `display_name`, `bio`, `age`, `location`, `interests`, upload primary photo → Save → profile status = `draft`.
2. **Publish**: Open Profile detail → "Go Live" → status transitions to `active` (visible in Discover).
3. **Browse Discover**: Navigate to Discover feed → paginated list of `active` profiles. Open a profile detail to read bio/photos.
4. **Like / Initiate Match**: Tap "Like" on a profile → `POST /api/profiles/{id}/like`. If mutual, server creates a Match (`pending`→`active`) and returns `match_created: true`.
5. **List Matches**: Navigate to Matches tab → paginated list of own active matches with both profile thumbnails.
6. **Edit Match Note**: Open match detail → edit `match_note` field → Save → `PATCH /api/matches/{id}`.
7. **Unmatch**: Tap "Unmatch" on match detail → confirm dialog → `PATCH /api/matches/{id}/status` `{status:"unmatched"}`. Match disappears from list.
8. **Pause Profile**: Own Profile → "Pause" → status = `paused` (hidden from Discover; still editable).
9. **Archive Profile**: Own Profile → "Delete Profile" → confirm dialog → status = `archived` (terminal; data retained for moderation).

### 4.2 Admin — Full Control

1. Login as `admin@dat.io`.
2. Admin Dashboard → Profile table (all statuses). Open any profile detail.
3. Edit any profile bio/image → Save.
4. Archive a violating profile (`DELETE /api/profiles/{id}`).
5. Create a seed match directly (`POST /api/matches` with `initiator_uid` + `receiver_uid`).
6. Block an existing match (`PATCH /api/matches/{id}/status {status:"blocked"}`).

### 4.3 Moderator — Content Safety

1. Login as `moderator@dat.io`.
2. Moderator Panel → filter profiles by `active`. Open a flagged profile detail.
3. Pause profile (`PATCH /api/profiles/{id}/status {status:"paused"}`).
4. Navigate to Matches list → open a reported match detail.
5. Block the match (`PATCH /api/matches/{id}/status {status:"blocked"}`).

### 4.4 Guest — Browse Only

1. Open app without login → Discover feed of `active` profiles (read-only).
2. Open a profile detail (bio + photos visible).
3. Tap "Like" or "Match" → Login/Signup wall shown.

### 4.5 Fixed Automation Flow (all clients)

1. Login as `chat-a@dat.io` (uid `dat-cha-001`).
2. Navigate to Matches → open the match with `dat-chb-001` (match `dat-mat-001`, status `active`).
3. Open the CometChat conversation panel.
4. Send TEXT message: `"Hey, great to meet you!"`.
5. Send IMAGE message: attach bundled asset `assets/images/test_image.jpg` (or a stable image URL).
6. Tap the Call button to initiate a CometChat audio/video call.

---

## 5. REST API Contract

### Shared canonical skeleton

```
Base path: /api

GET  /api/health
     → {"status":"ok"}

POST /api/auth/login         body {email, password}
POST /api/auth/signup        body {email, password, name}
     → {token, cometchat_auth_token, user:{uid, name, role, avatar_url}}
     Bearer JWT — Authorization: Bearer <token>; subject = user uid

GET  /api/<resource>?page=1&limit=20
     → {"data":[...], "pagination":{"page","limit","total"}}

GET    /api/<resource>/{id}   → bare object
POST   /api/<resource>        → 201 created object
PATCH  /api/<resource>/{id}   → updated object
DELETE /api/<resource>/{id}   → 204

Errors: {"detail":"<message>"} + correct HTTP status
  401 unauthenticated · 403 forbidden · 404 not found · 422 validation

Money/decimals → JSON strings. Timestamps → ISO-8601 UTC. UIDs prefix "dat-".
```

**CLIENT API_URL RULE**: `API_URL` = `scheme://host:port` — NO trailing `/api`. Client appends the full path (`{API_URL}/api/auth/login`). Web behind nginx reverse-proxy: `API_URL=""` (relative). React Native emulator default: `http://10.0.2.2:8080`. Never bake `/api` into `API_URL` — double path `/api/api/…` causes 404.

### Use-case-specific endpoints

```
# Profiles
GET    /api/profiles?page&limit&status=   list; guest sees active only; member sees own (all statuses)
POST   /api/profiles                      create (member, admin)   body: {display_name,bio,age,location,interests,image_url}
GET    /api/profiles/{id}                 detail
PATCH  /api/profiles/{id}                 edit (own member, admin)
DELETE /api/profiles/{id}                 archive — sets status=archived (own member, moderator, admin)

PATCH  /api/profiles/{id}/status          body {status: "active"|"paused"|"archived"}

# Likes (drives match creation)
POST   /api/profiles/{id}/like
       → {liked: true, match_created: bool, match_id?: string}

# Matches
GET    /api/matches?page&limit&status=    list (member: own; moderator/admin: all)
POST   /api/matches                       create directly (admin only) body: {initiator_uid, receiver_uid}
GET    /api/matches/{id}                  detail (own member, moderator, admin)
PATCH  /api/matches/{id}                  edit match_note (own member, admin)
DELETE /api/matches/{id}                  unmatch (own member) → status=unmatched

PATCH  /api/matches/{id}/status           body {status: "active"|"unmatched"|"blocked"}
```

---

## 6. Namespaced Seed

**Shared seed password**: `Seed1234!`

### Users

| uid | email | role | display_name | avatar_url |
|---|---|---|---|---|
| `dat-adm-001` | `admin@dat.io` | admin | Alex Admin | `https://i.pravatar.cc/300?u=dat-adm-001` |
| `dat-mod-001` | `moderator@dat.io` | moderator | Morgan Mod | `https://i.pravatar.cc/300?u=dat-mod-001` |
| `dat-mem-001` | `member1@dat.io` | member | Jamie Lee | `https://i.pravatar.cc/300?u=dat-mem-001` |
| `dat-mem-002` | `member2@dat.io` | member | Riley Park | `https://i.pravatar.cc/300?u=dat-mem-002` |
| `dat-gst-001` | `guest@dat.io` | guest | Guest User | `https://i.pravatar.cc/300?u=dat-gst-001` |
| `dat-cha-001` | `chat-a@dat.io` | member | Chat Alpha | `https://i.pravatar.cc/300?u=dat-cha-001` |
| `dat-chb-001` | `chat-b@dat.io` | member | Chat Beta | `https://i.pravatar.cc/300?u=dat-chb-001` |

### Profile Seed (spans all statuses)

| id | owner_uid | display_name | age | location | interests | status | image_url |
|---|---|---|---|---|---|---|---|
| `dat-pro-001` | `dat-mem-001` | Jamie Lee | 28 | San Francisco | `["hiking","coffee","travel"]` | `active` | `https://picsum.photos/seed/dat-pro-001/600/400` |
| `dat-pro-002` | `dat-mem-002` | Riley Park | 31 | New York | `["art","yoga","books"]` | `active` | `https://picsum.photos/seed/dat-pro-002/600/400` |
| `dat-pro-003` | `dat-cha-001` | Chat Alpha | 25 | Austin | `["music","gaming","cooking"]` | `active` | `https://picsum.photos/seed/dat-pro-003/600/400` |
| `dat-pro-004` | `dat-chb-001` | Chat Beta | 27 | Chicago | `["photography","cycling"]` | `active` | `https://picsum.photos/seed/dat-pro-004/600/400` |
| `dat-pro-005` | `dat-mem-001` | Jamie (Draft) | 28 | San Francisco | `["hiking"]` | `draft` | `https://picsum.photos/seed/dat-pro-005/600/400` |
| `dat-pro-006` | `dat-mem-002` | Riley (Paused) | 31 | New York | `["art"]` | `paused` | `https://picsum.photos/seed/dat-pro-006/600/400` |

### Match Seed (spans all statuses)

| id | initiator_uid | receiver_uid | profile_a_id | profile_b_id | status | match_note |
|---|---|---|---|---|---|---|
| `dat-mat-001` | `dat-cha-001` | `dat-chb-001` | `dat-pro-003` | `dat-pro-004` | `active` | `"Looking forward to chatting!"` |
| `dat-mat-002` | `dat-mem-001` | `dat-mem-002` | `dat-pro-001` | `dat-pro-002` | `active` | `""` |
| `dat-mat-003` | `dat-mem-002` | `dat-cha-001` | `dat-pro-002` | `dat-pro-003` | `pending` | `""` |
| `dat-mat-004` | `dat-mem-001` | `dat-chb-001` | `dat-pro-001` | `dat-pro-004` | `unmatched` | `""` |
| `dat-mat-005` | `dat-mem-002` | `dat-chb-001` | `dat-pro-002` | `dat-pro-004` | `blocked` | `""` |

The seed script must be **idempotent** (upsert by uid/id). It must also register all users with the CometChat SDK so their `cometchat_auth_token` is retrievable at login. Seed emails use real domain `dat.io` (not reserved TLDs; Pydantic `EmailStr` rejects `.test`/`.example`/`.invalid`/`.local`).

The `dat-mat-001` match (chat-a ↔ chat-b) must have at least one pre-seeded IMAGE message in its CometChat conversation so the thread is non-empty on first load.

---

## 7. Screen / Component Map

### Web (React)

| Screen | Route | Key Components | `data-testid` |
|---|---|---|---|
| Login | `/login` | EmailInput, PasswordInput, LoginBtn, QuickFill buttons | `email-input` · `password-input` · `login-submit`; QuickFill button text: `Admin` `Moderator` `Member` `Guest` |
| Signup | `/signup` | Same + name field | `email-input` · `password-input` · `login-submit` |
| Discover | `/discover` | ProfileCardGrid, PaginationControls, EmptyDiscover, LoadingSkeleton | — |
| Profile Detail | `/profiles/:id` | ProfileHero, ImageGallery, LikeBtn, BackBtn | — |
| My Profile | `/profile/me` | ProfileForm, StatusBadge, StatusToggle, ArchiveBtn | — |
| Matches | `/matches` | MatchList, MatchCard, EmptyMatches, LoadingSkeleton | — |
| Match Detail | `/matches/:id` | MatchHeader, ChatPanel (CometChat UIKit), EditNoteBtn, UnmatchBtn | — |
| Admin Dashboard | `/admin` | UserTable, ProfileTable, MatchTable, StatusFilter | — |
| Moderator Panel | `/moderator` | ProfileList (all statuses), PauseBtn, MatchList, BlockBtn | — |

### Mobile / Native (React Native bare)

| Screen | Key Components | `testID` |
|---|---|---|
| Login | TextInput×2, TouchableOpacity, QuickFill row | `email-input` · `password-input` · `login-submit`; QuickFill labels: `Admin` `Moderator` `Member` `Guest` |
| Discover | FlatList<ProfileCard>, LikeOverlay, EmptyDiscover | — |
| Profile Detail | ScrollView, ImageCarousel (FlatList), LikeBtn, BackBtn | — |
| Create / Edit Profile | Form (TextInput×n), ImagePicker, SaveBtn, StatusBadge | — |
| Matches | FlatList<MatchItem>, EmptyMatches, LoadingSpinner | — |
| Match Chat | CometChat MessageList + Composer, CallBtn | — |
| Admin / Mod screens | Simplified table views matching web flows | — |

---

## 8. UI States + Assets

### Placeholder image sources

| Usage | Source | Notes |
|---|---|---|
| User avatars | `https://i.pravatar.cc/300?u={uid}` | Deterministic by uid; stable |
| Profile / entity photos | `https://picsum.photos/seed/{id}/600/400` | Deterministic by seed string; stable |
| Bundled fallback | `assets/images/placeholder_profile.png` | Must exist in web `public/` and RN `assets/images/` |
| Test image (automation) | `assets/images/test_image.jpg` | Sent as IMAGE message in automation flow |

### Per-screen UI states

| Screen | Empty state | Loading state | Error state |
|---|---|---|---|
| Discover (profile list) | Copy: "No profiles here yet — be the first!" · CTA: "Create Profile" button | Shimmer skeleton grid (6 cards) | "Couldn't load profiles" + Retry button |
| My Profile (draft) | Copy: "Your profile is a draft — publish to start meeting people" · CTA: "Go Live" button | Spinner centred | "Couldn't load your profile" + Retry button |
| Matches list | Copy: "No matches yet — start liking profiles!" · CTA: "Discover" button | Shimmer skeleton list (3 rows) | "Couldn't load matches" + Retry button |
| Match detail | n/a (detail only opens from a real match) | Spinner + CometChat loading state | "Couldn't load this match" + Back button |
| Admin Profile table | "No profiles found" | Table skeleton rows | "Load failed" + Retry |
| Moderator Panel | "Nothing to review — all clear!" | Spinner | "Load failed" + Retry |

### Image messages

Clients must render `MessageType.IMAGE` inline as a thumbnail bubble (not a file-download link). Use CometChat UIKit's default image message renderer. The automation flow sends one IMAGE message and expects it to appear in the thread immediately after send.
