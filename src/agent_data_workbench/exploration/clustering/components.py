"""Connected components of the lexical similarity graph.

Membership is transitive: an edge can connect groups whose other members are
below the pairwise threshold. The explorer discloses this distinction.
"""

from collections import defaultdict

from agent_data_workbench.exploration.clustering.vectors import cosine_similarity


def connected_components(vectors: list[dict[str, float]], threshold: float) -> list[list[int]]:
    parent = list(range(len(vectors)))

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    for index, left in enumerate(vectors):
        for other in range(index + 1, len(vectors)):
            if cosine_similarity(left, vectors[other]) + 1e-12 >= threshold:
                parent[find(other)] = find(index)

    groups = defaultdict(list)
    for index in range(len(vectors)):
        groups[find(index)].append(index)
    return list(groups.values())
