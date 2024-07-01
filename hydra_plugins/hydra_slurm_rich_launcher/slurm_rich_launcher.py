# Copyright (c) Facebook, Inc. and its affiliates. 
# Copyright (c) 2024 Christoph Reinders and Frederik Schubert
# All Rights Reserved
import atexit
import logging
import os
from pathlib import Path
from time import sleep
import traceback
from typing import Any, Dict, List, Optional, Sequence

from hydra.core.singleton import Singleton
from hydra.core.utils import JobReturn, run_job, setup_globals, JobStatus
from hydra.plugins.launcher import Launcher
from hydra.types import HydraContext, TaskFunction
from omegaconf import DictConfig, OmegaConf, open_dict

from hydra_plugins.hydra_slurm_rich_launcher.utils import get_common_overrides, ask_cancel_jobs

from .config import BaseQueueConf
from rich.prompt import Confirm
import sys

log = logging.getLogger(__name__)


class BaseSlurmRichLauncher(Launcher):

    _EXECUTOR = "abstract"

    def __init__(self, **params: Any) -> None:
        self.params = {}
        for k, v in params.items():
            if OmegaConf.is_config(v):
                v = OmegaConf.to_container(v, resolve=True)
            self.params[k] = v

        self.config: Optional[DictConfig] = None
        self.task_function: Optional[TaskFunction] = None
        self.sweep_configs: Optional[TaskFunction] = None
        self.hydra_context: Optional[HydraContext] = None

    def setup(
        self,
        *,
        hydra_context: HydraContext,
        task_function: TaskFunction,
        config: DictConfig,
    ) -> None:
        self.config = config
        self.hydra_context = hydra_context
        self.task_function = task_function

    def __call__(
        self,
        sweep_overrides: List[str],
        job_dir_key: str,
        job_num: int,
        job_id: str,
        singleton_state: Dict[type, Singleton],
    ) -> JobReturn:
        # lazy import to ensure plugin discovery remains fast
        import submitit

        assert self.hydra_context is not None
        assert self.config is not None
        assert self.task_function is not None

        Singleton.set_state(singleton_state)
        setup_globals()
        sweep_config = self.hydra_context.config_loader.load_sweep_config(
            self.config, sweep_overrides
        )

        with open_dict(sweep_config.hydra.job) as job:
            # Populate new job variables
            job.id = submitit.JobEnvironment().job_id  # type: ignore
            sweep_config.hydra.job.num = job_num

        ret = run_job(
            hydra_context=self.hydra_context,
            task_function=self.task_function,
            config=sweep_config,
            job_dir_key=job_dir_key,
            job_subdir_key="hydra.sweep.subdir",
        )

        if ret.status == JobStatus.FAILED:
            # log error because its catched and not printed to job-log
            print(ret._return_value, file=sys.stderr)
            
        return ret

    def checkpoint(self, *args: Any, **kwargs: Any) -> Any:
        """Resubmit the current callable at its current state with the same initial arguments."""
        # lazy import to ensure plugin discovery remains fast
        import submitit

        return submitit.helpers.DelayedSubmission(self, *args, **kwargs)

    def launch(
        self, job_overrides: Sequence[Sequence[str]], initial_job_idx: int
    ) -> Sequence[JobReturn]:
        # lazy import to ensure plugin discovery remains fast
        import submitit

        assert self.config is not None

        num_jobs = len(job_overrides)
        assert num_jobs > 0
        params = self.params
        # build executor
        init_params = {"folder": self.params["submitit_folder"]}
        specific_init_keys = {"max_num_timeout"}
        additional_keys = ["slurm_query_interval_s", "filter_job_ids", "max_retries", "retry_strategy", "le_mode"]

        init_params.update(
            **{
                f"{self._EXECUTOR}_{x}": y
                for x, y in params.items()
                if x in specific_init_keys and not x in additional_keys
            }
        )
        init_keys = specific_init_keys | {"submitit_folder"}
        executor = submitit.AutoExecutor(cluster=self._EXECUTOR, **init_params)

        # specify resources/parameters
        baseparams = set(OmegaConf.structured(BaseQueueConf).keys())
        params = {
            x if x in baseparams else f"{self._EXECUTOR}_{x}": y
            for x, y in params.items()
            if x not in init_keys and x not in additional_keys
        }
        executor.update_parameters(**params)

        
        if self.params["le_mode"] == 'auto':
            le_mode = False
            if "HYDRA_SLURM_PROGRESS_LE_MODE" in os.environ:
                le_mode = os.environ['HYDRA_SLURM_PROGRESS_LE_MODE'] in ('y', 'yes', 't', 'true', 'True', 'on', '1')

        else:
            assert self.params["le_mode"] in ['off', 'on']
            le_mode = self.params["le_mode"] == 'on'

        log.info(
            f"Submitit '{self._EXECUTOR}' sweep output dir: "
            f"{os.path.abspath(self.config.hydra.sweep.dir)}"
        )

        if le_mode:
            log.info('Running progress visualization in low energy mode')
        
        sweep_dir = Path(str(self.config.hydra.sweep.dir))
        sweep_dir.mkdir(parents=True, exist_ok=True)
        if "mode" in self.config.hydra.sweep:
            mode = int(str(self.config.hydra.sweep.mode), 8)
            os.chmod(sweep_dir, mode=mode)

        job_ids = [initial_job_idx + i for i in range(len(job_overrides))]
        job_params: List[Any] = []
        filter_job_ids = [int(idx) for idx in self.params["filter_job_ids"].split(",")] if isinstance(self.params["filter_job_ids"], str) else None
        if filter_job_ids:
            log.info(f"Only executing {len(filter_job_ids)} of {len(job_ids)} jobs")
        for idx, overrides in zip(job_ids, job_overrides):
            job_params.append(
                (
                    list(overrides),
                    "hydra.sweep.dir",
                    idx,
                    f"job_id_for_{idx}",
                    Singleton.get_state(),
                )
            )
        
        n_jobs = len(job_params) if not filter_job_ids else len(filter_job_ids)
        log.info("Starting {} {}".format(n_jobs, 'jobs' if n_jobs > 1 else 'job'))

        results_completed = []
        results_failed = []
        missing_job_ids = job_ids if not filter_job_ids else filter_job_ids

        for retry_idx in range(self.params["max_retries"] + 1):
            job_overrides_filtered = [overrides for job_id, overrides in zip(job_ids, job_overrides) if job_id in missing_job_ids]
            common_overrides = get_common_overrides(job_overrides_filtered) if len(job_overrides_filtered) > 1 else []
            if common_overrides:
                log.info("Common overrides: {}".format(" ".join(common_overrides)))
            job_params_filtered = [job_param for job_id, job_param in zip(job_ids, job_params) if job_id in missing_job_ids]

            results = self.execute_jobs(executor, missing_job_ids, job_overrides_filtered, job_params_filtered, common_overrides=common_overrides, le_mode=le_mode)
            job_ids_failed = [i for i, r in zip(missing_job_ids, results) if r.status == JobStatus.FAILED]
            results_completed.extend([r for r in results if r.status == JobStatus.COMPLETED])
            results_failed = [r for r, job_id in zip(results, missing_job_ids) if job_id in job_ids_failed]
            if job_ids_failed:
                log.warning("Retry {}/{}: {} jobs failed".format(retry_idx, self.params["max_retries"], len(job_ids_failed)))
                for result, job_id in zip(results_failed, missing_job_ids):
                    ex = result._return_value
                    log.error(f"Job {job_id} failed with the following error: ", exc_info=ex)
                    log.error(''.join(traceback.format_exception(type(ex), value=ex, tb=ex.__traceback__)))
                log.info("To manually retry the failed jobs, add the following overrides to your command: 'hydra.launcher.filter_job_ids=\"{}\"'".format(",".join([str(i) for i in job_ids_failed]))) 
                if self.params["retry_strategy"] == "never" or retry_idx == self.params["max_retries"]:
                    break
                elif self.params["retry_strategy"] == "always":
                    pass
                elif self.params["retry_strategy"] == "prompt":
                    should_retry = Confirm.ask("Do you want to automatically retry the failed runs?", default='y')
                    if not should_retry:
                        break
            else:
                break
            missing_job_ids = job_ids_failed
        if results_failed:
            raise RuntimeError(f"{len(results_failed)} jobs failed")
        return results_completed

    
    def execute_jobs(self, executor, job_idx, job_overrides, job_params: List[Any], common_overrides, le_mode=False) -> List[JobReturn]:
        jobs = executor.map_array(self, *zip(*job_params))
        from ._slurm_watcher import ExtendedSlurmInfoWatcher
        watcher = ExtendedSlurmInfoWatcher() # use the same watcher for all jobs to avoid multiple sacct calls
        for job in jobs:
            job.watcher = watcher
        atexit.register(lambda: print("\x1b[?25h"))  
        sleep(1) # if the SLURM IDs have been reset, submitit finds old runs if the new are not started

        from ._progress_handler import InteractiveProgressHandler

        progress_handler = InteractiveProgressHandler(le_mode=le_mode)

        try:
            progress_handler.loop(job_idx, jobs, job_overrides, slurm_query_interval_s=self.params["slurm_query_interval_s"], common_overrides=common_overrides)
        except KeyboardInterrupt:
            progress_handler.live.stop()
            ask_cancel_jobs(jobs)
            exit(1)

        return [InteractiveProgressHandler.get_job_result(j) for j in jobs]


class LocalLauncher(BaseSlurmRichLauncher):
    _EXECUTOR = "local"


class SlurmLauncher(BaseSlurmRichLauncher):
    _EXECUTOR = "slurm"
