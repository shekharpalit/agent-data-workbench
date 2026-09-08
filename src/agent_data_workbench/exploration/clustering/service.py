"""Select trace values and assemble the explorer's lexical clustering response."""

from collections import Counter

from agent_data_workbench.data.store import TraceStore
from agent_data_workbench.exploration.clustering.components import connected_components
from agent_data_workbench.exploration.clustering.tokenization import CLUSTER_TEXT_LIMIT, words
from agent_data_workbench.exploration.clustering.vectors import tfidf_vectors
from agent_data_workbench.exploration.schemas import ClusterQuery
from agent_data_workbench.exploration.search import search
from agent_data_workbench.shared.identifiers import stable_id
from agent_data_workbench.shared.json import json_text, pointer_value


def cluster(store: TraceStore, request: ClusterQuery) -> dict:
    query = request.query.model_copy(
        update={"limit": request.limit, "offset": 0, "sort": "trace_id", "direction": "asc"}
    )
    page = search(store, query)
    documents, omitted, text_truncated = [], [], []
    for row in page["records"]:
        try:
            tokens, clipped = words(pointer_value(row["data"], request.pointer))
        except ValueError:
            tokens, clipped = [], False
        if clipped:
            text_truncated.append(row["trace_id"])
        if tokens:
            documents.append((row["trace_id"], Counter(tokens)))
        else:
            omitted.append(row["trace_id"])
    vectors = tfidf_vectors([counts for _, counts in documents])
    groups = connected_components(vectors, request.threshold)
    clusters = []
    for indexes in groups:
        terms = Counter()
        ids = [documents[i][0] for i in indexes]
        for i in indexes:
            terms.update(vectors[i])
        top = sorted(terms, key=lambda term: (-terms[term], term))[:5]
        clusters.append(
            {
                "id": stable_id("cluster", json_text(ids)),
                "trace_ids": ids,
                "count": len(ids),
                "terms": top,
                "label": " · ".join(top[:3]),
            }
        )
    clusters.sort(key=lambda c: (-c["count"], c["trace_ids"]))
    return {
        "method": "TF-IDF cosine connected components",
        "pointer": request.pointer,
        "threshold": request.threshold,
        "eligible": page["eligible"],
        "sampled": page["selected"],
        "clustered": len(documents),
        "omitted_ids": omitted,
        "text_limit_chars": CLUSTER_TEXT_LIMIT,
        "text_truncated_ids": text_truncated,
        "truncated": page["eligible"] > page["selected"],
        "source_sha256": page["source_sha256"],
        "clusters": clusters,
        "scope": "Lexical similarity on a bounded ID-ordered selection. Transitive links may "
        "join traces below the pairwise threshold. These are not semantic labels.",
    }
