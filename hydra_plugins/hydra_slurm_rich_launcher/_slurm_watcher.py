import typing as tp
import logging
from submitit.slurm.slurm import SlurmInfoWatcher

log = logging.getLogger(__name__)


class ExtendedSlurmInfoWatcher(SlurmInfoWatcher):

    def _make_command(self) -> tp.Optional[tp.List[str]]:
        # asking for array id will return all status
        # on the other end, asking for each and every one of them individually takes a huge amount of time
        to_check = {x.split("_")[0] for x in self._registered - self._finished}
        if not to_check:
            return None
        command = ["sacct", "-o", "JobID,State,NodeList,Start,End", "--parsable2"]
        for jid in to_check:
            command.extend(["-j", str(jid)])

        return command
    def read_info(self, string: tp.Union[bytes, str]) -> tp.Dict[str, tp.Dict[str, str]]:
        data = super().read_info(string)
        return data
    
    # compared to parent, we do not reset the start time
    def register_job(self, job_id: str) -> None:
        """Register a job on the instance for shared update"""
        assert isinstance(job_id, str)
        self._registered.add(job_id)
        # self._start_time = _time.time()
        # self._last_status_check = float("-inf")