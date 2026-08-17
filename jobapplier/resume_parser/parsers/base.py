from abc import ABC, abstractmethod

from jobapplier.resume_parser.models import ResumeJSON


class BaseResumeParser(ABC):
    @abstractmethod
    def parse(self, text: str) -> ResumeJSON:
        pass
