"""Reads the example blocks of docs/contratos/ so tests check code against the docs."""

import re
from pathlib import Path

CONTRACTS_DIR = Path(__file__).resolve().parent.parent / "docs" / "contratos"


def code_blocks(doc: str, lang: str) -> list[str]:
    text = (CONTRACTS_DIR / doc).read_text(encoding="utf-8")
    return re.findall(rf"```{lang}\n(.*?)```", text, flags=re.DOTALL)
