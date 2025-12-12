## 2024-05-22 - Custom File Inputs & Keyboard Focus
**Learning:** Standard `input[type="file"]` elements that are visually hidden (opacity: 0) for custom styling break keyboard accessibility because the user cannot see the focus ring.
**Action:** Always add `:focus-within` styles to the parent container of a hidden file input to mimic the browser's default focus ring behavior.
## 2025-12-11 - Accessible Tooltips & Focus States
**Learning:** Tooltips triggered only by `hover` are inaccessible to keyboard users. By wrapping the trigger in a focusable element (e.g., `span tabindex="0"`) and using the `peer` pattern (`peer-focus:opacity-100`), tooltips become accessible without JavaScript.
**Action:** Always include `peer-focus` (or `focus-within`) alongside `group-hover` for tooltips, and ensure interactive elements have visible focus rings (`focus:ring`).
## 2025-12-12 - Alpine.js Tabs & Keyboard Navigation
**Learning:** Using simple buttons for tabs lacks ARIA semantics and standard keyboard behaviors (arrow navigation). Alpine.js makes it easy to add `role="tab"` and `@keydown` handlers, but one must remember to handle focus management explicitly (`$refs.xxx.focus()`) to match native tab behavior.
**Action:** Always add `role="tablist"`, `aria-selected`, and arrow key support to Alpine.js tab implementations.
