from langgraph.graph import END, START, StateGraph
from .nodes import (
    complement_search,
    discover_candidates,
    failed_with_report,
    fetch_accepted,
    merge_validate,
    probe_and_score,
    rate_limit_review,
    result_export,
    sparse_data_review,
    user_review,
)
from .models import WorkflowState, CandidateStatus
from .routes import route_after_constraint_review, route_after_review
from langgraph.checkpoint.memory import InMemorySaver


def route_after_probe(state: WorkflowState) -> str:
    candidates = state.candidates

    if any(c.status == CandidateStatus.READY_FOR_REVIEW for c in candidates):
        return "user_review"

    if any(c.status == CandidateStatus.PARTIAL for c in candidates):
        return "complement_search"

    return "failed_with_report"

builder = StateGraph(WorkflowState)
checkpointer = InMemorySaver()
builder.add_edge(START, "discover_candidates")
builder.add_node("discover_candidates", discover_candidates)
builder.add_node("probe_and_score", probe_and_score)
builder.add_node("user_review", user_review)
builder.add_node("complement_search", complement_search)
builder.add_node("fetch_accepted", fetch_accepted)
builder.add_node("failed_with_report", failed_with_report)
builder.add_node("merge_validate", merge_validate)
builder.add_node("result_export", result_export)
builder.add_node("rate_limit_review", rate_limit_review)
builder.add_node("sparse_data_review", sparse_data_review)

builder.add_edge("discover_candidates", "probe_and_score")
builder.add_conditional_edges(
    "probe_and_score",
    route_after_probe,
    {
        "user_review": "user_review",
        "complement_search": "complement_search",
        "failed_with_report": "failed_with_report",
    },
)
builder.add_edge("complement_search", "probe_and_score")
builder.add_edge("failed_with_report", END)
builder.add_conditional_edges(
    "user_review",
    route_after_review,
    {
        "fetch_accepted": "fetch_accepted",
        "complement_search": "complement_search",
        "rate_limit_review": "rate_limit_review",
        "sparse_data_review": "sparse_data_review",
        "failed_with_report": "failed_with_report",
    },
)
builder.add_conditional_edges(
    "rate_limit_review",
    route_after_constraint_review,
    {
        "fetch_accepted": "fetch_accepted",
        "user_review": "user_review",
    },
)
builder.add_conditional_edges(
    "sparse_data_review",
    route_after_constraint_review,
    {
        "fetch_accepted": "fetch_accepted",
        "user_review": "user_review",
    },
)
builder.add_edge("fetch_accepted", "merge_validate")
builder.add_edge("merge_validate", "result_export")
builder.add_edge("result_export", END)
graph = builder.compile(checkpointer=checkpointer)
