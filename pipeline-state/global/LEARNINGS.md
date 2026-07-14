# GLOBAL LEARNINGS — reusable across every use case

## CometChat provisioning: avatar:null breaks user creation (2026-07-14)
Backend create-user must OMIT `avatar` when the user has none — CometChat rejects `avatar: null`
(HTTP 400 "The avatar must have a value"), which silently leaves the user with an empty auth token and
unable to chat / "user not found" for others. Duplicate uid returns 400 `ERR_UID_ALREADY_EXISTS`, not 409.

## Flutter v6 calling: the working pattern (2026-07-14)
Raw `cometchat_calls_sdk` + custom widgets + `Navigator.of(context, rootNavigator: true)`; lazy Calls-SDK
init on the call path (eager init hijacks incoming calls); `await CometChatCalls.getLoggedInUser()` (async —
the `!= null` guard on the Future silently skipped login → "User auth token is null"); resolve the incoming
caller name via `getUser(uid)`. The kit's `CometChatCallButtons`/`CallNavigationContext` no-op under go_router.
