from pathlib import Path

def render_sbatch_script(
    app: str,
    replica_id: int,
    workdir: Path,
    entrypoint: str,
    cpus: int,
    mem_mb: int,
    partition: str,
    time_limit: str,
    log_out: str,
    log_err: str,
) -> str:
    return f"""#!/usr/bin/env bash
#SBATCH --job-name={app}-{replica_id}
#SBATCH --partition={partition}
#SBATCH --time={time_limit}
#SBATCH --cpus-per-task={cpus}
#SBATCH --mem={mem_mb}
#SBATCH --output={log_out}
#SBATCH --error={log_err}

set -e

echo "=== SLURM METADATA ==="
echo "Job ID     : $SLURM_JOB_ID"
echo "Job Name   : $SLURM_JOB_NAME"
echo "Node       : $(hostname)"
echo "Start Time : $(date)"
echo "======================"

echo "pwd before cd: $(pwd)"
cd {workdir}
echo "pwd after cd: $(pwd)"

echo "listing:"
ls -l

export APP_NAME="{app}"
export REPLICA_ID="{replica_id}"

chmod +x {entrypoint}
{entrypoint}

echo "End Time   : $(date)"
"""

