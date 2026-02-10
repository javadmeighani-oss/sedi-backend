# Stage 20.0 Report: UI Audit & Repair Pack

**Date:** 2025-02-10  
**Goal:** Review and polish existing UI for production-like field testing; Apple-like minimal look; EN default, FA/AR RTL correct.

---

## 1) Summary

- **Layout & consistency:** Chat header icon buttons use explicit `iconSize: 24` and `minimumSize: Size(44, 44)` for consistent tap targets. Overflow menu (more_vert) already used for Lifestyle to avoid header clutter. Horizontal padding 16 is used on Vitals, Devices, Lifestyle, Chat top bar; message list uses 16 left/right.
- **Chat UI:** Message list and input bar remain inside `SafeArea` (body is wrapped). Message bubbles use `AlignmentDirectional.centerStart` / `centerEnd` so RTL correctly places Sedi on start side and user on end side; no timestamps in bubbles (none were present).
- **Icons:** All header icons use `AppTheme.primaryBlack` (neutral); icon size 24. No separate “memory” icon found in the app; overflow menu icon (more_vert) follows same color/size.
- **Manual QA checklist:** Documented below.

---

## 2) Before / After Notes

| Area | Before | After |
|------|--------|--------|
| Chat header IconButtons | Default icon size (24), default tap target (~48). Color set per icon. | Explicit `iconSize: 24`, `IconButton.styleFrom(foregroundColor: AppTheme.primaryBlack, minimumSize: Size(44, 44))` for notifications, devices, favorite_border, history. |
| PopupMenuButton (overflow) | Icon with color. | Icon with explicit `size: 24` and `color: AppTheme.primaryBlack`. |
| MessageBubble alignment | `Alignment.centerLeft` / `centerRight` (fixed LTR). | `AlignmentDirectional.centerStart` / `centerEnd` so RTL flips bubble sides correctly. |
| Safe areas | Chat body already inside `SafeArea`; input bar `Positioned(bottom: keyboardHeight)` inside same. | No change; confirmed correct. |

---

## 3) Files Changed

| File | Change |
|------|--------|
| **lib/features/chat/presentation/pages/chat_page.dart** | IconButton: `iconSize: 24`, `style: IconButton.styleFrom(foregroundColor: AppTheme.primaryBlack, minimumSize: Size(44, 44))` for notifications, devices, favorite_border, history. PopupMenuButton icon: `Icon(Icons.more_vert, size: 24, color: AppTheme.primaryBlack)`. |
| **lib/features/chat/presentation/widgets/message_bubble.dart** | Alignment changed from `Alignment.centerLeft`/`centerRight` to `AlignmentDirectional.centerStart`/`centerEnd` for RTL-aware bubble alignment. |
| **docs/FRONTEND_STAGE20_REPORT.md** | This report. |

---

## 4) Icon Consistency

- **Style:** Outlined where available (e.g. `notifications_outlined`); fill for devices, favorite_border, history, more_vert.
- **Color:** All use `AppTheme.primaryBlack` (neutral). Accent (e.g. pistachio) not used in header to keep it minimal.
- **Size:** 24dp for all header and overflow icons.
- **Tap target:** Minimum 44×44 for IconButtons in header.
- **Memory icon:** Not present in codebase; no change.

---

## 5) Manual QA Checklist

Run through in order on a device or simulator:

1. **Intro** — Full-screen intro with logo; auto-navigation after ~2s.
2. **Onboarding** — If not completed: name, security password, flow to verification.
3. **Verification** — User verification step (if shown).
4. **Chat** — Main chat loads; header shows notifications, devices, heart (vitals), history, overflow (⋮). Tap each icon; overflow opens and “Lifestyle” navigates to Lifestyle. Send a message; Sedi reply aligns correctly. In RTL (fa/ar), bubbles align to start/end.
5. **Notifications** — Notifications icon opens list; pull-to-refresh; tap item; like/dislike if applicable.
6. **Vitals** — Heart icon opens Vitals; last recorded + trend; add vitals form; submit; values LTR in RTL.
7. **Devices** — Devices icon opens Devices; register device; long-press card → Revoke / Rotate token / Copy ID; confirm dialogs.
8. **Lifestyle** — Overflow (⋮) → Lifestyle; context (if any); update form (sleep, steps, calories, stress); submit.

Check: no heavy shadows; neutral colors; consistent 16px horizontal padding on list/content pages; RTL does not break alignment or input.

---

## 6) Verify (CI)

| Command | Purpose |
|--------|---------|
| `flutter analyze` | No new analysis errors. |
| `flutter test` | All existing tests pass. |

---

## 7) Rules Followed

- No new dependencies.
- No backend contract changes.
- Targeted UI fixes only (icons, bubble alignment).
- Single responsibility per widget kept.
- EN default; FA/AR RTL respected.

---

# Stage 20.2 Report: Chat InputBar full-width + Apple-like layout

**Date:** 2025-02-10  
**Context:** Stage 20.0 standardized header icons and RTL bubbles. Chat body uses SafeArea; input bar is Positioned(bottom: keyboardHeight).

---

## 1) Summary (Stage 20.2)

- **Full width:** InputBar root uses `width: double.infinity`; no outer horizontal margin. ChatPage positions it with `Positioned(left: 0, right: 0, bottom: keyboardHeight)` and no Center wrapper, so it spans edge-to-edge within SafeArea. Internal horizontal padding 16 keeps the pill inset.
- **Pill design:** Single-row pill container height 56, border radius 18, subtle border (`AppTheme.borderInactive`), no heavy shadows. Internal padding 12–16; spacing between text field and icons consistent.
- **Icons:** Send = `Icons.arrow_upward_rounded` in circular button (pistachio when enabled, grey when empty). Voice = `Icons.mic_rounded`. Both wrapped in `SizedBox(44, 44)` + `InkResponse` for tap target ≥44×44. Icons remain inside the bar.
- **RTL:** Icon order swaps: in RTL, send is on the “end” side and mic on the “start” side (via `Directionality.of(context)`). Input text direction follows page direction.

---

## 2) Before / After (Stage 20.2)

| Area | Before | After |
|------|--------|--------|
| InputBar width | `(screenWidth - 6) * 0.9` with horizontal margin 3 | `width: double.infinity`, padding 16 inside; no outer margin |
| ChatPage | `Positioned` + `Center` + InputBar | `Positioned(left: 0, right: 0, bottom)` only; no Center |
| Bar shape | ~90px height, radiusMedium, 1.5px border | Pill 56px height, radius 18, 1px subtle border |
| Layout | Column (text row + icon row) | Single Row: Expanded(TextField) \| mic \| send |
| Icons | GestureDetector + fixed sizes | InkResponse in 44×44; Send circle 36px, mic 26px |
| RTL | Fixed order (timer, mic, send) | Order: RTL → [send, mic]; LTR → [mic, send] |

---

## 3) Files Changed (Stage 20.2)

| File | Change |
|------|--------|
| **lib/features/chat/presentation/pages/chat_page.dart** | InputBar no longer wrapped in Center; Positioned uses left: 0, right: 0, bottom: keyboardHeight. |
| **lib/features/chat/presentation/widgets/input_bar.dart** | Full-width root; pill 56×radius 18; single Row with Expanded(TextField), mic, send; 44×44 tap targets (InkResponse); RTL icon order; Send disabled (grey) / enabled (pistachio); recording state (dot + timer). |
| **docs/FRONTEND_STAGE20_REPORT.md** | Stage 20.2 section + manual QA additions. |

---

## 4) Manual QA Additions (Stage 20.2)

Add to the main QA flow (after Chat step):

- **Very narrow screen:** Input bar stays full width; text field wraps or scrolls; mic and send stay visible and tappable.
- **Long message:** Single-line input scrolls horizontally; send/mic remain in place.
- **RTL (fa/ar):** Mic appears on start side, send on end side; input direction follows locale; send disabled/enabled states correct.
- **Keyboard open/close:** Bar stays attached to bottom (above keyboard when open); remains full width; no jump or overlap.
- **Send states:** Send disabled (grey circle) when input empty; enabled (pistachio) when text present; tap sends and clears.

---

## 5) Verify (Stage 20.2)

| Command | Purpose |
|--------|---------|
| `flutter analyze` | No new errors. |
| `flutter test` | All existing tests pass. |
