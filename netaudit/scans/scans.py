"""Base class for all scans."""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass(kw_only=True)
class Scan:
    """What all scans have in common. Each kind of scan is a subclass."""

    # Subclasses must store host IPs, never Host objects: asdict would write out their passwords
    performed_at: datetime = field(default_factory=datetime.now)
    path: Path | None = None  # where the scan was written, if it was written to disk

    def write(self, folder: Path) -> Path:
        """Write the scan to a new file in folder and return the file's path."""
        scan_type = type(self).__name__
        data = asdict(self)
        del data["path"]  # where the file is doesn't belong inside the file
        data["type"] = scan_type
        data["performed_at"] = self.performed_at.isoformat()
        # TODO: encrypt before writing (part B), this is plain text for now
        text = json.dumps(data, indent=4)

        folder.mkdir(exist_ok=True)
        path = folder / f"{self.performed_at:%Y-%m-%d_%H-%M-%S-%f}_{scan_type}.scan.json"
        with path.open("x", encoding="utf-8") as file:
            file.write(text)
        self.path = path
        return path
