<!-- RECOVERED VERBATIM from session ec152094-e614-4e0c-a8d5-c098728fc4af (2026-07-07): the answer-key section of the blind-grader prompt for the edge-numerical area, unmodified. -->

ANSWER KEY — 9 issue classes. Mark Y only if genuinely identified:
- C1 Missing 'price'/'qty' key → KeyError.
- C2 Present-but-None value (distinct from missing key) → TypeError.
- C3 Empty string '' → ValueError.
- C4 Non-numeric / currency symbols / thousands separators / locale.
- C5 int('3.0') (decimal-looking qty string) raises ValueError.
- C6 Money as binary float → drift; use Decimal/integer cents.
- C7 Negative price or qty accepted silently.
- C8 'nan'/'inf' strings parse via float() and poison the total.
- C9 Error messages should NAME the offending row index / field / value (not a bare exception).
