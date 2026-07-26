## minrepro release

Structure-aware JSON/YAML config shrinker: reduce a failing config to the smallest document that still fails your test command.

### Install this release

```bash
# from the GitHub source tag
pip install "git+https://github.com/OWNER/minrepro.git@v0.1.0"

# or clone and install editable
git clone https://github.com/OWNER/minrepro.git
cd minrepro
pip install -e ".[dev]"
```

Replace `OWNER` with your GitHub username or org.

### Changelog

See [CHANGELOG.md](https://github.com/OWNER/minrepro/blob/main/CHANGELOG.md) for the full list of changes.

### Verify

```bash
minrepro --version
minrepro examples/broken.yaml \
  --test "python examples/oracle_bad_option.py {}" \
  --error-contains BAD_OPTION
```
