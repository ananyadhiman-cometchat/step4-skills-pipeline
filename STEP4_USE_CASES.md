# Step 4 — Final Use-Case Set (10 runs · tri-platform)

> The locked use-case matrix for the Iterative Skills Reviewer Step 4 sweep. **Every use case ships on all three platforms — web + Android + iOS.** Frontend tech is varied *across* the set so the whole `cometchat-skills` catalog is exercised. Companion to [STEP4_PIPELINE.md](STEP4_PIPELINE.md).

## Runs

Where a cross-platform framework fills more than one cell, it's **one codebase** for those platforms (Flutter → all 3; React Native → Android+iOS). Native cells (Kotlin/Compose, Swift) are separate codebases.

| # | Use case | Web | Android | iOS | Backend | Codebases | Frontend skills |
|---|---|---|---|---|---|:---:|---|
| 1 | Marketplace | Next.js | React Native (Expo) | React Native (Expo) | Python | 2 | `nextjs-patterns`, `native-expo` |
| 2 | Community forum | Flutter v6 | Flutter v6 | Flutter v6 | PHP | 1 | `flutter-v6` |
| 3 | Delivery | Angular | Android Compose (v6) | iOS (Swift) | Node | 3 | `angular`, `android-v6-compose`, `ios` |
| 4 | Dating | React | React Native (bare) | React Native (bare) | Python | 2 | `react`, `native-bare` |
| 5 | Fintech support | Vue 3 | Android Compose (v6) | iOS (Swift) | Java (Spring) | 3 | **`vue` (gap)**, `android-v6-compose`, `ios` |
| 6 | Creator community | Astro | Android Kotlin (v5) | iOS (Swift) | Go | 3 | `astro-patterns`, `android-v5`, `ios` |
| 7 | Field-service | Flutter v5 | Flutter v5 | Flutter v5 | PHP | 1 | `flutter-v5` |
| 8 | Real-estate | Angular | Android Kotlin (v5) | iOS (Swift) | Golang | 3 | `angular`, `android-v5`, `ios` |
| 9 | Rideshare | Next.js | React Native (bare) | React Native (bare) | Node | 2 | `nextjs-patterns`, `native-bare` |
| 10 | Event platform | Vue 3 | Android Compose (v6) | iOS (Swift) | Java (Spring) | 3 | **`vue` (gap)**, `android-v6-compose`, `ios` |

**~23 frontend codebases total.** Backend counts unchanged (one per use case).

## Already done (feed consolidation, not re-run)

| Use case | Frontend(s) | Backend |
|---|---|---|
| Deskline (helpdesk) | React web + Flutter v5 mobile | Node/TS |
| Telehealth | React Native (Expo) | Go |
| Edtech (educator) | Angular web | Node |

## Coverage

Every `cometchat-skills` frontend family is exercised across the set:

- **Web:** Next.js · React · Angular · **Vue 3** · Astro
- **Cross-platform mobile:** Flutter v6 · Flutter v5 · React Native (bare) · React Native (Expo)
- **Native mobile:** Android Compose (v6) · Android Kotlin (v5) · iOS (Swift)
- **Backends:** Python · PHP · Node · Java (Spring) · Go
- **UI-Kit versions:** v5 **and** v6 · **Products:** 1:1 · groups · calls · push · moderation · reactions/polls · RBAC

> **Vue (runs 5 & 10) is the deliberate gap-probe:** CometChat ships a Vue UI Kit but there's **no `cometchat-vue` skill** — record "no skill triggered" as the finding.

## Fleet implication

- **iOS is in every use case → the Mac mini builds all 10 iOS targets** (native Swift + Flutter/RN iOS all need Xcode).
- **The HP handles web + Android** for every use case.
- So each use case **splits across both machines by platform**, not one-machine-per-use-case. The per-run report merges the platform slices (see `STEP4_PIPELINE.md` §6.5).
- **Users/seed unchanged:** the 3 platform clients per use case share one backend + one set of ~6 namespaced CometChat users — they're just different clients logging into the same app. The pooled 100-user cap math is unaffected.

---

## Slack paste (monospace block)

```
Step 4 — Final Use-Case Set (10 runs · tri-platform: web + Android + iOS)

#   Use case          Web        Android              iOS                  Backend
--  ----------------  ---------  -------------------  -------------------  -------------
1   Marketplace       Next.js    React Native (Expo)  React Native (Expo)  Python
2   Community forum   Flutter v6 Flutter v6           Flutter v6           PHP
3   Delivery          Angular    Android Compose v6   iOS (Swift)          Node
4   Dating            React      React Native (bare)  React Native (bare)  Python
5   Fintech support   Vue 3      Android Compose v6   iOS (Swift)          Java (Spring)
6   Creator community Astro      Android Kotlin v5    iOS (Swift)          Go
7   Field-service     Flutter v5 Flutter v5           Flutter v5           PHP
8   Real-estate       Angular    Android Kotlin v5    iOS (Swift)          Golang
9   Rideshare         Next.js    React Native (bare)  React Native (bare)  Node
10  Event platform    Vue 3      Android Compose v6   iOS (Swift)          Java (Spring)

Every use case ships web + Android + iOS. Flutter = 1 codebase for all 3;
React Native = 1 codebase for Android+iOS. ~23 frontend codebases total.

Coverage (web): Next.js·React·Angular·Vue3·Astro | (x-platform): Flutter v5/v6·
RN bare/Expo | (native): Android Compose v6·Android Kotlin v5·iOS Swift.
Backends: Python·PHP·Node·Java·Go. Vue = no skill (deliberate gap-probe).
iOS in every run -> Mac mini builds all iOS; HP does web+Android.
```
