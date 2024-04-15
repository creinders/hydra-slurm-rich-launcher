# Copyright (c) Facebook, Inc. and its affiliates. 
# Copyright (c) 2024 Christoph Reinders and Frederik Schubert
# All Rights Reserved
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from hydra.core.config_store import ConfigStore


@dataclass
class BaseQueueConf:
    """Configuration shared by all executors"""

    submitit_folder: str = "${hydra.sweep.dir}/.submitit/%j"

    # maximum time for the job in minutes
    timeout_min: int = 60
    # number of cpus to use for each task
    cpus_per_task: Optional[int] = None
    # number of gpus to use on each node
    gpus_per_node: Optional[int] = None
    # number of tasks to spawn on each node
    tasks_per_node: int = 1
    # memory to reserve for the job on each node (in GB)
    mem_gb: Optional[int] = None
    # number of nodes to use for the job
    nodes: int = 1
    # name of the job
    name: str = "${hydra.job.name}"
    # redirect stderr to stdout
    stderr_to_stdout: bool = False


@dataclass
class RichQueueConf(BaseQueueConf):
    # Additional parameters
    slurm_query_interval_s: int = 15
    filter_job_ids: Optional[str] = None
    max_retries: int = 3
    retry_strategy: str = 'prompt'  # 'prompt', 'never', 'always'
    le_mode: str = 'auto'  # low energy mode: on, off, auto (HYDRA_SLURM_PROGRESS_LE_MODE)


@dataclass
class SlurmQueueConf(RichQueueConf):
    """Slurm configuration overrides and specific parameters"""

    _target_: str = (
        "hydra_plugins.hydra_slurm_rich_launcher.slurm_rich_launcher.SlurmLauncher"
    )

    # Params are used to configure sbatch, for more info check:
    # https://github.com/facebookincubator/submitit/blob/master/submitit/slurm/slurm.py

    # Following parameters are slurm specific
    # More information: https://slurm.schedmd.com/sbatch.html
    #
    # slurm partition to use on the cluster
    partition: Optional[str] = None
    qos: Optional[str] = None
    comment: Optional[str] = None
    constraint: Optional[str] = None
    exclude: Optional[str] = None
    gres: Optional[str] = None
    cpus_per_gpu: Optional[int] = None
    gpus_per_task: Optional[int] = None
    mem_per_gpu: Optional[str] = None
    mem_per_cpu: Optional[str] = None
    account: Optional[str] = None

    # Following parameters are submitit specifics
    #
    # USR1 signal delay before timeout
    signal_delay_s: int = 120
    # Maximum number of retries on job timeout.
    # Change this only after you confirmed your code can handle re-submission
    # by properly resuming from the latest stored checkpoint.
    # check the following for more info on slurm_max_num_timeout
    # https://github.com/facebookincubator/submitit/blob/master/docs/checkpointing.md
    max_num_timeout: int = 0
    # Useful to add parameters which are not currently available in the plugin.
    # Eg: {"mail-user": "blublu@fb.com", "mail-type": "BEGIN"}
    additional_parameters: Dict[str, Any] = field(default_factory=dict)
    # Maximum number of jobs running in parallel
    array_parallelism: int = 256
    # A list of commands to run in sbatch before running srun
    setup: Optional[List[str]] = None


@dataclass
class LocalQueueConf(RichQueueConf):
    _target_: str = (
        "hydra_plugins.hydra_slurm_rich_launcher.slurm_rich_launcher.LocalLauncher"
    )

# Registering the SLURM and Local launchers
ConfigStore.instance().store(
    group="hydra/launcher",
    name="slurm_rich",
    node=SlurmQueueConf(),
    provider="slurm_rich_launcher",
)

ConfigStore.instance().store(
    group="hydra/launcher",
    name="local_rich",
    node=LocalQueueConf(),
    provider="slurm_rich_launcher",
)
