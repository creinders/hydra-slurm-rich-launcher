from typing import Sequence

from rich.prompt import Prompt
from submitit import Job


def get_common_overrides(job_overrides: Sequence[Sequence[str]]):
    assert len(job_overrides) > 0, "No overrides found"
    job_overrides_first = job_overrides[0]
    job_overrides_position = {k: v for v, k in enumerate(job_overrides_first)}
    common_overrides = set(job_overrides_first)

    for overrides in job_overrides:
        common_overrides = common_overrides.intersection(set(overrides))

    common_overrides = list(common_overrides)
    common_overrides.sort(key=lambda x: job_overrides_position[x])
    return common_overrides


def ask_cancel_jobs(jobs: Sequence[Job]) -> list[Job]:
    cancel_jobs = Prompt.ask(
        "Do you want to cancel jobs? ([n]o, [a]ll, [p]ending, [r]unning)",
        choices=["a", "p", "n", "r"], show_choices=False,  # Choices are shown in prompt
        default="n", show_default=True
    )
    if cancel_jobs == "n":
        return []

    pending_jobs = []
    running_jobs = []
    for job in jobs:
        state = job.state.upper()
        if state == "PENDING":
            pending_jobs.append(job)
        elif state in ["CONFIGURING", "RUNNING"]:
            running_jobs.append(job)

    jobs_to_cancel = []
    if cancel_jobs in ["a", "p"]:
        jobs_to_cancel += pending_jobs

    if cancel_jobs in ["a", "r"]:
        jobs_to_cancel += running_jobs

    for job in jobs_to_cancel:
        job.cancel(check=False)

    return jobs_to_cancel
