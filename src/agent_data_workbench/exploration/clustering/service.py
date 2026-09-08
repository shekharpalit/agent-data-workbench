"""Select trace values and assemble the explorer's lexical clustering response."""

import hashlib
from collections import Counter

from agent_data_workbench.data.store import TraceStore
from agent_data_workbench.exploration.clustering.components import connected_components
from agent_data_workbench.exploration.clustering.tokenization import words
from agent_data_workbench.exploration.clustering.vectors import tfidf_vectors
from agent_data_workbench.exploration.schemas import ClusterQuery
from agent_data_workbench.exploration.search import matching_rows
from agent_data_workbench.shared.identifiers import stable_id
from agent_data_workbench.shared.json import digest, json_text, pointer_value


def cluster(store: TraceStore, request: ClusterQuery) -> dict:
    documents, omitted = [], []
    eligible = sampled = 0
    source_hash = hashlib.sha256()
    for row in matching_rows(store, request.query):
        eligible += 1
        source_hash.update(json_text([row["trace_id"], digest(row["data"])]).encode())
        if request.limit is not None and sampled >= request.limit:
            continue
        sampled += 1
        try:
            counts = Counter(words(pointer_value(row["data"], request.pointer)))
        except ValueError:
            counts = Counter()
        if counts:
            documents.append((row["trace_id"], counts))
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
        "eligible": eligible,
        "sampled": sampled,
        "clustered": len(documents),
        "omitted_ids": omitted,
        "text_limit_chars": None,
        "text_truncated_ids": [],
        "truncated": eligible > sampled,
        "source_sha256": source_hash.hexdigest(),
        "clusters": clusters,
        "scope": "Lexical similarity using complete selected values. All matching traces are "
        "included unless you set a maximum. Transitive links may "
        "join traces below the pairwise threshold. These are not semantic labels.",
    }
