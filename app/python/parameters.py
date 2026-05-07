"""Load numeric EMS parameters from the packaged summary file."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re


APP_PYTHON_DIR = Path(__file__).resolve().parent
DEFAULT_SUMMARY_PARAMETERS_PATH = APP_PYTHON_DIR / "data" / "summary_parameters.txt"

_PARAMETER_RE = re.compile(
    r"^\s*(?:[-*]\s*)?"
    r"([A-Z][A-Z0-9_]+)"
    r"\s*=\s*"
    r"([-+]?(?:\d+(?:[.,]\d*)?|[.,]\d+)(?:[eE][-+]?\d+)?)"
)


@lru_cache(maxsize=8)
def load_summary_parameters(
    path: str | Path = DEFAULT_SUMMARY_PARAMETERS_PATH,
) -> dict[str, float]:
    """Return all ``NAME = number`` entries found in ``summary_parameters.txt``.

    The summary file is intentionally readable prose. This parser only cares
    about uppercase parameter assignments, so explanatory text can stay there.
    """

    parameter_path = Path(path)
    if not parameter_path.exists():
        return {}

    parameters: dict[str, float] = {}
    for line in parameter_path.read_text(encoding="utf-8").splitlines():
        match = _PARAMETER_RE.match(line)
        if not match:
            continue

        name, raw_value = match.groups()
        parameters[name] = float(raw_value.replace(",", "."))

    return parameters


def get_parameter(
    name: str,
    default: float | None = None,
    *,
    path: str | Path = DEFAULT_SUMMARY_PARAMETERS_PATH,
) -> float:
    """Read one numeric parameter, with an optional fallback for old files."""

    parameters = load_summary_parameters(path)
    if name in parameters:
        return parameters[name]

    if default is None:
        raise KeyError(f"Missing EMS parameter: {name}")

    return float(default)
