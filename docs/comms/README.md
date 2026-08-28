# docs/comms/ — correspondence with Systems 2 and 3

Append-only in spirit. **Do not rewrite or delete a message that was already sent.**
Each file here was transmitted to another computer's operator. It is the permanent record
of what was communicated. Future corrections go in a new file, not an edit.

## Folder structure

```
docs/comms/
├── to_system2/       Messages sent to Computer 2 (execution engine) and its dashboard
├── to_system3/       Messages sent to Computer 3 (account manager / risk gate)
├── handoffs/         Formal handoffs between agents or sessions
├── notices/          Status notices published to all downstream systems
├── replies/          Replies received from downstream
└── technical_docs/   Technical specifications transmitted to other systems
```

## Naming conventions

- Messages sent to a specific system: `TO-SYSTEM2-<date>-<slug>.md`
- Messages to both systems: `TO-SYSTEM2-3-<date>-<slug>.md`
- Dashboard-targeted: `TO-DASHBOARD-<date>-<slug>.md`
- Ask/question: `ASK-<date>-<slug>.md`

## Rules

1. Once a file is committed, its content is frozen — it represents what was actually sent.
2. New information about a previous message goes in a new file or a reply.
3. The `technical_docs/` subfolder holds specs that were transmitted (e.g. API contracts).
   Do not move a file out of here that was already cited by path from another system.

## Do NOT put here

- Work items or tasks (→ `task/`)
- Design documentation not transmitted to other systems (→ `docs/design/`)
- Internal notes (→ `docs/notes/`)
