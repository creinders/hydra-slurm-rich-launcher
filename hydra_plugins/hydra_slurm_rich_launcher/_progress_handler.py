from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn, BarColumn
from hydra.core.utils import filter_overrides, JobStatus
from rich.console import Group
from dataclasses import dataclass
from enum import Enum
from typing import List, Optional
from rich.rule import Rule
from rich.live import Live

from hydra.core.utils import JobReturn
from submitit.core.core import Job
from datetime import datetime
import math
import logging

class Status(Enum):
    PENDING = 'PENDING'
    CONFIGURING = 'CONFIGURING'
    SUCCESS = 'SUCCESS'
    RUNNING = 'RUNNING'
    FAILED = 'FAILED'
    UNKNOWN = 'UNKNOWN'

status_to_number = {
    Status.PENDING: 0,
    Status.CONFIGURING: 1,
    Status.RUNNING: 1,
    Status.SUCCESS: 2,
    Status.FAILED: 2,
    Status.UNKNOWN: 0,
}

dates_scheduled = {}
dates_start = {}
dates_end = {}

_get_time = lambda: datetime.now().timestamp()

log = logging.getLogger(__name__)


@dataclass
class TaskInfo:
    job_idx: int
    job_id: str # job name
    status: Status
    description: str
    done: bool
    visible: bool = True

    date_scheduled: Optional[float] = None
    date_start: Optional[float] = None
    date_end: Optional[float] = None

    def update_dates(self):
        if status_to_number[self.status] >= status_to_number[Status.PENDING] and self.date_scheduled is None:
            if self.job_id in dates_scheduled:
                self.date_scheduled = dates_scheduled[self.job_id]
            else:
                self.date_scheduled = _get_time()
                dates_scheduled[self.job_id] = self.date_scheduled

        if status_to_number[self.status] >= status_to_number[Status.RUNNING] and self.date_start is None:
            if self.job_id in dates_start:
                self.date_start = dates_start[self.job_id]
            else:
                self.date_start = _get_time()
                dates_start[self.job_id] = self.date_start

        if status_to_number[self.status] >= status_to_number[Status.SUCCESS] and self.date_end is None:
            if self.job_id in dates_end:
                self.date_end = dates_end[self.job_id]
            else:
                self.date_end = _get_time()
                dates_end[self.job_id] = self.date_end

    def sort_date(self):
        if self.date_end is not None:
            return -self.date_end
        elif self.date_start is not None:
            return -self.date_start
        else:
            return self.date_scheduled


class InteractiveProgressHandler:

    def __init__(self, le_mode=True) -> None:
        self.le_mode = le_mode

        columns = [
            TextColumn("{task.fields[idx]}", ),  # table_column=Column(width=3, no_wrap=True)
            TextColumn("{task.fields[status]}"),
            SpinnerColumn() if not le_mode else None,
            TimeElapsedColumn(),
            TextColumn("{task.fields[job_id]}"),
            TextColumn("{task.description}")
        ]

        columns = [c for c in columns if c is not None] # filter nones
        
        self.progress = Progress(
            *columns,
            get_time=_get_time,
        )

        self.overall_progress = Progress(
            TimeElapsedColumn(), 
            TextColumn("{task.fields[total_text]}"),
            BarColumn(), 
            TextColumn("{task.description}"),
            get_time=_get_time,

        )
        self.progress_group = Group(
            Rule(style='#AAAAAA'),
            self.progress,
            Rule(style='#AAAAAA'),
            self.overall_progress,
        )
        self.live = Live(self.progress_group, auto_refresh=not le_mode)
        self.idx_to_progress_task_id = {}

        self.overall_task_id = self.overall_progress.add_task("", total=0, total_text="")
        overall_task = self.overall_progress._tasks[self.overall_task_id]
        overall_task.start_time = math.floor(_get_time()) # slurm time is in seconds       

    def get_progress_task(self, idx):
        
        if idx in self.idx_to_progress_task_id:
            progress_task_id = self.idx_to_progress_task_id[idx]
        else:
            progress_task_id = self.progress.add_task("", total=1, start=False, idx="", job_id='', status=' ', status_text='')

            self.idx_to_progress_task_id[idx] = progress_task_id

        return self.progress._tasks[progress_task_id]

    def start(self):
        self.live.start()

    def stop(self):
        self.live.stop()

    def refresh(self, tasks: List[TaskInfo]):

        max_tasks = max(min(self.live.console.size.height - 3, 30), 3)
        for task in tasks:
            task.update_dates()

        num_done = 0

        status = [Status.PENDING, Status.RUNNING, Status.SUCCESS, Status.FAILED]
        num_per_status = {s: len([task for task in tasks if task.status == s]) for s in status}

        for task in tasks:
            if task.done:
                num_done += 1

        tasks_sorted = self.smart_task_selection(tasks, max_tasks=max_tasks)
        tasks_filtered = [t for t in tasks_sorted if t.visible]

        for index, task in enumerate(tasks_filtered):
            progress_task = self.get_progress_task(index)

            if task.status == Status.PENDING:
                status_icon = '🕛'
            elif task.status == Status.CONFIGURING:
                status_icon = '🚀'
            elif task.status == Status.RUNNING:
                status_icon = '🏃'
            elif task.status == Status.SUCCESS:
                status_icon = '🏁'
            elif task.status == Status.FAILED:
                status_icon = '💥'
            else:
                status_icon = '❓'
                print(f'unknown state: {task.status}')

            progress_task.start_time = task.date_start
            progress_task.stop_time = task.date_end
            progress_task.description = task.description
            progress_task.fields['idx'] = f"#{task.job_idx}"
            progress_task.fields['status'] = status_icon
            # progress_task.fields['status_text'] = s
            progress_task.fields['job_id'] = task.job_id
            progress_task.finished_time = None # reset field if progress is reused

            if task.done:
                if not progress_task.finished:
                    self.progress.update(progress_task.id, completed=1)
            
            progress_task.visible = True

        # hide progress tasks if number of tasks decreases
        for index in range(len(tasks_filtered), len(self.idx_to_progress_task_id)):
            progress_task = self.get_progress_task(index)
            progress_task.visible = False

        top_descr = "[magenta] %s pending [cyan] %s running [green]%d succeded [red] %s failed" % (
            num_per_status[Status.PENDING], num_per_status[Status.RUNNING], num_per_status[Status.SUCCESS], num_per_status[Status.FAILED], )
        total_text = "%d Runs" % (len(tasks), )
        self.overall_progress.update(self.overall_task_id, description=top_descr, total=len(tasks), completed=num_done, total_text=total_text)

        if self.le_mode:
            self.live.refresh()

        return num_done == len(tasks)

    def loop(self, job_idx, jobs: list[Job], job_overrides, slurm_query_interval_s=None, common_overrides=[]):
        import time

        if slurm_query_interval_s is None:
            slurm_query_interval_s = 15

        if slurm_query_interval_s < 15:
            log.warning('WARNING: slurm_query_interval_s should not be smaller than 15 seconds otherwise slurm will be queried too often')

        self.start()
        while True:
            jobs[0].get_info(mode="force")  # Force update once to sync the state
            tasks = self.task_from_slurm(job_idx, jobs, job_overrides, common_overrides=common_overrides)

            done = self.refresh(tasks=tasks)

            if done:
                break

            time.sleep(slurm_query_interval_s)

        self.stop()

    def task_from_slurm(self, job_idx, jobs: list[Job], job_overrides, common_overrides):
        tasks = []
        common_overrides = set(common_overrides or [])

        for (idx, job, overrides) in zip(job_idx, jobs, job_overrides):
            description = " ".join([override for override in filter_overrides(overrides) if override not in common_overrides])
            state = job.state.upper()

            date_start_str = job.get_info(mode="cache").get("Start")
            date_end_str = job.get_info(mode="cache").get("End")

            date_start = self.parse_date(date_start_str)
            date_end = self.parse_date(date_end_str)

            done = job.done()
            task_status: Optional[Status] = None
            if done:
                try:
                    r = job.result()
                    hydra_status = r.status

                    if hydra_status == JobStatus.COMPLETED:
                        task_status = Status.SUCCESS 
                    elif hydra_status == JobStatus.FAILED:
                        task_status = Status.FAILED
                    else:
                        task_status = Status.UNKNOWN

                except:
                    task_status = Status.FAILED
            elif state == 'RUNNING':
                task_status = Status.RUNNING
            elif state == 'PENDING':
                task_status = Status.PENDING
            elif state == 'CONFIGURING':
                task_status = Status.CONFIGURING
            elif state == 'UNKNOWN':  # job needs some time until it is visible in slurm controller
                task_status = Status.PENDING
            else:
                task_status = Status.UNKNOWN

            task = TaskInfo(
                job_idx=idx,
                job_id=job.job_id,
                status=task_status,
                description=description,
                done=done,
                date_start=date_start,
                date_end=date_end
            )
            tasks.append(task)
        return tasks

    @staticmethod
    def get_job_result(job):
        # get job result without raising
        
        try:
            return job.result()
        except Exception as e:
            ret = JobReturn()
            ret.return_value = e
            ret.status = JobStatus.FAILED

            return ret
        
    @staticmethod
    def parse_date(date_str):
        if date_str is None or date_str == "Unknown":
            return None
        else:
            return datetime.fromisoformat(date_str).timestamp()

    @staticmethod
    def smart_task_selection(tasks: List[TaskInfo], max_tasks=10):

        if len(tasks) <= max_tasks:
             # smart reordering only if necessary
            return tasks
        
        import heapq
        num_tasks = len(tasks)
        max_tasks = min(max_tasks, num_tasks)

        status_order = [Status.PENDING, Status.CONFIGURING, Status.RUNNING, Status.SUCCESS, Status.FAILED, Status.UNKNOWN]
        tasks = sorted(tasks, key=lambda x: (status_order.index(x.status), x.sort_date()), reverse=False)

        group_to_status = {
            'pending': [Status.PENDING],
            'running': [Status.CONFIGURING, Status.RUNNING],
            'success': [Status.SUCCESS],
            'failed': [Status.FAILED, Status.UNKNOWN],
        }
        status_to_group = {s: key for key, statuses in group_to_status.items() for s in statuses}
        groups = group_to_status.keys()
        tasks_per_group = {key: [] for key in groups}
        for task in tasks:
            tasks_per_group[status_to_group[task.status]].append(task)

        # tasks_per_group = {key: [task for task in tasks if task.status == group_to_status[key]] for key in groups}
        nums_per_group = {key: len(tasks_per_group[key]) for key in groups}

        q = [(0, key) for key in groups if nums_per_group[key] > 0]

        nums_selected_per_group = {key: 0 for key in groups}

        for _ in range(max_tasks):
            _, key = heapq.heappop(q)

            nums_selected_per_group[key] += 1
            if nums_selected_per_group[key] < nums_per_group[key]:
                heapq.heappush(q, (nums_selected_per_group[key], key))

        for key, group_tasks in tasks_per_group.items():
            for task in group_tasks:
                task.visible = False
            
            num_selected = nums_selected_per_group[key]
            num_top = int((num_selected + 0.5) // 2)
            num_bottom = num_selected - num_top

            for task in group_tasks[:num_top]:
                task.visible = True
            for task in group_tasks[-num_bottom:]:
                task.visible = True

        return tasks
