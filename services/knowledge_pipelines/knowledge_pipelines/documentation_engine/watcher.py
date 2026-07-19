import hashlib


def content_hash(content: str) -> str:
    return hashlib.sha256(content.encode()).hexdigest()


def has_changed(stored_hash: str, current_content: str) -> bool:
    if not stored_hash:
        return True  # never ingested before
    return content_hash(current_content) != stored_hash
