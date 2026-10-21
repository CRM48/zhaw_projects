import csv
import json
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from src.common.config import EXPERIMENT_RESULTS_DIR


# ---------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------

def current_utc_time() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_run_id(experiment: str, architecture: str) -> str:
    """
    Create a unique identifier for one experiment run.
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    unique_id = uuid.uuid4().hex[:8]
    return (f"{experiment}_{architecture}_{timestamp}_{unique_id}")


# ---------------------------------------------------------------------
# Experiment run
# ---------------------------------------------------------------------

class ExperimentRun:
    """
    Stores metadata, summary metrics and detailed records for one
    experiment run.
    """

    def __init__(self, experiment: str, architecture: str, metadata: dict[str, Any] | None = None):

        self.experiment = experiment
        self.architecture = architecture

        self.run_id = create_run_id(experiment=experiment, architecture=architecture)

        self.started_at = current_utc_time()

        self.completed_at = None
        self.duration_seconds = None

        self.metadata = metadata or {}
        self.metrics = {}

        self.status = "running"
        self.error = None

        self._start_clock = (time.perf_counter())

        self.run_dir = (EXPERIMENT_RESULTS_DIR / self.run_id)

        self.run_dir.mkdir(parents=True, exist_ok=True)

        self._write_summary()


    # -----------------------------------------------------------------
    # Detailed records
    # -----------------------------------------------------------------

    def save_records(self, filename: str, records: list[dict[str, Any]]) -> None:
        """
        Save detailed measurement records as CSV.
        """

        if not records:
            return

        file_path = (self.run_dir / filename)

        fieldnames = list(records[0].keys())

        for record in records:
            for key in record.keys():
                if key not in fieldnames:
                    fieldnames.append(key)

        with file_path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(records)


    # -----------------------------------------------------------------
    # Completion
    # -----------------------------------------------------------------

    def complete(self, metrics: dict[str, Any], status: str = "completed", error: str | None = None) -> None:
        """
        Complete the experiment run and save its final summary.
        """

        self.duration_seconds = (time.perf_counter() - self._start_clock)

        self.completed_at = (current_utc_time())

        self.metrics = metrics

        self.status = status
        self.error = error

        self._write_summary()


    # -----------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------

    def _write_summary(self) -> None:
        """
        Save the current run summary as JSON.
        """

        summary = {
            "run_id": self.run_id,
            "experiment": self.experiment,
            "architecture": self.architecture,
            "status": self.status,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "duration_seconds": self.duration_seconds,
            "metadata": self.metadata,
            "metrics": self.metrics,
            "error": self.error
        }

        file_path = (self.run_dir / "summary.json")

        with file_path.open("w", encoding="utf-8") as file:
            json.dump(summary, file, indent=2, default=str)

