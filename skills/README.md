# Skills

Each skill lives in its own folder under `skills/` and should include a `SKILL.md` file.

- Enabled by default.
- To disable a skill, create a file named `DISABLED` inside the skill folder.
- The bot loads all enabled `SKILL.md` files and appends them to the system prompt.

Example:

skills/my-skill/SKILL.md

```
Short title
- What this skill does
- How the agent should behave
```
