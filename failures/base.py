from abc import ABC, abstractmethod


class FailureInjector(ABC):
    name = "unknown"

    @abstractmethod
    def inject(self, x, config):
        pass