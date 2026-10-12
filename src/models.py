from enum import Enum
from pydantic import BaseModel, Field
from typing import Optional

class CandidateStatus(str, Enum):
    DISCOVERED = "discovered"
    REJECTED = "rejected"
    RATE_LIMITED = "rate_limited"
    PARTIAL = "partial"
    READY_FOR_REVIEW = "ready_for_review"
    ACCEPTED = "accepted"
    TRASHED = "trashed"
    SPARSE_DATA = "sparse_data"


class Candidate(BaseModel):
    id: str
    source: str
    search_mode: str  # basic | advanced | complement
    status: CandidateStatus = CandidateStatus.DISCOVERED
    coverage_score: float = 0.0
    completeness_score: float = 0.0
    missing_fields: list[str] = Field(default_factory=list)
    # For complement searches, this is the subset of fields the source is
    # expected to supply. It is intentionally distinct from missing_fields.
    target_fields: list[str] = Field(default_factory=list)
    source_priority: int = 0
    retry_count: int = 0
    estimated_total_records: Optional[int] = None
    estimated_wait_seconds: Optional[int] = None
    sample_records: list[dict] = Field(default_factory=list)
    fetched_records: list[dict] = Field(default_factory=list)


class UserDecision(str, Enum):
    ACCEPT = "accept"
    TRASH = "trash"
    DATA_MISSING = "data_missing"
    RATE_LIMIT = "rate_limit"
    SPARSE_DATA = "sparse_data"


class ConstraintDecision(str, Enum):
    PROCEED = "proceed"
    TRASH = "trash"


class FieldValue(BaseModel):
    value: object
    source_candidate_id: str
    confidence: float
    precision: str = "exact"  # exact | day | month | range | derived


class Record(BaseModel):
    entity_key: str
    fields: dict[str, FieldValue] = Field(default_factory=dict)


class WorkflowState(BaseModel):
    user_decision: Optional[UserDecision] = None
    constraint_decision: Optional[ConstraintDecision] = None
    request_id: str
    desired_fields: list[str]
    candidates: list[Candidate] = Field(default_factory=list)
    reviewed_candidate_ids: list[str] = Field(default_factory=list)
    accepted_candidate_ids: list[str] = Field(default_factory=list)
    accepted_candidates: list[Candidate] = Field(default_factory=list)
    merged_data: list[Record] = Field(default_factory=list)
    merge_conflicts: list[dict] = Field(default_factory=list)
    failure_report: Optional[dict] = None
    export_path: Optional[str] = None

