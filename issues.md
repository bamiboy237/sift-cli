# Issues & Improvements

This file tracks non-blocking issues—general patterns or opportunities for improvement that can benefit the whole app or specific areas.

Each entry should follow this format:
- **Command:** What to do, in a concise imperative.
- **Context:** Where/when this applies, or the general scenario.
- **Improvement:** What change is suggested.
- **Benefit:** Why this helps (debugging, maintainability, user experience, etc).

---

## Example

**Command:** Add logging for skipped operations  
**Context:** When the app silently skips files, records, or actions due to validation, size, or other constraints  
**Improvement:** Insert a logging statement before returning or skipping, to record what was skipped and why  
**Benefit:** Easier debugging, better auditing, and more transparency for users and developers

*Example instance: In extractors, log when a file is skipped for exceeding max size before returning None.*

---