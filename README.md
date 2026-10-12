Request         用户目标、目标字段、过滤条件、数量、时效与质量要求
Candidate       数据源候选、样本、评分、访问/合规状态、缺失字段、重试次数
Record          原始数据、规范化数据、字段级来源、置信度、精度与合并方式
SecurityContext 数据分级、允许的数据源/工具、密钥引用、保留与导出策略

DISCOVERED, PROBED, REJECTED, RATE_LIMITED, PARTIAL,
READY_FOR_REVIEW, ACCEPTED, TRASHED, FETCH_FAILED,
FETCHED, MERGED, VALIDATED, EXPORTED

intake → discover → probe_and_score → candidate_pool
      → user_review → fetch → merge_validate → export

User decision:
ACCEPT       → fetch_accepted
DATA_MISSING → complement_search
RATE_LIMIT   → wait_for_rate_limit_approval
SPARSE_DATA  → wait_for_sparse_data_approval
TRASH        → discover_candidates / failed_with_report