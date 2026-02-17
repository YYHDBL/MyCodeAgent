"""Task board service wrapper."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class TaskBoardService:
    """Encapsulates task-board CRUD and claim operations."""

    def __init__(self, task_board_store: Any):
        self._store = task_board_store

    def create_task(
        self,
        team_name: str,
        *,
        subject: str,
        description: str = "",
        owner: str = "",
        blocked_by: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        return self._store.create_task(
            team_name,
            subject=subject,
            description=description,
            owner=owner,
            blocked_by=blocked_by or [],
        )

    def get_task(self, team_name: str, task_id: str) -> Dict[str, Any]:
        return self._store.get_task(team_name, str(task_id))

    def list_tasks(self, team_name: str, status: Optional[str] = None) -> List[Dict[str, Any]]:
        return self._store.list_tasks(team_name, status=status)

    def update_task(
        self,
        team_name: str,
        *,
        task_id: str,
        status: Optional[str] = None,
        owner: Optional[str] = None,
        subject: Optional[str] = None,
        description: Optional[str] = None,
        add_blocked_by: Optional[List[str]] = None,
        add_blocks: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        return self._store.update_task(
            team_name,
            task_id=str(task_id),
            status=status,
            owner=owner,
            subject=subject,
            description=description,
            add_blocked_by=add_blocked_by or [],
            add_blocks=add_blocks or [],
        )

    def claim_next_task(self, team_name: str, owner: str) -> Optional[Dict[str, Any]]:
        return self._store.claim_next_task(team_name, owner=owner)

