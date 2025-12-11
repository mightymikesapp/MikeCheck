## 2024-05-23 - Regex Optimization Pitfall
**Learning:** Combining many regex patterns into a single alternation `(A)|(B)|...` can be slower than iterating over individual patterns if the regex engine has to backtrack frequently. However, extracting common prefixes/suffixes (like `\b`) to anchor the alternation `\b(?:A|B|...)\b` allows the engine to fail fast and yielded a 2x speedup.
**Action:** When combining regexes, always factor out common anchors or prefixes to minimize backtracking state size.
