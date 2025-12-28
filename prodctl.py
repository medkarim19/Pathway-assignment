from pathlib import Path
import subprocess
import typer
from rich.console import Console
from rich.table import Table

from controller.config import default_paths
from controller.state import StateDB
from controller import lifecycle
from controller import slurm

# CLI application entry point
app = typer.Typer(no_args_is_help=True)
console = Console()


# load project paths and open the state database
def _db():
    paths = default_paths()
    return paths, StateDB(paths.db_path)


# replace SLURM placeholders (%x, %j) to show real log paths
def resolve_log_path(template: str, app: str, replica: int, job_id: str) -> str:
    return (
        template
        .replace("%x", f"{app}-{replica}")
        .replace("%j", job_id)
    )


# deploy an application from a YAML spec
@app.command()
def deploy(spec: Path = typer.Argument(..., help="Path to deployment YAML spec")):
    paths, db = _db()
    name = lifecycle.deploy(paths, db, spec)
    console.print(f"[bold green]Deployed[/bold green] app={name} using spec={spec}")


# show status of all replicas of an app
@app.command()
def status(name: str):
    paths, db = _db()

    # update job states from SLURM
    lifecycle.refresh_status(db, name)

    # fetch replicas from DB
    reps = db.list_replicas(name)

    # table output
    t = Table(title=f"Status: {name}")
    t.add_column("Replica", justify="right")
    t.add_column("SLURM Job ID")
    t.add_column("State")
    t.add_column("Log Out")
    t.add_column("Log Err")

    # add one row per replica
    for r in reps:
        log_out = resolve_log_path(
            r.log_out, r.app, r.replica_id, r.slurm_job_id
        )
        log_err = resolve_log_path(
            r.log_err, r.app, r.replica_id, r.slurm_job_id
        )

        t.add_row(
            str(r.replica_id),
            r.slurm_job_id,
            r.status,
            log_out,
            log_err,
        )

    console.print(t)


# fetch and display stdout logs
@app.command(name="logs-out")
def logs_out(name: str, replica: int):
    _, db = _db()

    # get replica info from DB
    rec = db.get_replica(name, replica)
    if not rec:
        console.print("[red]Replica not found[/red]")
        raise typer.Exit(1)

    job_id = rec.slurm_job_id

    # find which node ran the job
    node = slurm.job_node(job_id)
    if not node:
        console.print("[red]Unable to determine execution node[/red]")
        raise typer.Exit(1)

    # copy log file from compute node to host
    host_log = f"./slurm-{job_id}.out"
    slurm.copy_stdout_log(
        rec.log_out,
        rec.app,
        rec.replica_id,
        job_id,
        node,
        host_log,
    )

    # display log content
    console.print(f"[green]Log copied from {node} → {host_log}[/green]")
    with open(host_log) as f:
        print(f.read())


# fetch and display stderr logs
@app.command(name="logs-err")
def logs_err(name: str, replica: int):
    _, db = _db()

    # get replica info
    rec = db.get_replica(name, replica)
    if not rec:
        console.print("[red]Replica not found[/red]")
        raise typer.Exit(1)

    job_id = rec.slurm_job_id

    # find execution node
    node = slurm.job_node(job_id)
    if not node:
        console.print("[red]Unable to determine execution node[/red]")
        raise typer.Exit(1)

    # resolve real stderr path
    container_path = (
        rec.log_err
        .replace("%x", f"{rec.app}-{rec.replica_id}")
        .replace("%j", job_id)
    )

    # read log directly from container
    cmd = ["docker", "exec", node, "cat", container_path]
    p = subprocess.run(cmd, capture_output=True, text=True)

    if p.returncode != 0:
        console.print("[yellow]Log not available yet[/yellow]")
        raise typer.Exit(0)

    console.print(p.stdout)


# scale number of replicas
@app.command()
def scale(
    name: str,
    replicas: int,
    spec: Path = typer.Argument(..., help="Spec YAML"),
):
    paths, db = _db()
    lifecycle.scale(paths, db, name, spec, replicas)
    console.print(f"[bold cyan]Scaled[/bold cyan] app={name} -> replicas={replicas}")


# delete an application and its jobs
@app.command()
def delete(name: str):
    _, db = _db()
    lifecycle.delete_app(db, name)
    console.print(f"[bold red]Deleted[/bold red] app={name}")


# run CLI
if __name__ == "__main__":
    app()

