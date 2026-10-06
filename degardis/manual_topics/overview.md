## What a source is

A Degardis source declares a skill and the authored material each class of work needs. A build produces an agent skill with one page per task.

Five construct types hold authored Markdown:

- **Task** — one recognizable class of requested work.
- **Knowledge** — reusable subject matter, classified as concept, fact, constraint, or guidance.
- **Principle** — a standard the agent's work must honor.
- **Facet** — guidance selected by the situation rather than the task.
- **Guide** — detail a task, facet, or another guide loads separately.

Degardis adds no domain content and never paraphrases, merges, summarizes, or drops authored material. Around that material it adds headings and short, domain-neutral instructions in English with American spelling. The instructions route each requested outcome to a task and tell the agent which pages to read and when. They also have the agent track its progress and check its work against the requirements that apply, before an effect it cannot undo and before it claims completion.

`SKILL.md` is the bundle entry point: it identifies the skill, carries its skill-wide guidance, and routes a request to task pages. A task page contains that task's complete knowledge closure and may hand the work to another task. Principles, facets, and guides remain separate loads.
