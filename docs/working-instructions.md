# Working Instructions — Grocery List

## The Workflow
1. **Spec/design decisions happen in this Claude.ai project chat.**
   This is where features are designed, decisions are made, and the spec is updated.

2. **Canonical files live on GitHub (`mattb2518/grocery-list`).**
   After every chat session where something changes, push updates to:
   - `SPEC.md` — what the product does
   - `DECISIONS.md` — why we made key choices (append-only, new entries at top)
   - `docs/working-instructions.md` — this file

3. **Claude Code reads from GitHub and does all the building.**
   Spec-to-code is one-way. Claude Code never rewrites the spec wholesale.
   If Claude Code changes something not reflected in the spec, update the spec
   before the next session.

## Reading Repo Files From Chat
Fetch files via raw.githubusercontent.com — this avoids GitHub's 60-requests/hour
anonymous API rate limit, which causes confusing intermittent 403s:

https://raw.githubusercontent.com/mattb2518/grocery-list/main/SPEC.md
https://raw.githubusercontent.com/mattb2518/grocery-list/main/DECISIONS.md
https://raw.githubusercontent.com/mattb2518/grocery-list/main/docs/working-instructions.md
https://raw.githubusercontent.com/mattb2518/grocery-list/main/CLAUDE.md

Use `git ls-remote https://github.com/mattb2518/grocery-list.git` to confirm
which branches actually exist — treat this as the authority, not memory.

## The GitHub Token
A fine-grained personal access token scoped to this repo only (Contents = Read
and Write) lives in `.env.local` on your local machine (gitignored, never
committed). Paste it into chat only at the moment a push is needed. Never store
it in project instructions or anywhere persistent.

`.env.local` format:
GITHUB_TOKEN=github_pat_...

## Starting a New Chat Session
Paste this at the start of every new chat in this project:

Please read SPEC.md first:
https://raw.githubusercontent.com/mattb2518/grocery-list/main/SPEC.md

Then read the working instructions:
https://raw.githubusercontent.com/mattb2518/grocery-list/main/docs/working-instructions.md

Once you've read both, confirm what you understand the current state of the
project to be, and ask me what we're working on today.

## Starting a New Claude Code Session
Paste this at the start of every Claude Code session:

Read SPEC.md from GitHub before writing any code:
https://raw.githubusercontent.com/mattb2518/grocery-list/main/SPEC.md

Also read CLAUDE.md in this repo — it has the full architecture and
implementation details.

Do not rewrite SPEC.md. If you make a change not reflected in the spec,
flag it so I can update the spec manually.

## After Every Session
- Push all spec/decision changes to GitHub
- If Claude Code changed something not in the spec, update SPEC.md before
  the next session
- Add a DECISIONS.md entry for any non-obvious choices made today

## Rules of the Road
- Tokens never go in prompts, project instructions, or committed files
- Claude Code reads the spec; it does not own the spec
- Flag complexity creep — if a feature is getting complicated, pause and discuss
- One branch: `main`. No stray branches.
