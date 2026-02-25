# SOFA MCP Skill Management Guide

This guide outlines the commands and steps to manage your `sofa-mcp` skill for the Gemini CLI.

---

### 1. Initialize the Skill Structure

Use this command to create the basic directory structure for your skill. You should only run this once for a new skill.

**Command:**

```bash
node /home/sizhe/.nvm/versions/node/v24.5.0/lib/node_modules/@google/gemini-cli/node_modules/@google/gemini-cli-core/dist/src/skills/builtin/skill-creator/scripts/init_skill.cjs sofa-mcp --path skills/sofa-mcp
```

*(Note: Replace `skills/sofa-mcp` with your desired path if different.)*

---

### 2. Edit the Skill Definition (`SKILL.md`)

After initialization, navigate to the `skills/sofa-mcp/SKILL.md` file. You will need to edit this file to:

* **Update the YAML Frontmatter:**
  * Set the `name` to `sofa-mcp`.
  * Write a comprehensive `description` for the skill (this tells the LLM when to use it).
* **Define Your Tools:** Add the details of your MCP tools (names, descriptions, parameters, types) in the Markdown body. This will be the schema the LLM uses to call your tools.

---

### 3. Package the Skill

Once you've defined your skill in `SKILL.md`, use this command to validate and package it into a distributable `.skill` file.

**Command:**

```bash
node /home/sizhe/.nvm/versions/node/v24.5.0/lib/node_modules/@google/gemini-cli/node_modules/@google/gemini-cli-core/dist/src/skills/builtin/skill-creator/scripts/package_skill.cjs skills/sofa-mcp/sofa-mcp
```

*(The `.skill` file will be created in the current directory unless you specify an output path.)*

---

### 4. Install the Skill

After packaging, install the `.skill` file into your Gemini CLI. You can choose to install it locally for the current workspace or globally for your user.

**Install for current workspace (recommended for development):**

```bash
gemini skills install sofa-mcp.skill --scope workspace
```

**Install for user (global):**

```bash
gemini skills install sofa-mcp.skill --scope user
```

*(Replace `sofa-mcp.skill` with the actual path to your packaged skill file if it's not in the current directory.)*

combined with packaging command to update and install in one step:

```bash
node /home/sizhe/.nvm/versions/node/v24.5.0/lib/node_modules/@google/gemini-cli/node_modules/@google/gemini-cli-core/dist/src/skills/builtin/skill-creator/scripts/package_skill.cjs skills/sofa-mcp/sofa-mcp
gemini skills install sofa-mcp.skill --scope workspace
```

---

### 5. Reload Skills (User Action Required)

**IMPORTANT:** After installing, you MUST manually execute the following command in your interactive Gemini CLI session to enable the new skill:

```
/skills reload
```

You can then verify the installation by running:

```
/skills list
```

---

### 6. Iterating on Skill Changes

If you make any changes to your `SKILL.md` (e.g., adding/modifying tools or their descriptions), you must repeat steps 3, 4, and 5 to update and reload the skill for the changes to take effect.
