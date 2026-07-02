"""Proposal 管理 — 单个 Skill 的完整生命周期管理。

每个 Skill 独立一个 ProposalManager 实例。
每个 Proposal 保存为独立 JSON 文件。
"""

from __future__ import annotations

import json
from pathlib import Path

from extensions.skill_evolution.types import PatchOp, Proposal, ProposalStatus, ProposalType


class ProposalManager:
    def __init__(self, proposals_dir: Path):
        self._proposals_dir = Path(proposals_dir)
        self._proposals_dir.mkdir(parents=True, exist_ok=True)

    def _path(self, proposal_id: str) -> Path:
        return self._proposals_dir / f"{proposal_id}.json"

    def _rejected_path(self) -> Path:
        return self._proposals_dir.parent / "rejected.jsonl"

    def _next_id(self, prefix: str) -> str:
        max_n = 0
        for f in self._proposals_dir.glob(f"{prefix}-*.json"):
            try:
                n = int(f.stem.split("-")[1])
                max_n = max(max_n, n)
            except (IndexError, ValueError):
                continue
        return f"{prefix}-{max_n + 1:05d}"

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def propose(self, proposal: Proposal):
        if not proposal.proposal_id:
            prefix = "HF" if proposal.proposal_type == ProposalType.USER_DIRECTED_HOTFIX else "P"
            proposal.proposal_id = self._next_id(prefix)
        proposal.status = ProposalStatus.PROPOSED
        self._save(proposal)

    def stage(self, proposal_id: str):
        p = self.load(proposal_id)
        if p:
            p.status = ProposalStatus.STAGED
            self._save(p)

    def evaluate(self, proposal_id: str):
        p = self.load(proposal_id)
        if p:
            p.status = ProposalStatus.EVALUATING
            self._save(p)

    def accept(self, proposal_id: str):
        p = self.load(proposal_id)
        if p:
            p.status = ProposalStatus.ACCEPTED
            self._save(p)

    def reject(self, proposal_id: str, reason: str, failure_trace_ids: list[str]):
        p = self.load(proposal_id)
        if p:
            p.status = ProposalStatus.REJECTED
            p.rejection_reason = reason
            p.failure_trace_ids = failure_trace_ids
            self._save(p)
            self._append_rejected(p)

    def supersede(self, proposal_id: str):
        p = self.load(proposal_id)
        if p:
            p.status = ProposalStatus.SUPERSEDED
            self._save(p)

    def get_active(self) -> Proposal | None:
        for f in sorted(self._proposals_dir.glob("*.json")):
            p = self.load(f.stem)
            if p and p.status == ProposalStatus.EVALUATING:
                return p
        return None

    def load(self, proposal_id: str) -> Proposal | None:
        path = self._path(proposal_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text())
            data["patch"] = PatchOp(**data["patch"])
            data["proposal_type"] = ProposalType(data["proposal_type"])
            data["status"] = ProposalStatus(data["status"])
            return Proposal(**data)
        except Exception:
            return None

    def get_recent_rejected(self, n: int) -> list[Proposal]:
        result: list[Proposal] = []
        rp = self._rejected_path()
        if not rp.exists():
            return result
        for line in reversed(rp.read_text(encoding="utf-8").splitlines()):
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
                obj["patch"] = PatchOp(**obj["patch"])
                obj["proposal_type"] = ProposalType(obj["proposal_type"])
                obj["status"] = ProposalStatus(obj["status"])
                result.append(Proposal(**obj))
            except Exception:
                continue
        return result[:n]

    def is_duplicate(self, proposal: Proposal) -> bool:
        fingerprint = (proposal.error_signature, proposal.target_section, proposal.patch.patch_type)
        for rejected in self.get_recent_rejected(n=10):
            rf = (rejected.error_signature, rejected.target_section, rejected.patch.patch_type)
            if fingerprint == rf:
                return True
        return False

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _save(self, proposal: Proposal):
        data = {
            "proposal_id": proposal.proposal_id,
            "proposal_type": proposal.proposal_type.value,
            "target_skill": proposal.target_skill,
            "base_version": proposal.base_version,
            "source_trace_ids": proposal.source_trace_ids,
            "problem": proposal.problem,
            "reason": proposal.reason,
            "target_section": proposal.target_section,
            "patch": {
                "patch_type": proposal.patch.patch_type,
                "target_section": proposal.patch.target_section,
                "old_text": proposal.patch.old_text,
                "new_text": proposal.patch.new_text,
            },
            "expected_behavior": proposal.expected_behavior,
            "error_signature": proposal.error_signature,
            "risk_level": proposal.risk_level,
            "status": proposal.status.value,
            "user_instruction": proposal.user_instruction,
            "rejection_reason": proposal.rejection_reason,
            "failure_trace_ids": proposal.failure_trace_ids,
        }
        tmp_path = self._path(proposal.proposal_id).with_suffix(".tmp")
        tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2))
        tmp_path.replace(self._path(proposal.proposal_id))

    def _append_rejected(self, proposal: Proposal):
        data = {
            "proposal_id": proposal.proposal_id,
            "proposal_type": proposal.proposal_type.value,
            "target_skill": proposal.target_skill,
            "base_version": proposal.base_version,
            "source_trace_ids": proposal.source_trace_ids,
            "problem": proposal.problem,
            "reason": proposal.reason,
            "target_section": proposal.target_section,
            "patch": {
                "patch_type": proposal.patch.patch_type,
                "target_section": proposal.patch.target_section,
                "old_text": proposal.patch.old_text,
                "new_text": proposal.patch.new_text,
            },
            "expected_behavior": proposal.expected_behavior,
            "error_signature": proposal.error_signature,
            "risk_level": proposal.risk_level,
            "status": proposal.status.value,
            "user_instruction": proposal.user_instruction,
            "rejection_reason": proposal.rejection_reason,
            "failure_trace_ids": proposal.failure_trace_ids,
        }
        with self._rejected_path().open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(data, ensure_ascii=False) + "\n")


__all__ = ["ProposalManager"]
