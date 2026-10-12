from .models import (
    Candidate,
    CandidateStatus,
    ConstraintDecision,
    FieldValue,
    Record,
    UserDecision,
    WorkflowState,
)
from langgraph.types import interrupt

def discover_candidates(state: WorkflowState) -> dict:
    """根据用户需求产生候选数据源；当前先返回模拟候选。"""

    candidates = [
        Candidate(
            id="public-demo-api",
            source="Public Demo API",
            search_mode="basic",
            status=CandidateStatus.DISCOVERED,
            source_priority=100,
        ),
        Candidate(
            id="partner-api",
            source="Partner API",
            search_mode="advanced",
            status=CandidateStatus.DISCOVERED,
            source_priority=80,
        ),
        Candidate(
            id="rate-limited-api",
            source="Rate Limited API",
            search_mode="basic",
            status=CandidateStatus.DISCOVERED,
            source_priority=90,
        ),
        Candidate(
            id="sparse-catalog-api",
            source="Sparse Catalog API",
            search_mode="basic",
            status=CandidateStatus.DISCOVERED,
            source_priority=50,
        ),
    ]

    # LangGraph 节点返回“状态增量”，而不是负责决定下一跳。
    return {"candidates": candidates}


def _has_value(value) -> bool:
    return value is not None and value != ""


def _score_sample(sample_records: list[dict], target_fields: list[str]):
    """Return coverage, cell completeness, and fields absent from a sample."""
    if not sample_records or not target_fields:
        return 0.0, 0.0, list(target_fields)

    covered_fields = [
        field
        for field in target_fields
        if any(_has_value(record.get(field)) for record in sample_records)
    ]
    total_cells = len(sample_records) * len(target_fields)
    filled_cells = sum(
        _has_value(record.get(field))
        for record in sample_records
        for field in target_fields
    )

    return (
        len(covered_fields) / len(target_fields),
        filled_cells / total_cells,
        [field for field in target_fields if field not in covered_fields],
    )


def _mock_probe(candidate: Candidate):
    """Temporary source adapter. Replace this with real source probes later."""
    full_record = {
        "entity_key": "acme-001",
        "name": "ACME",
        "address": "100 Main St",
        "phone": "555-0100",
        "website": "https://acme.example",
    }

    if candidate.id == "public-demo-api":
        return [full_record], 500, None
    if candidate.id == "partner-api":
        return [{
            "entity_key": "acme-001",
            "name": "ACME",
            "address": "100 Main St",
            "phone": None,
            "website": None,
        }], 800, None
    if candidate.search_mode == "complement":
        return [{
            "entity_key": "acme-001",
            "phone": "555-0100",
            "website": "https://acme.example",
        }], 500, None
    if candidate.id == "rate-limited-api":
        return [full_record], 10_000, 1800
    if candidate.id == "sparse-catalog-api":
        return [{"entity_key": "acme-001", "name": "ACME"}], 120, None
    return None


def probe_and_score(state: WorkflowState) -> dict:
    """Probe candidates, score their samples, and assign a reviewable status."""
    updated = []
    terminal_statuses = {
        CandidateStatus.ACCEPTED,
        CandidateStatus.TRASHED,
        CandidateStatus.REJECTED,
    }

    for candidate in state.candidates:
        if candidate.status in terminal_statuses:
            updated.append(candidate)
            continue

        probe_result = _mock_probe(candidate)
        if probe_result is None:
            updated.append(candidate.model_copy(update={"status": CandidateStatus.REJECTED}))
            continue

        sample_records, estimated_total_records, estimated_wait_seconds = probe_result
        target_fields = (
            candidate.target_fields
            if candidate.search_mode == "complement"
            else state.desired_fields
        )
        coverage, completeness, missing_fields = _score_sample(
            sample_records,
            target_fields,
        )

        if estimated_wait_seconds is not None:
            status = CandidateStatus.RATE_LIMITED
        elif candidate.id == "sparse-catalog-api":
            status = CandidateStatus.SPARSE_DATA
        elif missing_fields:
            status = CandidateStatus.PARTIAL
        else:
            status = CandidateStatus.READY_FOR_REVIEW

        updated.append(
            candidate.model_copy(
                update={
                    "status": status,
                    "sample_records": sample_records,
                    "coverage_score": coverage,
                    "completeness_score": completeness,
                    "missing_fields": missing_fields,
                    "estimated_total_records": estimated_total_records,
                    "estimated_wait_seconds": estimated_wait_seconds,
                }
            )
        )

    return {"candidates": updated}



def user_review(state: WorkflowState) -> dict:
    reviewable_candidates = [
        candidate
        for candidate in state.candidates
        if candidate.status in {
            CandidateStatus.READY_FOR_REVIEW,
            CandidateStatus.PARTIAL,
            CandidateStatus.RATE_LIMITED,
            CandidateStatus.SPARSE_DATA,
        }
    ]

    # 第一次运行时，图在这里暂停。
    response = interrupt({
        "type": "candidate_review",
        "request_id": state.request_id,
        "candidates": [
            candidate.model_dump(mode="json")
            for candidate in reviewable_candidates
        ],
        "allowed_decisions": [
            "accept",
            "trash",
            "data_missing",
            "rate_limit",
            "sparse_data",
        ],
    })

    # 恢复图后，response 是用户提交的内容。
    decision = UserDecision(response["decision"])
    selected_ids = set(response.get("candidate_ids", []))
    reviewable_ids = {candidate.id for candidate in reviewable_candidates}

    if not selected_ids:
        raise ValueError("Select at least one candidate before submitting a decision.")
    if not selected_ids.issubset(reviewable_ids):
        raise ValueError("A submitted candidate is not available for review.")

    selected_candidates = [
        candidate for candidate in state.candidates if candidate.id in selected_ids
    ]

    if decision == UserDecision.ACCEPT:
        updated_candidates = [
            candidate.model_copy(update={"status": CandidateStatus.ACCEPTED})
            if candidate.id in selected_ids
            else candidate
            for candidate in state.candidates
        ]
        return {
            "user_decision": decision,
            "reviewed_candidate_ids": list(selected_ids),
            "accepted_candidate_ids": list(selected_ids),
            "candidates": updated_candidates,
        }

    if decision == UserDecision.TRASH:
        updated_candidates = [
            candidate.model_copy(update={"status": CandidateStatus.TRASHED})
            if candidate.id in selected_ids
            else candidate
            for candidate in state.candidates
        ]
        return {
            "user_decision": decision,
            "reviewed_candidate_ids": list(selected_ids),
            "accepted_candidate_ids": [],
            "candidates": updated_candidates,
        }

    if decision == UserDecision.DATA_MISSING:
        if any(candidate.status != CandidateStatus.PARTIAL for candidate in selected_candidates):
            raise ValueError("DATA_MISSING can only be applied to PARTIAL candidates.")
        return {
            "user_decision": decision,
            "reviewed_candidate_ids": list(selected_ids),
            "accepted_candidate_ids": [],
        }

    expected_status = {
        UserDecision.RATE_LIMIT: CandidateStatus.RATE_LIMITED,
        UserDecision.SPARSE_DATA: CandidateStatus.SPARSE_DATA,
    }[decision]
    if any(candidate.status != expected_status for candidate in selected_candidates):
        raise ValueError(
            "{} requires candidates with status {}.".format(
                decision.value, expected_status.value
            )
        )
    return {
        "user_decision": decision,
        "reviewed_candidate_ids": list(selected_ids),
        "accepted_candidate_ids": [],
    }


def _review_constraint(state, review_type, expected_status, estimate_key):
    candidates = [
        candidate
        for candidate in state.candidates
        if candidate.id in state.reviewed_candidate_ids
        and candidate.status == expected_status
    ]
    if not candidates:
        raise ValueError("No {} candidates are awaiting confirmation.".format(expected_status.value))

    response = interrupt({
        "type": review_type,
        "request_id": state.request_id,
        "candidates": [candidate.model_dump(mode="json") for candidate in candidates],
        "estimate_key": estimate_key,
        "allowed_decisions": ["proceed", "trash"],
    })
    decision = ConstraintDecision(response["decision"])
    selected_ids = set(response.get("candidate_ids", state.reviewed_candidate_ids))
    candidate_ids = {candidate.id for candidate in candidates}
    if not selected_ids or not selected_ids.issubset(candidate_ids):
        raise ValueError("Select one or more candidates shown in this confirmation.")

    if decision == ConstraintDecision.PROCEED:
        updated_candidates = [
            candidate.model_copy(update={"status": CandidateStatus.ACCEPTED})
            if candidate.id in selected_ids else candidate
            for candidate in state.candidates
        ]
        return {
            "constraint_decision": decision,
            "accepted_candidate_ids": list(selected_ids),
            "candidates": updated_candidates,
        }

    updated_candidates = [
        candidate.model_copy(update={"status": CandidateStatus.TRASHED})
        if candidate.id in selected_ids else candidate
        for candidate in state.candidates
    ]
    return {
        "constraint_decision": decision,
        "accepted_candidate_ids": [],
        "candidates": updated_candidates,
    }


def rate_limit_review(state: WorkflowState) -> dict:
    """Show estimated wait time and let the user approve or discard the source."""
    return _review_constraint(
        state,
        "rate_limit_review",
        CandidateStatus.RATE_LIMITED,
        "estimated_wait_seconds",
    )


def sparse_data_review(state: WorkflowState) -> dict:
    """Show estimated record count and let the user approve or discard the source."""
    return _review_constraint(
        state,
        "sparse_data_review",
        CandidateStatus.SPARSE_DATA,
        "estimated_total_records",
    )

def complement_search(state: WorkflowState) -> dict:

    """针对现有候选缺失的字段，创建补集搜索候选。"""

    partial_candidates = [
        candidate
        for candidate in state.candidates
        if candidate.status == CandidateStatus.PARTIAL
    ]

    missing_fields = sorted({
        field
        for candidate in partial_candidates
        for field in candidate.missing_fields
    })

    # 没有缺失字段时，不创建补集候选。
    if not missing_fields:
        return {}

    complement_id = f"complement-{'-'.join(missing_fields)}"

    # 已经尝试过同样的补集策略时不重复加入，防止循环。
    if any(candidate.id == complement_id for candidate in state.candidates):
        return {}
    """模拟补充搜索，返回一个新的候选数据源。"""
    new_candidate = Candidate(
        id=complement_id,
        source="Complement Search",
        search_mode="complement",
        status=CandidateStatus.DISCOVERED,
        target_fields=missing_fields,
        source_priority=70,
    )
    return {"candidates": state.candidates + [new_candidate]}

def fetch_accepted(state: WorkflowState) -> dict:
    """Simulate fetching full data by promoting each accepted sample to records."""
    accepted_ids = set(state.accepted_candidate_ids)
    updated_candidates = [
        candidate.model_copy(update={"fetched_records": candidate.sample_records})
        if candidate.id in accepted_ids
        else candidate
        for candidate in state.candidates
    ]
    accepted_candidates = [
        candidate for candidate in updated_candidates if candidate.id in accepted_ids
    ]
    return {
        "candidates": updated_candidates,
        "accepted_candidates": accepted_candidates,
    }

def failed_with_report(state: WorkflowState) -> dict:
    """模拟失败处理，返回失败报告。"""
    report = {
        "message": "No suitable data source found.",
        "candidates": [c.dict() for c in state.candidates],
    }
    return {"failure_report": report}

def merge_validate(state: WorkflowState) -> dict:
    """Merge accepted records by entity key, retaining field-level provenance."""
    accepted_ids = set(state.accepted_candidate_ids)
    candidates = [
        candidate for candidate in state.candidates if candidate.id in accepted_ids
    ]
    candidates_by_id = {candidate.id: candidate for candidate in candidates}
    merged_by_entity = {}
    conflicts = []

    for candidate in candidates:
        for raw_record in candidate.fetched_records:
            entity_key = raw_record.get("entity_key")
            if not entity_key:
                continue

            record = merged_by_entity.setdefault(
                entity_key,
                Record(entity_key=entity_key),
            )
            for field, value in raw_record.items():
                if field == "entity_key" or not _has_value(value):
                    continue

                incoming = FieldValue(
                    value=value,
                    source_candidate_id=candidate.id,
                    confidence=candidate.completeness_score,
                )
                current = record.fields.get(field)
                if current is None:
                    record.fields[field] = incoming
                    continue
                if current.value == incoming.value:
                    continue

                current_candidate = candidates_by_id[current.source_candidate_id]
                incoming_rank = (incoming.confidence, candidate.source_priority)
                current_rank = (
                    current.confidence,
                    current_candidate.source_priority,
                )
                chosen = incoming if incoming_rank > current_rank else current
                rejected = current if chosen is incoming else incoming
                record.fields[field] = chosen
                conflicts.append({
                    "entity_key": entity_key,
                    "field": field,
                    "chosen": chosen.model_dump(mode="json"),
                    "rejected": rejected.model_dump(mode="json"),
                })

    return {
        "merged_data": list(merged_by_entity.values()),
        "merge_conflicts": conflicts,
    }

def result_export(state: WorkflowState) -> dict:
    """模拟结果导出。"""
    # 假设导出成功，返回导出路径
    export_path = f"exports/{state.request_id}.json"
    return {"export_path": export_path}
