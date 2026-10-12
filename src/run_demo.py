import argparse

from langgraph.types import Command
from src.graph import graph


parser = argparse.ArgumentParser()
parser.add_argument(
    "--scenario",
    choices=["accept", "data_missing", "rate_limit", "sparse_data"],
    default="accept",
)
args = parser.parse_args()

first_responses = {
    "accept": {"decision": "accept", "candidate_ids": ["public-demo-api"]},
    "data_missing": {"decision": "data_missing", "candidate_ids": ["partner-api"]},
    "rate_limit": {"decision": "rate_limit", "candidate_ids": ["rate-limited-api"]},
    "sparse_data": {"decision": "sparse_data", "candidate_ids": ["sparse-catalog-api"]},
}

config = {
    "configurable": {
        "thread_id": "demo-{}".format(args.scenario),
    }
}

paused = graph.invoke(
    {
        "request_id": "demo-001",
        "desired_fields": ["name", "address", "phone", "website"],
    },
    config=config,
)

print("首次审核：", paused["__interrupt__"])

result = graph.invoke(
    Command(
        resume=first_responses[args.scenario]
    ),
    config=config,
)

if args.scenario == "data_missing":
    result = graph.invoke(
        Command(
            resume={
                "decision": "accept",
                "candidate_ids": ["partner-api", "complement-phone-website"],
            }
        ),
        config=config,
    )
elif args.scenario in {"rate_limit", "sparse_data"}:
    result = graph.invoke(
        Command(resume={"decision": "proceed"}),
        config=config,
    )

print("最终结果：", result)
