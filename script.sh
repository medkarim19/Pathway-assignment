#!/usr/bin/env bash
set -e

echo "========================================"
echo " Pathway SLURM Prototype – Bootstrap"
echo "========================================"

echo "Creating virtual environment..."

if [ ! -d ".venv" ]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "Virtual environment ready"

echo "Verifying SLURM cluster..."

docker exec -it slurmctld sinfo || {
  echo "SLURM not responding"
  exit 1
}

echo "SLURM cluster is running"

echo "Cleaning previous state..."

rm -rf .state .generated .logs slurm-*.out || true

echo "Deploying example application..."

python prodctl.py deploy specs/example-app.yaml

echo "Current status:"

python prodctl.py status example-app

echo
echo "========================================"
echo "Deployed successfully"
echo "========================================"
echo
echo "Next commands:"
echo "  python prodctl.py status example-app"
echo "  python prodctl.py logs-out example-app 0"
echo "  python prodctl.py scale example-app 4 specs/example-app.yaml"
