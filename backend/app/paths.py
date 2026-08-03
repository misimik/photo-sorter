"""Path safety helpers.

All file-serving endpoints resolve the requested path and verify it stays
inside an allowed root. Docker-level :ro mounts are defense-in-depth only.
"""

import os
from pathlib import Path


def resolve_within(root: Path, candidate: str | Path) -> Path:
    """Resolve `candidate` (absolute or relative) and require it to live inside root.

    Raises ValueError on escape or missing file.
    """
    root = root.resolve()
    target = Path(candidate)
    if not target.is_absolute():
        target = root / target
    target = target.resolve()
    try:
        common = os.path.commonpath([root, target])
    except ValueError:  # different drives on Windows
        raise ValueError(f"Path outside allowed root: {target}")
    if common != str(root):
        raise ValueError(f"Path outside allowed root: {target}")
    if not target.is_file():
        raise ValueError(f"File not found: {target}")
    return target
