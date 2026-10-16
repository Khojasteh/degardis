# Degardis

Degardis helps skill authors express complex agent workflows through explicit tasks, conditions, requirements, and verification rules, then compiles those definitions into skills that AI agents can execute.

## Why Degardis

An agent skill is a package of instructions an AI agent loads to do a particular kind of work. A skill often starts as one `SKILL.md` file, and that works until the job it describes grows. Every request then makes the agent read guidance it does not need, the rules that matter get buried, and no one can say for sure which instruction applies when.

Degardis lets you write a big skill as small, focused pieces, say how they connect, and have the whole thing checked before any agent sees it.

- **Focused reading.** The agent reads a short entry page, then one page for the job at hand, and opens further guidance only when it applies.
- **Nothing left to guesswork.** You declare what each kind of work needs and when each piece of guidance applies. The compiler builds exactly that and infers nothing.
- **Your words, untouched.** Degardis never paraphrases, merges, summarizes, or drops what you wrote. All subject knowledge in the skill is yours.
- **Checked and reproducible.** A build fails unless every page is complete and every link resolves, and rebuilding the same source with the same Degardis version produces identical bytes on any machine.
- **Ready to install.** The output is a self-contained folder or ZIP for agent hosts that load skills from disk or by upload.

### Built for long, complex jobs

Degardis earns its keep when a skill covers several kinds of work, carries more guidance than any one request needs, or asks the agent to see a long job through. For a short, single-purpose skill, a hand-written `SKILL.md` is the better choice: the structure Degardis adds, and the instructions it gives the agent for working through that structure, are read on every run and pay off only when there is a lot of ground to cover.

## How it works

You write your skill as a source folder: a `skill.yaml` file that names the skill and lists its parts, plus Markdown files, each with a few lines of YAML frontmatter and one of five roles.

| You write | Which is |
| --- | --- |
| a **task** | a recognizable kind of work someone asks for, with cues that tell the agent when it is being asked |
| a **knowledge unit** | one reusable piece of what your skill knows: a concept, fact, constraint, or guidance |
| a **principle** | a standard the agent's work must honor across all of your tasks |
| a **facet** | guidance one aspect of the situation calls for, such as the audience, the material, or the rules in force |
| a **guide** | detail a task, a facet, or another guide opens as a separate page when its conditions hold |

Degardis compiles the source into a bundle:

- **`SKILL.md`**, the entry point, lists your tasks and when each applies.
- **One page per task** carries everything that task needs: its goal, its approach, and all the knowledge it depends on.
- **Principles, facets, and guides** get pages of their own, which the agent opens only when they apply.

## Keeping the agent on track

A skill that covers a lot of ground needs more than good content: the agent has to find the right part of it and follow through. Degardis writes the short, domain-neutral operating instructions that make each bundle direct the agent to:

- **Pick the right work.** Each outcome a request asks for goes to one task, and several outcomes are handled one at a time, in the order asked. A request no task covers is reported rather than forced into the closest one.
- **Read only what applies.** The agent opens a principle, facet, or guide when its conditions hold, and reconsiders them as the work changes.
- **Follow your hand-offs.** A task can pass work to another task under conditions you state, for example pausing until a prerequisite is done and then resuming where it left off.
- **Keep its place.** Every bundle includes a progress register the agent keeps current: which tasks are in progress, which are done, and what its work must satisfy.
- **Check before it commits.** Before an effect it cannot undo, and before it calls anything finished, the agent checks its work against the requirements that apply.

## Write it with your agent

Degardis has a companion skill, **[Degardis Authoring](https://github.com/Khojasteh/degardis-skills/tree/main/skills/degardis-authoring)**, that turns your AI agent into a Degardis author. It is itself built with Degardis.

You don't need to learn the format before you start. The compiler can tell you a source is well formed, but not how to split your subject into tasks, which knowledge each task needs, which standards deserve to be principles, or when a piece of guidance should apply. Degardis Authoring gives your agent that judgment. Describe the skill you want in plain words, and your agent designs and writes the source, then validates and builds it with Degardis. It can also review or revise an existing source, explain format choices, and help you test how an agent behaves with the skill you built.

The two are designed as a pair: Degardis Authoring supplies the authoring judgment, and the compiler checks the result.

## Get started

1. Install Degardis Authoring in your agent: download [degardis-authoring.zip](https://github.com/Khojasteh/degardis-skills/releases/latest/download/degardis-authoring.zip) and follow [Install a skill](https://github.com/Khojasteh/degardis-skills/blob/main/docs/installation.md).
2. Ask your agent to create a Degardis skill for the work you have in mind.

That's it. If the Degardis compiler isn't installed yet, your agent asks for your permission and installs it. Degardis needs Python 3.10 or newer in the environment your agent works in.

### Working by hand

To write a source yourself, or to see what your agent works with, install the compiler and start from a source that already compiles:

```console
python -m pip install degardis
degardis init my-skill
degardis build my-skill --output bundles
```

`build` checks the source first and writes the bundle, here to `bundles/my-skill/`, only when the checks pass. [Getting started](https://github.com/Khojasteh/degardis/blob/main/docs/getting-started.md) walks through the loop, including the repository's worked example.

## Documentation

| If you want to | Read |
| --- | --- |
| Install it and build your first skill | [Getting started](https://github.com/Khojasteh/degardis/blob/main/docs/getting-started.md) |
| Understand a part of a source, or look up a field | [Reference manual](https://github.com/Khojasteh/degardis/blob/main/docs/manual.md) |
| Look up a command, an option, or an exit status | [CLI reference](https://github.com/Khojasteh/degardis/blob/main/docs/cli.md) |
| Understand a built bundle and how it runs | [Bundles](https://github.com/Khojasteh/degardis/blob/main/docs/artifact-format.md) |
| Get Degardis Authoring and other ready-made skills | [Degardis Skills](https://github.com/Khojasteh/degardis-skills) |
