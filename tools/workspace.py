"""Small, project-confined primitives shared by file tools."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import stat
import tempfile


class WorkspaceError(Exception):
    """A filesystem failure whose kind is safe for a tool to map to its protocol."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind


@dataclass(frozen=True)
class FileSnapshot:
    """The durable properties used to detect a changed file before replacement."""

    path: Path
    mtime_ns: int
    size: int

    @property
    def mtime_ms(self) -> int:
        return self.mtime_ns // 1_000_000


class FileWorkspace:
    """Resolve and update regular text files beneath one project root."""

    binary_check_size = 8192

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()

    def resolve(self, requested: str) -> Path:
        """Return a normalized relative path only when it remains under ``root``."""
        if not isinstance(requested, str) or not requested:
            raise WorkspaceError("invalid_path", "Path must be a non-empty relative string.")
        candidate = Path(requested)
        if candidate.is_absolute():
            raise WorkspaceError("absolute", "Absolute paths are not allowed.")
        try:
            target = (self.root / candidate).resolve(strict=False)
            target.relative_to(self.root)
        except ValueError as error:
            raise WorkspaceError("outside", "Path is outside project root.") from error
        except (OSError, RuntimeError) as error:
            raise WorkspaceError("io", f"Path resolution failed: {error}") from error
        return target

    def relative(self, target: Path) -> str:
        relative = target.relative_to(self.root)
        return str(relative) or "."

    def inspect(self, requested: str) -> FileSnapshot:
        """Validate a readable regular text file and capture its current snapshot."""
        target = self.resolve(requested)
        try:
            file_stat = target.stat()
            if stat.S_ISDIR(file_stat.st_mode):
                raise WorkspaceError("directory", f"Path '{requested}' is a directory.")
            if not stat.S_ISREG(file_stat.st_mode):
                raise WorkspaceError("not_regular", f"Path '{requested}' is not a regular file.")
            if self._is_binary(target):
                raise WorkspaceError("binary", f"File '{requested}' appears to be binary.")
        except FileNotFoundError as error:
            raise WorkspaceError("not_found", f"File '{requested}' does not exist.") from error
        except WorkspaceError:
            raise
        except OSError as error:
            raise WorkspaceError("io", f"Cannot access file: {error}") from error
        return FileSnapshot(target, file_stat.st_mtime_ns, file_stat.st_size)

    def read_text(self, requested: str) -> tuple[str, str, bool, FileSnapshot]:
        """Read text consistently, rejecting a file changed while it was read."""
        before = self.inspect(requested)
        try:
            raw = before.path.read_bytes()
        except OSError as error:
            raise WorkspaceError("io", f"Failed to read file: {error}") from error
        after = self.inspect(requested)
        if before != after:
            raise WorkspaceError("conflict", "File was modified while being read.")
        try:
            return raw.decode("utf-8"), "utf-8", False, after
        except UnicodeDecodeError:
            return raw.decode("utf-8", errors="replace"), "utf-8 (replace)", True, after

    def atomic_write(self, requested: str, text: str, *, expected: FileSnapshot) -> int:
        """Atomically replace a file only if its exact read snapshot still matches."""
        current = self.inspect(requested)
        if current != expected:
            raise WorkspaceError("conflict", "File has been modified since it was read.")

        encoded = text.encode("utf-8")
        fd = -1
        temporary = None
        try:
            fd, temporary = tempfile.mkstemp(
                prefix=".mycodeagent-", suffix=".tmp", dir=current.path.parent
            )
            with os.fdopen(fd, "wb") as handle:
                fd = -1
                os.fchmod(handle.fileno(), stat.S_IMODE(current.path.stat().st_mode))
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, current.path)
            temporary = None
            return len(encoded)
        finally:
            if fd != -1:
                os.close(fd)
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass

    def atomic_create(self, requested: str, text: str) -> int:
        """Create one new text file without ever replacing a concurrent writer."""
        target = self.resolve(requested)
        encoded = text.encode("utf-8")
        fd = -1
        temporary = None
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            # Re-resolve after directory creation so a raced symlink cannot escape root.
            target = self.resolve(requested)
            fd, temporary = tempfile.mkstemp(
                prefix=".mycodeagent-", suffix=".tmp", dir=target.parent
            )
            with os.fdopen(fd, "wb") as handle:
                fd = -1
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary, target)
            except FileExistsError as error:
                raise WorkspaceError("conflict", "File was created concurrently.") from error
            os.unlink(temporary)
            temporary = None
            return len(encoded)
        finally:
            if fd != -1:
                os.close(fd)
            if temporary is not None:
                try:
                    os.unlink(temporary)
                except FileNotFoundError:
                    pass

    def _is_binary(self, target: Path) -> bool:
        with target.open("rb") as handle:
            return b"\x00" in handle.read(self.binary_check_size)
