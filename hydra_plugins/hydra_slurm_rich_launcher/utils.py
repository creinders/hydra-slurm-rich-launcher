from typing import Sequence


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