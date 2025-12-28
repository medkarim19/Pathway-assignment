from pathlib import Path
from typing import Dict, Any
import time
import yaml
import uuid
import subprocess

from .config import Paths
from .state import StateDB, ReplicaRecord
from . import slurm
from .render import render_sbatch_script


# Compute node used to stage code into shared /data
COMPUTE_STAGE_NODE = "c1"


def load_spec(spec_path: Path) -> Dict[str, Any]:
    # Load and validate deployment YAML
    data = yaml.safe_load(spec_path.read_text(encoding="utf-8"))
    for k in ["name", "workdir", "entrypoint", "resources", "replicas", "slurm", "logs_dir"]:
        if k not in data:
            raise ValueError(f"Spec missing required key: {k}")
    return data


def ensure_dirs(paths: Paths, spec: Dict[str, Any]) -> None:
    # Ensure required directories exist
    paths.db_path.parent.mkdir(parents=True, exist_ok=True)
    paths.generated_root.mkdir(parents=True, exist_ok=True)
    (paths.repo_root / spec["logs_dir"]).mkdir(parents=True, exist_ok=True)


def _docker_exec(container: str, cmd: list[str]) -> subprocess.CompletedProcess:
    # Run a command inside a Docker container
    return subprocess.run(
        ["docker", "exec", container] + cmd,
        capture_output=True,
        text=True
    )


def _docker_cp_to_container(src: Path, container: str, dst: str) -> None:
    # Copy files from host to container
    p = subprocess.run(
        ["docker", "cp", str(src), f"{container}:{dst}"],
        capture_output=True,
        text=True
    )
    if p.returncode != 0:
        raise RuntimeError(p.stderr)


def stage_app_to_shared_data(app: str, replica_id: int, host_app_dir: Path) -> Path:
    # Stage application code into shared /data directory
    stage_dir = Path(f"/data/apps/{app}/replica-{replica_id}")

    _docker_exec(COMPUTE_STAGE_NODE, ["mkdir", "-p", str(stage_dir)])

    tmp_dir = f"/tmp/{app}-{replica_id}-{uuid.uuid4().hex}"
    _docker_exec(COMPUTE_STAGE_NODE, ["mkdir", "-p", tmp_dir])

    _docker_cp_to_container(host_app_dir, COMPUTE_STAGE_NODE, tmp_dir)

    base = host_app_dir.name
    _docker_exec(
        COMPUTE_STAGE_NODE,
        ["bash", "-lc", f"cp -r {tmp_dir}/{base}/. {stage_dir}/"]
    )

    _docker_exec(COMPUTE_STAGE_NODE, ["rm", "-rf", tmp_dir])
    _docker_exec(COMPUTE_STAGE_NODE, ["chmod", "+x", str(stage_dir / "run.sh")])

    return stage_dir


def submit_replica(paths: Paths, db: StateDB, spec: Dict[str, Any], replica_id: int) -> str:
    app = spec["name"]

    host_app_dir = (paths.repo_root / spec["workdir"]).resolve()
    entrypoint = spec["entrypoint"]

    cpus = int(spec["resources"]["cpus"])
    mem_mb = int(spec["resources"]["mem_mb"])
    partition = spec["slurm"]["partition"]
    time_limit = spec["slurm"]["time_limit"]

    # Stage code to shared filesystem
    workdir = stage_app_to_shared_data(app, replica_id, host_app_dir)

    # SLURM-managed log paths
    log_out = "/data/slurm-%x-%j.out"
    log_err = "/data/slurm-%x-%j.err"

    script_text = render_sbatch_script(
        app=app,
        replica_id=replica_id,
        workdir=workdir,
        entrypoint=entrypoint,
        cpus=cpus,
        mem_mb=mem_mb,
        partition=partition,
        time_limit=time_limit,
        log_out=log_out,
        log_err=log_err,
    )

    script_dir = paths.generated_root / app
    script_dir.mkdir(parents=True, exist_ok=True)
    script_path = script_dir / f"replica-{replica_id}.sbatch"
    script_path.write_text(script_text, encoding="utf-8")

    # Submit job to SLURM
    res = slurm.sbatch(str(script_path))

    # Persist job metadata
    db.upsert_replica(
        ReplicaRecord(
            app=app,
            replica_id=replica_id,
            slurm_job_id=res.job_id,
            status="SUBMITTED",
            created_at=time.time(),
            log_out=log_out,
            log_err=log_err,
        )
    )

    return res.job_id


def deploy(paths: Paths, db: StateDB, spec_path: Path) -> str:
    # Deploy initial replicas
    spec = load_spec(spec_path)
    ensure_dirs(paths, spec)

    for rid in range(int(spec["replicas"])):
        submit_replica(paths, db, spec, rid)

    return spec["name"]


def scale(paths: Paths, db: StateDB, app: str, spec_path: Path, new_replicas: int) -> None:
    # Scale application replicas up or down
    spec = load_spec(spec_path)
    ensure_dirs(paths, spec)

    current = db.list_replicas(app)
    current_ids = {r.replica_id for r in current}

    for rid in range(new_replicas):
        if rid not in current_ids:
            submit_replica(paths, db, spec, rid)

    for r in current:
        if r.replica_id >= new_replicas:
            slurm.scancel(r.slurm_job_id)
            db.update_status(app, r.replica_id, "CANCELLED")


def refresh_status(db: StateDB, app: str) -> None:
    # Update job state from SLURM
    for r in db.list_replicas(app):
        st = slurm.resolve_state(r.slurm_job_id)
        db.update_status(app, r.replica_id, st)


def delete_app(db: StateDB, app: str) -> None:
    # Cancel jobs and remove app from DB
    for r in db.list_replicas(app):
        try:
            slurm.scancel(r.slurm_job_id)
        except Exception:
            pass
    db.delete_app(app)

