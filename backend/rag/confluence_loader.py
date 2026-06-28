from pathlib import Path


def load_documents(path: Path) -> list[dict[str, str]]:
    docs: list[dict[str, str]] = []
    if not path.exists():
        return docs
    for file in sorted(path.glob("*")):
        if file.suffix.lower() not in {".txt", ".md"}:
            continue
        docs.append({"id": file.stem, "source": file.name, "text": file.read_text(encoding="utf-8")})
    return docs

