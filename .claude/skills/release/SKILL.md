---
name: release
description: |
  Prepare a new version release for the openroad-mcp project. Automates version
  bumping, changelog generation, lockfile updates, and release commit creation.

  Use this skill whenever the user asks to:
  - Prepare a release, cut a release, or do a release
  - Bump the version or update the version
  - Create a release commit
  - Ship a new version
  - Update the changelog for a new release

  Trigger on phrases like "release", "bump version", "prepare release", "cut v0.x",
  "ship it", "new release", or any mention of version numbers in the context of
  publishing. Also trigger when the user references the release process we've done
  before (e.g., "do the release thing", "same as last time").
---

# Release Preparation

This skill automates the full release preparation workflow for the openroad-mcp
project. It ensures every file that references the version gets updated consistently.

## Project context

- **Build system**: hatchling (Python)
- **Package manager**: uv
- **Version source**: `pyproject.toml` `[project] version`
- **Changelog format**: Keep a Changelog
- **Commit style**: Conventional Commits (`feat:`, `fix:`, `chore:`, etc.)
- **GitHub repo**: `luarss/openroad-mcp`

## Workflow

### Step 1: Determine versions

Read the current version from `pyproject.toml`:

```
grep '^version = ' pyproject.toml
```

Then ask the user what the new version should be. Suggest the next logical
semver bump based on the commits since the last release:

- **Patch** (0.3.0 → 0.3.1): only fixes and minor changes
- **Minor** (0.3.0 → 0.4.0): new features added, backwards compatible
- **Major** (0.3.0 → 1.0.0): breaking changes

Show the suggestion but let the user decide.

### Step 2: Collect commits since last release

Get the last release tag:

```bash
git tag --sort=-v:refname | head -5
```

Then list all commits since that tag:

```bash
git log <last-tag>..HEAD --oneline
```

If no tag exists, use the first commit or the last "chore: release" commit:

```bash
git log --oneline --grep="chore: release" | head -1
```

### Step 3: Categorize commits into changelog sections

Read each commit message and sort into Keep a Changelog categories:

| Category | Conventional commit prefix |
|----------|---------------------------|
| **Added** | `feat:` |
| **Changed** | `chore:`, `build:`, `ci:`, `perf:`, `refactor:` |
| **Fixed** | `fix:` |
| **Removed** | commits mentioning removal/deprecation |

For each commit, format the changelog entry as:
```
- Description ([#PR](https://github.com/luarss/openroad-mcp/pull/PR))
```

Use the PR number from the commit message if present. For commits without a PR
number, just use the description part after the prefix.

### Step 4: Update all version references

These files must be updated with the new version. Update ALL of them — missing
one breaks the release consistency.

**pyproject.toml** — Update `version = "X.Y.Z"` in the `[project]` section.

**server.json** — Update all three version references:
- Top-level `"version": "X.Y.Z"`
- PyPI package `"version": "X.Y.Z"`
- OCI identifier `"identifier": "ghcr.io/luarss/openroad-mcp:X.Y.Z"`

**MCP manifest files and README** — These files use `git+https://github.com/luarss/openroad-mcp`
without a version pin. Update every occurrence to pin to the release tag, which
prevents supply chain attacks by ensuring users install a known, reviewed commit:

Change:
```
"git+https://github.com/luarss/openroad-mcp"
```
To:
```
"git+https://github.com/luarss/openroad-mcp@vX.Y.Z"
```

The safest way to do this in bulk is a single perl pass per file, e.g.:
```bash
perl -i -pe 's|git\+https://github\.com/luarss/openroad-mcp"|git+https://github.com/luarss/openroad-mcp\@vX.Y.Z"|g' README.md
```

Apply this to `README.md` (many occurrences — use perl or replace_all).

After updating, verify no bare URL remains:
```bash
grep "luarss/openroad-mcp\"" README.md
```
That grep should return no output.

> **Side note for users:** If you always want the latest version and prefer not
> to pin, omit the `@vX.Y.Z` suffix and use the bare URL:
> `git+https://github.com/luarss/openroad-mcp`. This trades supply chain
> safety for convenience — acceptable for local/dev setups, not recommended
> for shared or production environments.

**uv.lock** — Regenerate by running `uv lock`. Do NOT hand-edit this file.

**CHANGELOG.md** — Add new section before the previous version's section.
Today's date goes in the header. Add the link at the bottom:

```
[X.Y.Z]: https://github.com/luarss/openroad-mcp/releases/tag/vX.Y.Z
```

**ROADMAP.md** — Find the "Version Milestones" table and add a new row for
this release. Move any now-completed items from future milestones into this
release's description.

### Step 5: Run tests

Run the test suite to verify nothing is broken:

```bash
python -m pytest --tb=short -q
```

If tests fail, report the failures to the user before proceeding. Do not commit
a broken release.

### Step 6: Create the release commit

Stage only the release-related files:

```bash
git add CHANGELOG.md ROADMAP.md pyproject.toml server.json uv.lock README.md
```

Commit with the message:

```
chore: release vX.Y.Z
```

Do NOT push unless the user explicitly asks. The commit stays local for review.

## Important details

- Always use `uv lock` to regenerate the lockfile rather than editing it manually
- The CHANGELOG date format is ISO: `YYYY-MM-DD`
- Version tags use a `v` prefix: `v0.4.0` (but the version in files has no prefix)
- Check for ALL files referencing the old version by running:
  ```
  grep -r "OLD_VERSION" --include="*.toml" --include="*.json" --include="*.lock" --include="*.md"
  ```
  (replace `OLD_VERSION` with the actual previous version, e.g. `0\.5\.2`)
  before committing, to catch any missed references
- Also verify the README git URLs were updated:
  ```
  grep "openroad-mcp@" README.md
  ```
  All occurrences should show the new `@vX.Y.Z` tag
- If `server.json` doesn't exist, skip it (some repos may not have it)
- If `ROADMAP.md` doesn't exist or has no version table, skip it
