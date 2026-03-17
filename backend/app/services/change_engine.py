from dataclasses import dataclass, field


class ChangeError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


@dataclass
class ChangeResult:
    content: str
    changes_applied: int
    summaries: list[str] = field(default_factory=list)


def _find_nth(text: str, target: str, n: int) -> int:
    """Find the nth occurrence of target in text (1-based). Returns -1 if not found."""
    start = 0
    for _ in range(n):
        pos = text.find(target, start)
        if pos == -1:
            return -1
        start = pos + 1
    return pos


def _count_occurrences(text: str, target: str) -> int:
    count = 0
    start = 0
    while True:
        pos = text.find(target, start)
        if pos == -1:
            return count
        count += 1
        start = pos + 1


def apply_changes(content: str, changes: list[dict]) -> ChangeResult:
    applied = 0
    summaries = []

    for change in changes:
        target_text = change["target"]["text"]
        replacement = change["replacement"]
        occurrence = change["target"].get("occurrence")

        # Replace all occurrences
        if occurrence == "all" or occurrence == 0:
            if target_text not in content:
                raise ChangeError(f"Target text '{target_text[:50]}' not found in document")
            content = content.replace(target_text, replacement)
            applied += 1
            summaries.append(f"Replaced all '{target_text[:30]}' with '{replacement[:30]}'")
            continue

        # Replace specific occurrence (default: first)
        n = occurrence if occurrence is not None else 1
        total = _count_occurrences(content, target_text)

        if total == 0:
            raise ChangeError(f"Target text '{target_text[:50]}' not found in document")
        if n > total:
            raise ChangeError(
                f"Target text '{target_text[:50]}' has only {total} occurrences, "
                f"but occurrence {n} was requested"
            )

        pos = _find_nth(content, target_text, n)
        content = content[:pos] + replacement + content[pos + len(target_text):]
        applied += 1
        summaries.append(f"Replaced occurrence {n} of '{target_text[:30]}' with '{replacement[:30]}'")

    return ChangeResult(content=content, changes_applied=applied, summaries=summaries)
