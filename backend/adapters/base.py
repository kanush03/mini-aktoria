from abc import ABC, abstractmethod

class RobotAdapter(ABC):
    @abstractmethod
    def get_state(self) -> dict: ...

    @abstractmethod
    def send_command(self, cmd: dict) -> None: ...

    @abstractmethod
    def step(self, dt: float) -> None: ...