## Delivery (del) — backend

- coverageGap: "CometChat REST API error code for duplicate user creation (POST /users with existing UID)" — `ERR_BAD_REQUEST` is confirmed from the error-guide, but was not listed under User Errors section specifically; inferred from the general errors table.
- docsEscape: REST API returns 400 `ERR_BAD_REQUEST` for duplicate UID on user create (not 409); had to cross-reference the error-guide page to confirm and cannot find explicit documentation of this specific case in the users/create page.

## Delivery (del) — ios (CometChat UIKit Swift)

- SDK-gap: CometChat's iOS **binary xcframeworks cannot be compiled on Xcode 16.4 (Swift 6.1.2)**, though
  16.4 is a current release. `CometChatSDK 4.1.6` and `CometChatUIKitSwift 5.1.16` are shipped as binary
  frameworks built with **Swift 6.2.3**; a 6.1.2 compiler rejects them with
  `failed to build module 'CometChatSDK/CometChatUIKitSwift'; this SDK is not supported by the compiler
  (built with Apple Swift 6.2.3 … while this compiler is 6.1.2). Please select a toolchain which matches
  the SDK.` The textual `.private.swiftinterface` fallback ALSO fails because it references transitive
  modules that are not exposed to the app target: `no such module 'CometChatStarscream'` (SDK's WebSocket
  lib) and `no such module 'CometChatCardsSwift'` (UIKit's cards module). Net: the iOS SDK is
  **un-compilable on this machine** regardless of app code — a hard packaging/toolchain-pinning gap that
  blocks every iOS use case here until Xcode is updated to a Swift-6.2.3 toolchain (Xcode 16.5+/26).
- staleness: the iOS UI Kit getting-started page states **Requirements: "Xcode 16+, iOS 13.0+, Swift 5.0+"**
  and pins **`pod 'CometChatUIKitSwift', '5.1.9'`** — both inaccurate for the shipped binaries. Xcode 16.4
  (Swift 6.1.2) satisfies "Xcode 16+, Swift 5.0+" yet cannot build the SDK (needs Swift 6.2.3). And the
  version story is inconsistent across THREE numbers: docs pin `5.1.9`, but `~> 5.1` resolves to `5.1.16`;
  worse, `5.1.9`'s own binary is built with **Swift 6.0.2** while its forced dependency `CometChatSDK 4.1.6`
  is built with **6.2.3** — so the documented pin is not even internally consistent. The doc should state
  the true minimum Xcode/Swift for each SDK patch (and ideally ship swiftmodules for the current stable
  Xcode, or a working swiftinterface).
