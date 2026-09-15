# Methodology Module 01: LLM Cognition & Weakness Counters

> **Core Law:** AI agents are non-deterministic, conversational, and suffer from context amnesia. Autonomous reliability requires deterministic mechanical constraints, single-writer state locking, and feedforward prompts.

---

## 1. The Core LLM Failure Modes

| Failure Mode | Root Cause | Mechanical Counter |
|---|---|---|
| **Conversational Idling** | LLMs are trained for single-turn Q&A and stop when no user is prompting. | **Cron Pacemakers (P28)** wake persistent sessions via `session_notify` on scheduled cadences. |
| **Context Amnesia** | Token context windows compact, wiping ephemeral conversation history. | **Post-Compaction Recovery Anchors** in always-loaded laws force reloading `SKILL.md` immediately after compaction. |
| **Phantom Tool Calls** | Model narrates what it *would* do without emitting structured calls. | **Tool Receipts Rule**: Every claim of action requires a same-turn tool result in context. |
| **Concurrent State Clobbering** | Multiple lanes reading and writing shared files simultaneously cause race conditions and lost updates. | **Single-Writer State (P26)** enforced with `fcntl.flock` (exclusive file locks) in `tools/ledger.py`. |
| **Mental Math & Boundary Slips** | Autoregressive models cannot reliably compute arithmetic or string lengths in reasoning tokens. | **Python Heredocs**: All counts, row budgets, and costs must pass through `python3 -c` or script execution. |

---

## 2. The Single-Writer Locking Principle

State that lives only in chat is a memory of a conversation. Durable state lives in files on disk with **exactly one named writer**.

```python
import fcntl

# Pattern: Exclusive append lock with atomic monotonic row assignment
with open("evidence/ledger.jsonl", "a+") as f:
    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
    # 1. Read existing rows to determine n + 1
    # 2. Write new JSONL row with timestamp
    # 3. fsync to flush to disk before releasing lock
    f.flush()
    fcntl.flock(f.fileno(), fcntl.LOCK_UN)
```

---

## 3. Feedforward Context Injection vs. Feedback

1. **Feedforward Constraints (`SKILL.md`):** Injected into the model's context window before generation begins. Prevents known bugs before token 1.
2. **Deterministic Feedback (Mechanical Gates):** Linters, schema tests, and audit scripts (`tools/audit.py`) return exact error deltas if generation violates constraints.
3. **The Learning Accumulator (`rework.md`):** Every defect caught by feedback must record a `Prevented by` rule that permanently updates the feedforward prompt.
