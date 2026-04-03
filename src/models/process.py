"""Data model for a single system process."""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ProcessInfo:
    """Represents a snapshot of a single system process."""

    pid: int
    name: str
    cpu_percent: float
    memory_percent: float
    status: str
    ppid: Optional[int] = None
    # Insights / annotations added by detectors
    insights: List[str] = field(default_factory=list)

    def add_insight(self, message: str) -> None:
        """Append an insight annotation to this process."""
        if message not in self.insights:
            self.insights.append(message)

    @property
    def insight_text(self) -> str:
        """Return a comma-separated string of all insights."""
        return ", ".join(self.insights) if self.insights else "—"

    def is_zombie(self) -> bool:
        return self.status.lower() == "zombie"

    def is_high_cpu(self, threshold: float = 50.0) -> bool:
        return self.cpu_percent > threshold
