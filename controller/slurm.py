import subprocess
from dataclasses import dataclass
from typing import Optional
from pathlib import Path
import uuid

SLURM_CONTAINER = "slurmctld"

@dataclass
class SlurmSubmitResult:
    job_id: str
    raw: str


# internal helpers
def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def _docker_exec(cmd: list[str]) -> subprocess.CompletedProcess:
    return _run(["docker", "exec", SLURM_CONTAINER] + cmd)


def _docker_cp(src: Path, dst: str) -> None:
    p = _run(["docker", "cp", str(src), f"{SLURM_CONTAINER}:{dst}"])
    if p.returncode != 0:
        raise RuntimeError(f"docker cp failed:\n{p.stderr}")


# slurm commands
def sbatch(script_path: str) -> SlurmSubmitResult:
    """
    Submit an sbatch script to Slurm (inside slurmctld container).
    """
    script_path = Path(script_path)

    container_path = f"/tmp/{script_path.name}-{uuid.uuid4().hex}.sbatch"
    _docker_cp(script_path, container_path)

    p = _docker_exec(["sbatch", container_path])
    if p.returncode != 0:
        raise RuntimeError(
            f"sbatch failed:\nSTDOUT:\n{p.stdout}\nSTDERR:\n{p.stderr}"
        )

    job_id = p.stdout.strip().split()[-1]
    return SlurmSubmitResult(job_id=job_id, raw=p.stdout.strip())


def scancel(job_id: str) -> None:
    _docker_exec(["scancel", job_id])


def squeue_job_state(job_id: str) -> Optional[str]:
    p = _docker_exec(["squeue", "-h", "-j", job_id, "-o", "%T"])
    if p.returncode != 0:
        return None
    return p.stdout.strip() or None


def sacct_job_state(job_id: str) -> Optional[str]:
    p = _docker_exec(
        ["sacct", "-j", job_id, "--format=State", "-n", "-P"]
    )
    if p.returncode != 0:
        return None

    txt = p.stdout.strip()
    if not txt:
        return None

    return txt.split("|")[0].strip()


def resolve_state(job_id: str) -> str:
    s = squeue_job_state(job_id)
    if s:
        return s

    s2 = sacct_job_state(job_id)
    return s2 or "UNKNOWN"


# node + log handling
def job_node(job_id: str) -> Optional[str]:
    """
    Return compute node where job executed (c1, c2, ...)
    """
    p = _run(
        [
            "docker", "exec", SLURM_CONTAINER,
            "sacct", "-j", job_id,
            "--format=NodeList",
            "-n",
        ]
    )
    if p.returncode != 0:
        return None

    node = p.stdout.strip().split()[0]
    return node if node else None


def copy_stdout_log(
    log_template: str,
    app: str,
    replica: int,
    job_id: str,
    node: str,
    dest: str,
) -> None:
    """
    Copy SLURM stdout log from compute node to host,
    resolving %x and %j correctly.
    """

    # Resolve SLURM template (%x, %j)
    container_path = (
        log_template
        .replace("%x", f"{app}-{replica}")
        .replace("%j", job_id)
    )

    p = subprocess.run(
        ["docker", "cp", f"{node}:{container_path}", dest],
        capture_output=True,
        text=True,
    )

    if p.returncode != 0:
        raise RuntimeError(
            f"docker cp failed:\n{p.stderr}"
        )

