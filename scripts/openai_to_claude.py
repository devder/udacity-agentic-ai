#!/usr/bin/env python3
"""Convert course notebooks from the OpenAI client to the Anthropic Claude client.

Rewrites only the provider plumbing (imports, client, model enum, get_completion) via the
Python AST, leaving lesson content untouched. Aborts without writing if any OpenAI reference
survives, so a notebook is never left half-converted.

Usage: python scripts/openai_to_claude.py [--dry-run] NOTEBOOK [NOTEBOOK ...]
"""

from __future__ import annotations

import argparse
import ast
import difflib
import json
import os
import re
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

CLAUDE_MODELS = {
    "OPUS": "claude-opus-5-5",
    "SONNET": "claude-sonnet-5-5",
    "HAIKU": "claude-haiku-5-5",
}

# OpenAIModels member -> ClaudeModels member, matched by capability tier
MODEL_MAP = {
    "GPT_4O_MINI": "HAIKU",
    "GPT_41_NANO": "HAIKU",
    "GPT_41_MINI": "SONNET",
    "GPT_4O": "OPUS",
    "GPT_41": "OPUS",
}

GET_COMPLETION_PARAMS = ["system_prompt", "user_prompt", "model"]

# Literal phrase swaps for comments and strings left outside the rewritten definitions
PHRASE_MAP = {"OpenAI API": "Claude API"}

ANTHROPIC_IMPORTS = "import anthropic\nfrom dotenv import load_dotenv"
LOAD_DOTENV = "load_dotenv()"
CLIENT = "client = anthropic.Anthropic()"
MODELS_ENUM = "class ClaudeModels(str, Enum):\n" + "\n".join(
    f'    {name} = "{model_id}"' for name, model_id in CLAUDE_MODELS.items()
)
GET_COMPLETION = '''def get_completion(system_prompt, user_prompt, model=MODEL):
    """
    Get a completion from the Claude API.
    Args:
        system_prompt: The system prompt
        user_prompt: The user prompt
        model: The model to use (defaults to MODEL)
    Returns:
        The completion text
    """
    system_kwargs = {"system": system_prompt} if system_prompt is not None else {}
    try:
        response = client.beta.messages.create(
            model=model,
            max_tokens=16000,
            messages=[{"role": "user", "content": user_prompt}],
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            **system_kwargs
        )
    except (anthropic.APIStatusError, anthropic.APIConnectionError) as e:
        return f"An error occurred: {e}"
    if response.stop_reason == "refusal":
        return "The model declined this request."
    return "".join(block.text for block in response.content if block.type == "text")'''

OPENAI_MARKER = re.compile(r"openai|vocareum|chat\.completions|\.choices\[", re.IGNORECASE)
MODEL_REF = re.compile(r"\bOpenAIModels\.(\w+)\b")


class ConversionError(Exception):
    pass


@dataclass(frozen=True)
class Edit:
    start: int  # 0-based line index, inclusive
    end: int  # 0-based line index, exclusive; start == end inserts
    text: str


def node_span(node: ast.stmt) -> tuple[int, int]:
    first = min([node.lineno, *(d.lineno for d in getattr(node, "decorator_list", []))])
    return first - 1, node.end_lineno


def apply_edits(src: str, edits: list[Edit]) -> str:
    lines = src.split("\n")
    for edit in sorted(edits, key=lambda e: (e.start, e.end), reverse=True):
        lines[edit.start : edit.end] = edit.text.split("\n")
    return "\n".join(lines)


def is_openai_client(node: ast.stmt) -> bool:
    return (
        isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "OpenAI"
    )


def convert_definitions(src: str, cell_idx: int) -> str:
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return src  # cells with IPython magics are left to the residual check

    edits: list[Edit] = []
    needs_dotenv = False
    last_import_end = None
    for node in tree.body:
        start, end = node_span(node)
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            last_import_end = end
        if isinstance(node, ast.ImportFrom) and node.module == "openai":
            edits.append(Edit(start, end, ANTHROPIC_IMPORTS))
            needs_dotenv = True
        elif is_openai_client(node):
            if len(tree.body) == 1:
                return CLIENT  # drop the surrounding Vocareum setup comments too
            edits.append(Edit(start, end, CLIENT))
        elif isinstance(node, ast.ClassDef) and node.name == "OpenAIModels":
            edits.append(Edit(start, end, MODELS_ENUM))
        elif isinstance(node, ast.FunctionDef) and node.name == "get_completion":
            if "chat.completions" not in ast.get_source_segment(src, node):
                continue
            params = [a.arg for a in node.args.args]
            if params != GET_COMPLETION_PARAMS:
                raise ConversionError(
                    f"cell {cell_idx}: get_completion{tuple(params)} does not match the "
                    f"supported signature {tuple(GET_COMPLETION_PARAMS)}; extend GET_COMPLETION"
                )
            edits.append(Edit(start, end, GET_COMPLETION))

    if needs_dotenv:
        edits.append(Edit(last_import_end, last_import_end, LOAD_DOTENV))
    return apply_edits(src, edits)


def convert_references(src: str, cell_idx: int) -> str:
    def swap(match: re.Match) -> str:
        member = match.group(1)
        if member not in MODEL_MAP:
            raise ConversionError(f"cell {cell_idx}: no Claude mapping for OpenAIModels.{member}; add it to MODEL_MAP")
        return f"ClaudeModels.{MODEL_MAP[member]}"

    src = MODEL_REF.sub(swap, src)
    for old, new in PHRASE_MAP.items():
        src = src.replace(old, new)
    return src


def uses_os(sources: list[str]) -> bool:
    for src in sources:
        try:
            tree = ast.parse(src)
        except SyntaxError:
            if re.search(r"\bos\.", src):
                return True
            continue
        if any(isinstance(n, ast.Name) and n.id == "os" for n in ast.walk(tree)):
            return True
    return False


def drop_import_os(src: str) -> str:
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return src
    spans = [
        node_span(node)
        for node in tree.body
        if isinstance(node, ast.Import) and [a.name for a in node.names] == ["os"] and not node.names[0].asname
    ]
    lines = src.split("\n")
    for start, end in reversed(spans):
        del lines[start:end]
    return "\n".join(lines)


def residual_openai_refs(cells: dict[int, str]) -> list[str]:
    return [
        f"  cell {idx} line {n}: {line.strip()}"
        for idx, src in cells.items()
        for n, line in enumerate(src.split("\n"), start=1)
        if OPENAI_MARKER.search(line)
    ]


def convert_notebook(nb: dict) -> dict[int, tuple[str, str]]:
    """Mutates nb in place and returns {cell_index: (old_source, new_source)} for changed cells."""
    code_cells = {i: c for i, c in enumerate(nb["cells"]) if c["cell_type"] == "code"}
    original = {i: "".join(c["source"]) for i, c in code_cells.items()}

    converted = {i: convert_references(convert_definitions(src, i), i) for i, src in original.items()}
    if not uses_os(list(converted.values())):
        converted = {i: drop_import_os(src) for i, src in converted.items()}

    leftovers = residual_openai_refs(converted)
    if leftovers:
        raise ConversionError("OpenAI references remain after conversion:\n" + "\n".join(leftovers))

    changes = {i: (original[i], converted[i]) for i in code_cells if original[i] != converted[i]}
    for i, (_, new) in changes.items():
        cell = code_cells[i]
        cell["source"] = new.splitlines(keepends=True)
        cell["outputs"] = []
        cell["execution_count"] = None
    return changes


def detect_indent(raw: str) -> int:
    second_line = raw.split("\n", 2)[1] if raw.count("\n") >= 1 else ""
    return len(second_line) - len(second_line.lstrip(" ")) or 1


def write_atomic(path: Path, content: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise


def print_diff(path: Path, changes: dict[int, tuple[str, str]]) -> None:
    for idx, (old, new) in changes.items():
        diff = difflib.unified_diff(
            old.splitlines(),
            new.splitlines(),
            fromfile=f"{path} [cell {idx}] (openai)",
            tofile=f"{path} [cell {idx}] (claude)",
            lineterm="",
        )
        print("\n".join(diff), end="\n\n")


def process(path: Path, dry_run: bool) -> bool:
    raw = path.read_text(encoding="utf-8")
    nb = json.loads(raw)
    if not residual_openai_refs({i: "".join(c["source"]) for i, c in enumerate(nb["cells"]) if c["cell_type"] == "code"}):
        print(f"{path}: no OpenAI usage found, skipping")
        return True
    try:
        changes = convert_notebook(nb)
    except ConversionError as e:
        print(f"{path}: not converted\n{e}", file=sys.stderr)
        return False

    if dry_run:
        print_diff(path, changes)
        print(f"{path}: {len(changes)} cell(s) would change (dry run)")
        return True

    content = json.dumps(nb, indent=detect_indent(raw), ensure_ascii=False)
    write_atomic(path, content + ("\n" if raw.endswith("\n") else ""))
    print(f"{path}: converted {len(changes)} cell(s) {sorted(changes)}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("notebooks", nargs="+", type=Path, help="notebook(s) to convert in place")
    parser.add_argument("--dry-run", action="store_true", help="print the per-cell diff without writing")
    args = parser.parse_args()

    results = [process(p, args.dry_run) for p in args.notebooks]
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
