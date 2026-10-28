# Tasks
Group tasks by capability and dependencies. Each source task names its affected
files and focused checks; keep runtime/ORM/browser verification tasks separate.
Do not mark unrun checks complete or treat missing runtime as missing source.
During implementation, use the runner's work-items.json/checkpoint.json and
target.json. For a targeted invocation, report its target and requirements you
actually reassess; the runner merges these rows into the full checkpoint. When no
target is assigned, report every active requirement. Complete the assigned target and
focused regressions first; unrelated cleanup does not satisfy it. If blocked,
record the reason and resolution options rather than claiming completion.
## 1. Implementation and Verification
- [ ] 1.1 Implement the requirement and verify the observable result.
