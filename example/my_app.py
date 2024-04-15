import hydra
from omegaconf import DictConfig

@hydra.main(config_path=".", config_name="config", version_base="1.3")
def my_app(cfg: DictConfig) -> None:

    print(f"Task: {cfg.task}")

if __name__ == "__main__":
    my_app()
