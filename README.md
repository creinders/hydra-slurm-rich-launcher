# Hydra Slurm Rich Launcher

<p align="center">
  <img src="https://github.com/creinders/hydra-slurm-rich-launcher/assets/8905380/b34924df-7b94-4e20-bf54-7592e432ab74">
</p>

> A rich, visual interface for easily starting and monitoring your [Hydra](https://hydra.cc) applications on [SLURM](https://slurm.schedmd.com/documentation.html) clusters.

- **Ease of Use**: Streamline your workflow with a simplified process for submitting jobs to SLURM
- **Rich Visualization**: A clear and beautiful visual overview of your jobs
- **Integration**: Seamlessly integrates with Hydra-powered CLIs
- **Real-Time Updates**: Monitor the status of your jobs in real-time

## Installation

The Hydra Slurm Rich Launcher can be installed via pip:
```
pip install hydra-slurm-rich-launcher --upgrade
```
<details>
  <summary>Alternative installation methods</summary>
  
  ### Locally
    ```
    git clone git@github.com:creinders/hydra-slurm-rich-launcher.git
    cd hydra-slurm-rich-launcher
    poetry install
    ```
</details>

## Quick Start

Define your configuration in `config.yaml`:

```yaml
defaults:
  - override hydra/launcher: slurm_rich
hydra:
  launcher:
    partition: <SLURM_PARTITION>

task: 1
```

Implement your Hydra app in `my_app.py`:
```python
import hydra

@hydra.main(config_path=".", config_name="config", version_base="1.3")
def my_app(cfg) -> None:
    print(f"Task: {cfg.task}")

if __name__ == "__main__":
    my_app()
```

Starting the app with `task=1,2,4` will launch three jobs with different configurations:
```bash
python my_app.py task=1,2,4 --multirun
```
![example](https://github.com/creinders/hydra-slurm-rich-launcher/assets/8905380/9ed7e585-573b-4982-8c6b-97365d2c410e)

Please see the [Hydra documentation](https://hydra.cc/docs/intro/) for details regarding the configuration and multi-run.

## Scalability

Lots of run? No problem! Hydra Slurm Rich Launcher smartly organizes all of your runs.

![Scalability](https://github.com/creinders/hydra-slurm-rich-launcher/assets/8905380/47fc4916-a3aa-41da-8ef1-97422c90e999)

## Restarts

Easily monitor the status of your jobs and swiftly restart any failed runs.

![Restarts](https://github.com/creinders/hydra-slurm-rich-launcher/assets/8905380/105764f5-55ef-486c-aa8e-3f5dba52d110)

## Parameters

The Hydra Slurm Rich Launcher has the following parameters.
```yaml
slurm_query_interval_s: 15 #  Query update interval from SLURM controller
filter_job_ids: null # Filter specific jobs from the job array, separated by comma (e.g., "1,4"), that should not be executed
retry_strategy: 'prompt'  # Defines job retry strategy. 'prompt': will ask the user, 'never': never restarts, and 'always': restarts the runs automatically
max_retries: 3 # Maximum retry attempts
le_mode: 'auto'  # Low energy mode settings. The low energy mode disables all animations and can be turned on if the cpu-usage must be minimized. Values are: 'on', 'off', and 'auto'. 'auto' will turn on the low energy mode if the environment variable HYDRA_SLURM_PROGRESS_LE_MODE is set.

submitit_folder: ${hydra.sweep.dir}/.submitit/%j
timeout_min: 60
cpus_per_task: null
gpus_per_node: null
tasks_per_node: 1
mem_gb: null
nodes: 1
name: ${hydra.job.name}
partition: null
qos: null
comment: null
constraint: null
exclude: null
gres: null
cpus_per_gpu: null
gpus_per_task: null
mem_per_gpu: null
mem_per_cpu: null
account: null
signal_delay_s: 120
max_num_timeout: 0
additional_parameters: {}
array_parallelism: 256
setup: null
```

## License

Hydra Slurm Rich Launcher is licensed under [MIT License](./LICENSE).

## Credits

This package was inspired by and extends the capabilities of the `hydra-submitit-launcher`. We gratefully acknowledge the developers of [hydra-submitit-launcher](https://hydra.cc/docs/plugins/submitit_launcher/) and [Hydra](https://hydra.cc) for their contributions to the open-source community.

