# Releasing minrepro

Version source of truth: `pyproject.toml` (`project.version`) and `src/minrepro/__init__.py` (`__version__`). Keep them equal.

## Version policy

- Semantic Versioning: `MAJOR.MINOR.PATCH`
- Git tags: `v` prefix, for example `v0.1.0`
- Each release updates `CHANGELOG.md` under a new section dated `YYYY-MM-DD`

## Checklist for a new release

1. Update version in:
   - `pyproject.toml`
   - `src/minrepro/__init__.py`
2. Update `CHANGELOG.md` (move items under `## [X.Y.Z] - YYYY-MM-DD`).
3. Run the full suite:

   ```bash
   pip install -e ".[dev]"
   pytest
   ```

4. Commit on `main`:

   ```bash
   git add -A
   git commit -m "Release vX.Y.Z"
   ```

5. Create an annotated tag:

   ```bash
   git tag -a vX.Y.Z -m "minrepro X.Y.Z"
   ```

6. Push branch and tag (after the GitHub remote exists):

   ```bash
   git push origin main
   git push origin vX.Y.Z
   ```

7. The **Release** workflow (`.github/workflows/release.yml`) runs on the tag:
   - tests
   - builds sdist and wheel into `dist/`
   - publishes a GitHub Release with those artifacts

## First-time GitHub setup

1. Create a new empty repository named **`minrepro`** (public recommended).
2. Do not initialize with a README on GitHub if this local tree already has one.
3. Point `origin` at it and push:

   ```bash
   git remote add origin https://github.com/YOUR_USER/minrepro.git
   git branch -M main
   git push -u origin main
   git push origin v0.2.0
   ```

4. Open the Actions tab and confirm CI is green; open the Releases page for `v0.2.0`.

## Optional: publish to PyPI later

Not required for v0.1. When ready:

```bash
python -m build
python -m twine upload dist/*
```

Prefer a trusted-publishing GitHub Action over long-lived tokens.
