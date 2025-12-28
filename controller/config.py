from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Paths:
    # Root directory of the project
    repo_root: Path

    # SQLite database storing job and replica state
    db_path: Path

    # Directory where logs are stored
    logs_root: Path

    # Directory for generated sbatch scripts
    generated_root: Path


def default_paths() -> Paths:
    # Find the project root directory
    root = Path(__file__).resolve().parents[1]

    # Return all important project paths
    return Paths(
        repo_root=root,
        db_path=root / ".state" / "state.db",
        logs_root=root / ".logs",
        generated_root=root / ".generated"
    )

