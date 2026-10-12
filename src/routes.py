from .models import ConstraintDecision, WorkflowState, UserDecision

def route_after_review(state: WorkflowState) -> str:
    if state.user_decision == UserDecision.ACCEPT:
        return "fetch_accepted"

    if state.user_decision == UserDecision.DATA_MISSING:
        return "complement_search"

    if state.user_decision == UserDecision.RATE_LIMIT:
        return "rate_limit_review"

    if state.user_decision == UserDecision.SPARSE_DATA:
        return "sparse_data_review"

    if state.user_decision == UserDecision.TRASH:
        return "failed_with_report"

    raise ValueError(
        f"Decision not implemented yet: {state.user_decision}"
    )


def route_after_constraint_review(state: WorkflowState) -> str:
    if state.constraint_decision == ConstraintDecision.PROCEED:
        return "fetch_accepted"
    if state.constraint_decision == ConstraintDecision.TRASH:
        return "user_review"
    raise ValueError("Constraint decision not implemented: {}".format(state.constraint_decision))
