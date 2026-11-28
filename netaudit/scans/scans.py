"""Scan data structures and serialization."""

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

from netaudit.enc_handler import EncHandler


@dataclass(kw_only=True)
class Scan:
    """A Base class for all scans"""
    # Subclasses must store host IPs, never Host objects: asdict would write out their passwords
    performed_at: datetime = field(default_factory=datetime.now)
    path: Path | None = None  # where the scan was written, if it was written to disk

    def write(self, folder: Path, enc_handler: EncHandler) -> Path:
        """Write the scan, encrypted with enc_handler, to a new file in folder and return the file's path."""
        scan_type = type(self).__name__
        data = asdict(self)
        del data["path"]  # where the file is doesn't belong inside the file
        data["type"] = scan_type
        data["performed_at"] = self.performed_at.isoformat()
        text = json.dumps(data, indent=4)
        token = enc_handler.encrypt(text.encode("utf-8"))

        folder.mkdir(exist_ok=True)
        path = folder / f"{self.performed_at:%Y-%m-%d_%H-%M-%S-%f}_{scan_type}.scan.json"
        with path.open("xb") as file:  # x: never overwrite, b: bytes, as a token is bytes
            file.write(token)
        self.path = path
        return path


# All scan types that can be loaded. Every new scan class needs a line here.
SCAN_TYPES: dict[str, type[Scan]] = {
    "Scan": Scan,
}
