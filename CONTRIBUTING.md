# Contributing

## Language

Everything is written in **English**: code, comments, docstrings, variable names, commit messages, issue and pull request text, and the documentation (`README.md`). Only the placeholder examples use Cyrillic or Latin names.

## Branch Strategy

| Branch       | Purpose                                           |
| ------------ | ------------------------------------------------- |
| `main`       | Production — stable, released code                |
| `develop`    | Development — integration branch for ongoing work |
| `release/v*` | Release staging — e.g. `release/v0.2.0`           |

- Feature branches are cut from `develop`: `feat/my-feature`
- Hotfix branches are cut from `main`: `hotfix/critical-bug`
- Merge `develop` → `release/v*` → `main` when releasing

## Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>(<scope>): <short description>
```

**Types:**

| Type       | When to use                              |
| ---------- | ---------------------------------------- |
| `feat`     | New feature                              |
| `fix`      | Bug fix                                  |
| `refactor` | Code change that is not a fix or feature |
| `chore`    | Maintenance, dependency updates, tooling |
| `docs`     | Documentation only                       |
| `test`     | Adding or updating tests                 |
| `ci`       | CI/CD pipeline changes                   |
| `perf`     | Performance improvement                  |
| `style`    | Formatting, whitespace (no logic change) |
| `revert`   | Reverting a previous commit              |

**Examples:**

```
feat(engine): add a date type to function signatures
fix(parser): report the position of an unclosed parenthesis
docs(syntax): add examples of invalid placeholders
test(engine): cover NUMBER to NUMBER functions
ci: publish to PyPI from a version tag
```

- Use the imperative mood: "add feature" not "added feature"
- Keep the subject line under 72 characters
- Reference issues when relevant: `fix(parser): reject nested calls (#42)`

