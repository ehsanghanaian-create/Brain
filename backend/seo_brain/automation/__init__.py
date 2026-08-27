"""Automation layer: JobQueue abstraction (phase 1) → scheduler + pipelines (phase 8)."""
from .queue import InProcessJobQueue, Job, JobQueue, JobRun, PersistentJobQueue, get_job_queue

__all__ = ["Job", "JobRun", "JobQueue", "InProcessJobQueue", "PersistentJobQueue", "get_job_queue"]
