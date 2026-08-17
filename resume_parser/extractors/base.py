from abc import ABC, abstractmethod
from pathlib import Path


class BaseExtractor(ABC):
    def __init__(self, path: Path):
        self.path = path

    @abstractmethod
    def extract(self) -> str:
        pass
