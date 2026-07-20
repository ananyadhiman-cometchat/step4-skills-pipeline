# Flutter calling — session never released ("Call busy" forever)

**Handoff to the agent working the Flutter delivery app.**
Reference implementation: `runs/com/app/lib/cometchat/` (UC2 `com`, Flutter v6 + raw `cometchat_calls_sdk`),
where this exact class of bug was diagnosed and fixed end-to-end (android ↔ iOS calls connect).

---

## 0. Two corrections to the problem statement before you start

**(a) `clearActiveCall` is the wrong fix.** It exists on the Flutter SDK, but read what it does:

```dart
// cometchat_sdk-5.0.5/lib/main/cometchat.dart:3571
/// Clears the LOCALLY stored active call session.
static Future<void> clearActiveCall() async { ... }
```

It clears a **device-local** cache. Your own diagnosis says the stale state "lives on CometChat's servers,
not the device" — and that is correct, which is precisely why `clearActiveCall` cannot fix it. If you add it
and test on a freshly-wiped device, you will see the busy state persist and conclude the fix failed. It
didn't fail; it was never the right call.

**The server-side terminators are:**

| API | Use when |
|---|---|
| `CometChat.endCall(sessionId, onSuccess:, onError:)` | A session was **joined** (ongoing/connected) and must be torn down |
| `CometChat.rejectCall(sessionId, CometChatCallStatus.rejected, ...)` | Callee declines a **ringing** call |
| `CometChat.rejectCall(sessionId, CometChatCallStatus.cancelled, ...)` | Caller abandons their **own unanswered** ringing call |

`CometChatCallStatus` values (verified, `lib/utils/constants.dart:57`): `initiated`, `ongoing`,
`unanswered`, `rejected`, `busy`, `cancelled`, `ended`.

**(b) `ccCallEnded` / `ccCallRejected` are UI-Kit event-bus names, not the SDK's.** On the raw Flutter Chat
SDK the surface you want is `CallListener` (`CometChat.addCallListener(id, this)`), whose callbacks are
`onIncomingCallReceived`, `onIncomingCallCancelled`, `onOutgoingCallAccepted`, `onOutgoingCallRejected`,
`onCallEndedMessageReceived`. Grepping `lib/` for `ccCallEnded` will always return zero on a raw-SDK app and
tells you nothing about whether termination is wired.

---

## 1. The proven core fix — one idempotent teardown, fanned in from every exit

This is the shape that works in `com`
(`runs/com/app/lib/cometchat/call_buttons_widget.dart:248-293`). Copy the structure, not just the body.

```dart
class _OngoingCallScreenState extends State<OngoingCallScreen>
    implements SessionStatusListeners, ButtonClickListeners {
  CallSession? _session;
  bool _popped = false;                      // ← idempotency guard: teardown fires from 5+ paths

  Future<void> _endAndPop() async {
    if (_popped) return;
    _popped = true;

    // 1. leave the WebRTC session (Calls SDK)
    try { await _session?.leaveSession(); } catch (_) {}

    // 2. release the session SERVER-SIDE (Chat SDK) — this is the step whose
    //    absence pins the session and makes every later call return busy.
    try {
      final c = Completer<void>();
      CometChat.endCall(widget.sessionId,
          onSuccess: (_) { if (!c.isCompleted) c.complete(); },
          onError:   (_) { if (!c.isCompleted) c.complete(); });   // swallow: never block the pop
      await c.future;
    } catch (_) {}

    if (mounted) Navigator.of(context, rootNavigator: true).pop();
  }

  // Fan EVERY terminal signal into the one path:
  @override void onSessionLeft()                => _endAndPop();
  @override void onConnectionClosed()           => _endAndPop();
  @override void onSessionTimedOut()            => _endAndPop();
  @override void onLeaveSessionButtonClicked()  => _endAndPop();
}
```

Two things make this work and are easy to drop:

- **`_popped` guard.** `onLeaveSessionButtonClicked` → `leaveSession()` → `onSessionLeft` means the happy
  path re-enters teardown. Without the guard you double-`endCall` and double-`pop` (pops the caller's
  underlying route too — looks like a random navigation bug).
- **Errors are swallowed, not propagated.** `endCall` legitimately errors when the peer ended first. If you
  let that reject, the screen never pops and the user force-quits — which recreates the exact bug you're fixing.

Register the listeners where the session is created, and remove them in `dispose()`:

```dart
_session = CallSession.getInstance();
_session?.addSessionStatusListener(this);
_session?.addButtonClickListener(this);
```

---

## 2. The gap `com` did NOT close — you must, because it is your headline symptom

Be aware: `com`'s `dispose()` only removes listeners. **It does not end the call.** So in `com`, a caller who
hits the Android back button (or swipes back) while ringing pops the route with the session still live.

That is the "unanswered call whose caller navigates away" case in your problem statement — so **copying `com`
verbatim will not fully fix you.** Add the two guards `com` lacks:

```dart
// a) intercept back / swipe-back so teardown always runs before the route leaves
@override
Widget build(BuildContext context) {
  return PopScope(
    canPop: _popped,                            // only allow the pop we ourselves perform
    onPopInvokedWithResult: (didPop, _) { if (!didPop) _endAndPop(); },
    child: Scaffold(/* ...existing call UI... */),
  );
}

// b) last-resort net: if the route is torn down any other way, still release the session
@override
void dispose() {
  _session?.removeSessionStatusListener(this);
  _session?.removeButtonClickListener(this);
  if (!_popped) {
    _popped = true;
    _session?.leaveSession();
    CometChat.endCall(widget.sessionId, onSuccess: (_) {}, onError: (_) {});  // fire-and-forget
  }
  super.dispose();
}
```

`dispose()` cannot `await`, so (b) is fire-and-forget — correct here, since the HTTP call outlives the
widget. (b) alone is not enough: `PopScope` is what gives the request time to actually leave the device.

**Caller abandons a ringing call.** If the callee never accepted, the caller's correct terminator is
`rejectCall(sessionId, CometChatCallStatus.cancelled)`, not `endCall` — track whether
`onOutgoingCallAccepted` fired and branch on it. Using `endCall` on a never-joined session is what leaves the
`initiated` state dangling.

**Callee declines.** `com` gets this right already
(`incoming_call_widget.dart:122-128`) — `CometChat.rejectCall(sessionId, CometChatCallStatus.rejected, ...)`,
and it clears local UI state in **both** `onSuccess` and `onError` so a failed reject can't wedge the overlay.

---

## 3. Process death / force-quit — the one case no client-side code can fix

`PopScope` + `dispose` do not run on SIGKILL. There is no Dart hook that does. Two honest options:

1. **Accept it and add a recovery path** (recommended, cheap): on app start, after login, sweep for a
   dangling session and clear it.

   ```dart
   final active = await CometChat.getActiveCall();      // returns Call?
   if (active?.sessionId != null) {
     CometChat.endCall(active!.sessionId!, onSuccess: (_) {}, onError: (_) {});
   }
   ```

   This is also your **unblock for pairs that are already stuck** — no rebuild needed on the peer's device.

2. **Server-side call timeout**, configured in the CometChat dashboard, so orphaned sessions expire instead
   of pinning forever. This is the only thing that covers a device that force-quit and never came back.

> I have not verified option 1 against a genuinely server-pinned session — `getActiveCall()` may return the
> local record rather than the server's. If it returns `null` while the peer still gets `busy`, fall back to
> the CometChat **REST API** to end the session by id (check current docs for the exact endpoint — do not
> guess it). Confirm which of the two actually clears the state before you write it up as fixed.

---

## 4. Why your gates missed it, and what to add

Your read is right: every check asserts *setup*, none asserts *lifecycle*. A static grep can't catch this —
the assertion has to be behavioural:

- **Gate: a second call succeeds.** Place a call, end it, place another to the same pair. This is the single
  highest-value assertion and it directly encodes the bug.
- **Gate: interrupted call self-heals.** Place a call, kill the app mid-ring, relaunch, place another. Passes
  only once §3's recovery sweep exists.
- **Gate: no `initiateCall` without a reachable terminator.** Cheap static backstop — if `lib/` contains
  `initiateCall` but no `endCall`/`rejectCall`, fail.

Note that "Call busy instantly + peer presence `offline`" is a **clean signature for a stale session** —
worth asserting on directly, since it distinguishes this from a real concurrent call.

---

## 5. Scope note on web

Your web diagnosis (no `RTCPeerConnection`, `startSession()` unreachable) is a **different defect** and this
document does not address it. Do not expect the Flutter fix to move web. Related known-good reference for the
go_router-shaped web/Flutter navigation trap is in `pipeline-state/gaps/com.md` (the
`CometChatCallButtons` + `CallNavigationContext.navigatorKey` silent no-op under `MaterialApp.router`).

---

## 6. Checklist

- [ ] Remove any `clearActiveCall` you added expecting it to fix busy state (§0a)
- [ ] Single idempotent `_endAndPop()`: `leaveSession()` → `CometChat.endCall()` → `pop()` (§1)
- [ ] `_popped` guard; all `endCall` errors swallowed (§1)
- [ ] All four `SessionStatusListeners`/`ButtonClickListeners` terminal callbacks fan into it (§1)
- [ ] `PopScope` + `dispose()` net for back/swipe-away — **the part `com` is missing** (§2)
- [ ] Caller-abandons-ringing uses `cancelled`, not `endCall` (§2)
- [ ] Callee decline uses `rejectCall(..., rejected)`, clearing UI on both success and error (§2)
- [ ] Startup recovery sweep via `getActiveCall()` — also unblocks already-stuck pairs (§3)
- [ ] Verified which of `getActiveCall()` / REST actually clears a server-pinned session (§3)
- [ ] Gate: second call to the same pair succeeds after the first ends (§4)
- [ ] Gate: call survives app-kill mid-ring, next call still works (§4)
