"""Bounded file-backed long-term memory with frozen snapshots."""

from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from runtime.memory.policy import validate_memory_entry

try:
    import fcntl
except ImportError:  # pragma: no cover - non-Unix fallback
    fcntl = None

try:
    import msvcrt
except ImportError:  # pragma: no cover - non-Windows fallback
    msvcrt = None


MemoryTarget = Literal["memory", "user"]
ENTRY_DELIMITER = "\n§\n"
DEFAULT_MEMORY_CHAR_LIMIT = 3000
DEFAULT_USER_MEMORY_CHAR_LIMIT = 1500


@dataclass(frozen=True)
class MemoryUsage:
    chars: int
    limit: int
    entry_count: int

    def to_dict(self) -> dict[str, int]:
        return {
            "chars": self.chars,
            "limit": self.limit,
            "entry_count": self.entry_count,
        }


@dataclass(frozen=True)
class MemoryState:
    target: MemoryTarget
    path: str
    entries: tuple[str, ...]
    usage: MemoryUsage
    source: str

    @property
    def rendered_entries(self) -> str:
        return ENTRY_DELIMITER.join(self.entries)

    def to_dict(self) -> dict[str, object]:
        return {
            "target": self.target,
            "path": self.path,
            "entries": list(self.entries),
            "usage": self.usage.to_dict(),
            "source": self.source,
        }


@dataclass(frozen=True)
class FrozenLongTermMemorySnapshot:
    memory: MemoryState
    user: MemoryState

    def to_dict(self) -> dict[str, object]:
        return {
            "memory": self.memory.to_dict(),
            "user": self.user.to_dict(),
        }


@dataclass(frozen=True)
class MemoryMutationResult:
    success: bool
    action: str
    target: MemoryTarget
    state: MemoryState
    reason: str | None = None
    message: str | None = None
    matches: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "success": self.success,
            "action": self.action,
            "target": self.target,
            "state": self.state.to_dict(),
        }
        if self.reason is not None:
            payload["reason"] = self.reason
        if self.message is not None:
            payload["message"] = self.message
        if self.matches:
            payload["matches"] = list(self.matches)
        return payload


def parse_entry_list(text: str) -> tuple[str, ...]:
    raw = str(text or "")
    if not raw.strip():
        return ()
    return tuple(entry.strip() for entry in raw.split(ENTRY_DELIMITER) if entry.strip())


def serialize_entry_list(entries: tuple[str, ...] | list[str]) -> str:
    cleaned = [str(entry).strip() for entry in entries if str(entry).strip()]
    return ENTRY_DELIMITER.join(cleaned)


class LongTermMemoryStore:
    """Manage bounded project/user long-term memory files."""

    def __init__(
        self,
        *,
        project_root: str | Path,
        memory_char_limit: int = DEFAULT_MEMORY_CHAR_LIMIT,
        user_memory_char_limit: int = DEFAULT_USER_MEMORY_CHAR_LIMIT,
        user_memory_path: str | Path | None = None,
    ) -> None:
        self.project_root = Path(project_root).resolve()
        self.memory_path = self.project_root / "memory" / "long_term" / "MEMORY.md"
        if user_memory_path is None:
            self.user_path = self.project_root / "memory" / "long_term" / "USER.md"
        else:
            self.user_path = Path(user_memory_path).expanduser().resolve()
        self.memory_char_limit = max(1, int(memory_char_limit))
        self.user_memory_char_limit = max(1, int(user_memory_char_limit))
        self._live_entries: dict[MemoryTarget, tuple[str, ...]] = {"memory": (), "user": ()}
        self._frozen_snapshot = FrozenLongTermMemorySnapshot(
            memory=self._build_state("memory", (), source="frozen_snapshot"),
            user=self._build_state("user", (), source="frozen_snapshot"),
        )

    def load(self) -> FrozenLongTermMemorySnapshot:
        memory_entries = self._read_entries(self.memory_path)
        user_entries = self._read_entries(self.user_path)
        self._live_entries["memory"] = memory_entries
        self._live_entries["user"] = user_entries
        self._frozen_snapshot = FrozenLongTermMemorySnapshot(
            memory=self._build_state("memory", memory_entries, source="frozen_snapshot"),
            user=self._build_state("user", user_entries, source="frozen_snapshot"),
        )
        return self._frozen_snapshot

    def get_frozen_snapshot(self) -> FrozenLongTermMemorySnapshot:
        return self._frozen_snapshot

    def list(self, target: MemoryTarget) -> MemoryState:
        entries = self._read_entries(self._path_for(target))
        self._live_entries[target] = entries
        return self._build_state(target, entries, source="live_disk")

    def usage(self, target: MemoryTarget) -> MemoryUsage:
        return self.list(target).usage

    def add(self, target: MemoryTarget, content: str) -> MemoryMutationResult:
        reason, message = validate_memory_entry(
            content,
            max_entry_chars=self._max_entry_chars(target),
        )
        if reason is not None:
            return self._reject("add", target, reason, message)

        path = self._path_for(target)
        with self._file_lock(path):
            entries = list(self._read_entries(path))
            if str(content).strip() in entries:
                return self._reject(
                    "add",
                    target,
                    "duplicate_entry",
                    "Duplicate long-term memory entry rejected.",
                    entries=tuple(entries),
                )
            updated = tuple(entries + [str(content).strip()])
            if self._entry_chars(updated) > self._limit_for(target):
                return self._reject(
                    "add",
                    target,
                    "limit_exceeded",
                    "Long-term memory budget exceeded.",
                    entries=tuple(entries),
                )
            return self._persist("add", target, updated)

    def replace(self, target: MemoryTarget, *, old_text: str, content: str) -> MemoryMutationResult:
        if not str(old_text or "").strip():
            return self._reject("replace", target, "empty_old_text", "old_text cannot be empty.")
        reason, message = validate_memory_entry(
            content,
            max_entry_chars=self._max_entry_chars(target),
        )
        if reason is not None:
            return self._reject("replace", target, reason, message)

        path = self._path_for(target)
        with self._file_lock(path):
            entries = list(self._read_entries(path))
            matches = self._find_matches(entries, str(old_text).strip())
            if not matches:
                return self._reject(
                    "replace",
                    target,
                    "no_match",
                    f"No long-term memory entry matched '{old_text}'.",
                    entries=tuple(entries),
                )
            if len(matches) > 1:
                return self._reject(
                    "replace",
                    target,
                    "ambiguous_match",
                    f"Multiple entries matched '{old_text}'. Be more specific.",
                    entries=tuple(entries),
                    matches=tuple(match[1] for match in matches),
                )
            idx = matches[0][0]
            updated_list = list(entries)
            updated_list[idx] = str(content).strip()
            updated = tuple(updated_list)
            if self._entry_chars(updated) > self._limit_for(target):
                return self._reject(
                    "replace",
                    target,
                    "limit_exceeded",
                    "Long-term memory budget exceeded.",
                    entries=tuple(entries),
                )
            return self._persist("replace", target, updated)

    def remove(self, target: MemoryTarget, *, old_text: str) -> MemoryMutationResult:
        if not str(old_text or "").strip():
            return self._reject("remove", target, "empty_old_text", "old_text cannot be empty.")

        path = self._path_for(target)
        with self._file_lock(path):
            entries = list(self._read_entries(path))
            matches = self._find_matches(entries, str(old_text).strip())
            if not matches:
                return self._reject(
                    "remove",
                    target,
                    "no_match",
                    f"No long-term memory entry matched '{old_text}'.",
                    entries=tuple(entries),
                )
            if len(matches) > 1:
                return self._reject(
                    "remove",
                    target,
                    "ambiguous_match",
                    f"Multiple entries matched '{old_text}'. Be more specific.",
                    entries=tuple(entries),
                    matches=tuple(match[1] for match in matches),
                )
            updated = tuple(entry for idx, entry in enumerate(entries) if idx != matches[0][0])
            return self._persist("remove", target, updated)

    def _persist(
        self,
        action: str,
        target: MemoryTarget,
        entries: tuple[str, ...],
    ) -> MemoryMutationResult:
        path = self._path_for(target)
        try:
            self._atomic_write(path, entries)
        except OSError as exc:
            live_state = self.list(target)
            return MemoryMutationResult(
                success=False,
                action=action,
                target=target,
                state=live_state,
                reason="write_failed",
                message=str(exc),
            )
        self._live_entries[target] = entries
        return MemoryMutationResult(
            success=True,
            action=action,
            target=target,
            state=self._build_state(target, entries, source="live_disk"),
        )

    def _reject(
        self,
        action: str,
        target: MemoryTarget,
        reason: str,
        message: str | None,
        *,
        entries: tuple[str, ...] | None = None,
        matches: tuple[str, ...] = (),
    ) -> MemoryMutationResult:
        state = self._build_state(
            target,
            self._live_entries[target] if entries is None else entries,
            source="live_disk",
        )
        return MemoryMutationResult(
            success=False,
            action=action,
            target=target,
            state=state,
            reason=reason,
            message=message,
            matches=matches,
        )

    def _build_state(self, target: MemoryTarget, entries: tuple[str, ...], *, source: str) -> MemoryState:
        return MemoryState(
            target=target,
            path=str(self._path_for(target)),
            entries=tuple(entries),
            usage=MemoryUsage(
                chars=self._entry_chars(entries),
                limit=self._limit_for(target),
                entry_count=len(entries),
            ),
            source=source,
        )

    def _path_for(self, target: MemoryTarget) -> Path:
        if target == "user":
            return self.user_path
        return self.memory_path

    def _limit_for(self, target: MemoryTarget) -> int:
        return self.user_memory_char_limit if target == "user" else self.memory_char_limit

    def _max_entry_chars(self, target: MemoryTarget) -> int:
        return min(max(400, self._limit_for(target) * 4), 1200)

    @staticmethod
    def _entry_chars(entries: tuple[str, ...] | list[str]) -> int:
        return len(serialize_entry_list(entries))

    @staticmethod
    def _find_matches(entries: list[str], needle: str) -> list[tuple[int, str]]:
        return [(index, entry) for index, entry in enumerate(entries) if needle in entry]

    @staticmethod
    def _read_entries(path: Path) -> tuple[str, ...]:
        if not path.exists():
            return ()
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError:
            return ()
        return parse_entry_list(raw)

    @staticmethod
    def _atomic_write(path: Path, entries: tuple[str, ...]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = serialize_entry_list(entries)
        fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=".memory-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, path)
        except BaseException:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass
            raise

    @staticmethod
    @contextmanager
    def _file_lock(path: Path):
        lock_path = path.with_suffix(path.suffix + ".lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        if fcntl is None and msvcrt is None:  # pragma: no cover - platform fallback
            yield
            return
        with open(lock_path, "a+", encoding="utf-8") as handle:
            try:
                if fcntl is not None:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
                elif msvcrt is not None:  # pragma: no cover - Windows fallback
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
                yield
            finally:
                if fcntl is not None:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
                elif msvcrt is not None:  # pragma: no cover - Windows fallback
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


__all__ = [
    "DEFAULT_MEMORY_CHAR_LIMIT",
    "DEFAULT_USER_MEMORY_CHAR_LIMIT",
    "ENTRY_DELIMITER",
    "FrozenLongTermMemorySnapshot",
    "LongTermMemoryStore",
    "MemoryMutationResult",
    "MemoryState",
    "MemoryUsage",
    "parse_entry_list",
    "serialize_entry_list",
]
