---
paths:
  - "**/tests/**"
  - "**/conftest.py"
---

# Advanced Unit Testing Rules

## 1. Stay close to a bug

When a test is written to reproduce a reported bug, keep it focused on that exact failure and nothing else. Do not add assertions that check unrelated properties, because they do not help reproduce the problem and may only make the test harder to read. The goal is to make the test fail at the same point and for the same reason as it fails for the user. PNG generation is only a concrete example here; the same principle applies to any bug-focused test.

Bad example with a PNG file overwrite bug:

```python
from pathlib import Path

from PIL import Image
from assertpy import assert_that


def test_overwrites_file(tmp_path: Path) -> None:
    file_path = tmp_path / "test.png"
    file_path.touch()

    Logo("IBM").save(file_path)

    with Image.open(file_path) as image:
        assert_that(image.format).is_equal_to("PNG")
```

Better example focused on the reported bug:

```python
from pathlib import Path


def test_overwrites_existing_file(tmp_path: Path) -> None:
    file_path = tmp_path / "test.png"
    file_path.touch()

    Logo("IBM").save(file_path)
```
