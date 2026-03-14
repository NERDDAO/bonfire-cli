"""Content-addressed hashing for kEngram provenance.

Node and edge hashes are SHA-256 digests of their KG content.
The merkle root is built from sorted leaf hashes to ensure
order-independent determinism.
"""

import hashlib


def hash_node(uuid: str, name: str, summary: str, labels: list[str]) -> str:
    sorted_labels = "|".join(sorted(labels))
    content = f"{uuid}|{name}|{summary}|{sorted_labels}"
    return hashlib.sha256(content.encode()).hexdigest()


def hash_edge(source_uuid: str, target_uuid: str, name: str, fact: str) -> str:
    content = f"{source_uuid}|{target_uuid}|{name}|{fact}"
    return hashlib.sha256(content.encode()).hexdigest()


def merkle_root(leaf_hashes: list[str]) -> str:
    if not leaf_hashes:
        return hashlib.sha256(b"").hexdigest()
    if len(leaf_hashes) == 1:
        return leaf_hashes[0]

    sorted_leaves = sorted(leaf_hashes)
    level = sorted_leaves

    while len(level) > 1:
        next_level: list[str] = []
        for i in range(0, len(level), 2):
            left = level[i]
            right = level[i + 1] if i + 1 < len(level) else left
            combined = f"{left}{right}"
            next_level.append(hashlib.sha256(combined.encode()).hexdigest())
        level = next_level

    return level[0]
