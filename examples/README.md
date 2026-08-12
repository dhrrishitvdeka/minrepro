# Examples

| File | Purpose |
| --- | --- |
| `broken.yaml` | Multi-service Compose-like YAML with a bad `BAD_OPTION` key |
| `broken.json` | Same structure as JSON |
| `oracle_bad_option.py` | Fails (exit 1, message contains `BAD_OPTION`) while that key remains |
| `oracle_always_ok.py` | Always exits 0 (for non-interesting baseline demos) |

## Quick start

From the repository root (after `pip install -e .`):

```bash
minrepro examples/broken.yaml \
  --test "python examples/oracle_bad_option.py {}" \
  --error-contains BAD_OPTION
```

On Windows, if `python` is not on `PATH`, use `py` or the full interpreter path:

```text
minrepro examples/broken.yaml --test "py examples/oracle_bad_option.py {}" --error-contains BAD_OPTION
```

The same path is available as a library call:

```python
from pathlib import Path
from minrepro import reduce_file

result = reduce_file(
    Path("examples/broken.yaml"),
    command="python examples/oracle_bad_option.py {}",
    error_contains="BAD_OPTION",
)
print(result.reduced_text)
```

Expected reduced shape:

```yaml
services:
  backend:
    environment:
      BAD_OPTION: true
```
