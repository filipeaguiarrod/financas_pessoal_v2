---
name: git-branch-pr-workflow
description: >-
  Use this skill whenever proposing, suggesting, writing, or modifying code in a git repository.
  It identifies the primary branch (main or master), creates a dedicated feature/fix branch from it,
  applies code changes or suggestions on that branch, commits and pushes changes, and prepares or opens a Pull Request.
---

# Git Branch & Pull Request Workflow

This skill defines the mandatory workflow for proposing and implementing code changes. Changes must **never** be made directly on `main`, `master`, or an unapproved branch without creating a dedicated feature/fix branch originating from the repository's primary branch.

## 1. Overview of the Procedure

Whenever a code modification or feature implementation is requested and approved:
1. **Detect Primary Branch**: Identify whether the repository uses `main` or `master` as its primary branch.
2. **Synchronize & Branch**: Pull the latest changes from the primary branch and create a new dedicated branch.
3. **Implement Changes**: Make code adjustments, additions, or fixes on the dedicated branch.
4. **Validate**: Run tests and verify changes.
5. **Commit & Push**: Commit with semantic commit messages and push to `origin`.
6. **Open / Prepare Pull Request**: Generate the PR via GitHub CLI (`gh`) or provide the direct GitHub comparison URL and a structured PR summary.

---

## 2. Step-by-Step Instructions

### Step 1: Detect Primary Branch (`main` vs `master`)

Run the helper script or Git commands:

```bash
# Using the helper script:
python .agents/skills/git-branch-pr-workflow/scripts/git_branch_pr.py detect

# Or using raw git:
git symbolic-ref refs/remotes/origin/HEAD
```

If `origin/HEAD` is not set, check existence:
- Check `main`: `git rev-parse --verify origin/main` or local `main`
- Check `master`: `git rev-parse --verify origin/master` or local `master`

### Step 2: Create Dedicated Feature Branch

Choose a semantic branch name following the format `<type>/<short-description>`:
- `feat/<feature-name>`: for new features or enhancements
- `fix/<bug-name>`: for bug fixes
- `refactor/<target>`: for refactoring without behavior change

Run the helper script to sync with remote and checkout the new branch:

```bash
# Helper script (automatically fetches origin/<primary> and checks out):
python .agents/skills/git-branch-pr-workflow/scripts/git_branch_pr.py create feat/<nome-da-funcionalidade>

# Manual alternative:
git fetch origin <primary_branch>
git checkout -b <branch-name> origin/<primary_branch>
```

### Step 3: Implement & Validate

1. Apply the requested code suggestions and modifications on this branch.
2. Run automated tests (e.g., `pytest`, `npm test`, or relevant project test suite).
3. Ensure no unwanted files are staged or created.

### Step 4: Commit Changes

Write clear, semantic commit messages (Conventional Commits):

```bash
git add <arquivos-alterados>
git commit -m "feat(<escopo>): descrição concisa da alteração"
```

### Step 5: Push Branch to Remote

```bash
git push -u origin <branch-name>
```

### Step 6: Create or Prepare the Pull Request

1. **If GitHub CLI (`gh`) is installed and authenticated**:
   ```bash
   gh pr create --base <primary_branch> --head <branch-name> --title "<titulo>" --body "<descricao>"
   ```

2. **If GitHub CLI is not installed**:
   Use the helper script to obtain the comparison URL:
   ```bash
   python .agents/skills/git-branch-pr-workflow/scripts/git_branch_pr.py pr-url
   ```
   Output the link to the user along with a suggested PR title and markdown description:
   - **PR Link**: `https://github.com/<owner>/<repo>/compare/<primary_branch>...<branch-name>?expand=1`
   - **Suggested Title**: `feat: ...`
   - **Summary of Changes**: Bullet points of what was added/fixed.
