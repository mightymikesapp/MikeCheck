## 2024-05-22 - Custom File Inputs & Keyboard Focus
**Learning:** Standard `input[type="file"]` elements that are visually hidden (opacity: 0) for custom styling break keyboard accessibility because the user cannot see the focus ring.
**Action:** Always add `:focus-within` styles to the parent container of a hidden file input to mimic the browser's default focus ring behavior.
