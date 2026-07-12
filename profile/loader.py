"""YAML loader and validator for Research Profiles."""

from __future__ import annotations

from pathlib import Path

import yaml

from .models import Profile


def load_profile(path: str | Path) -> Profile:
    """Load and validate a Research Profile from a YAML file.

    Args:
        path: Filesystem path to the YAML profile.

    Returns:
        A frozen Profile instance.

    Raises:
        FileNotFoundError: If the YAML file does not exist.
        yaml.YAMLError: If the file contains invalid YAML.
        ValueError: If the parsed data fails validation.
    """
    filepath = Path(path)
    if not filepath.is_file():
        raise FileNotFoundError(f"Profile not found: {filepath}")
    text = filepath.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        raise ValueError("Profile YAML must contain a top-level mapping.")
    return Profile.from_dict(data)
