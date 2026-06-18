from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal


DiffCellType = Literal["context", "delete", "add", "empty"]


DiffLineKind = Literal["context", "added", "modified"]


@dataclass
class AfterCodeLine:
    code: str
    kind: DiffLineKind
    old_code: str | None = None


@dataclass
class SideBySideRow:
    left: str
    right: str
    left_type: DiffCellType
    right_type: DiffCellType


@dataclass
class ParsedFileDiff:
    old_path: str
    new_path: str
    rows: list[SideBySideRow]
    is_binary: bool = False

    @property
    def display_path(self) -> str:
        if self.old_path == self.new_path:
            return self.new_path or self.old_path
        if not self.old_path:
            return self.new_path
        if not self.new_path:
            return self.old_path
        return f"{self.old_path} → {self.new_path}"

    @property
    def before_lines(self) -> list[str]:
        return [row.left for row in self.rows if row.left_type in {"context", "delete"}]

    @property
    def after_lines(self) -> list[str]:
        return [row.right for row in self.rows if row.right_type in {"context", "add"}]

    @property
    def after_code_lines(self) -> list[AfterCodeLine]:
        lines: list[AfterCodeLine] = []
        for row in self.rows:
            if row.right_type == "empty":
                continue
            if row.right_type == "context":
                lines.append(AfterCodeLine(code=row.right, kind="context"))
            elif row.right_type == "add":
                if row.left_type == "delete":
                    lines.append(AfterCodeLine(code=row.right, kind="modified", old_code=row.left))
                else:
                    lines.append(AfterCodeLine(code=row.right, kind="added"))
        return lines


def _parse_hunk_lines(hunk_lines: list[str]) -> list[SideBySideRow]:
    rows: list[SideBySideRow] = []
    index = 0

    while index < len(hunk_lines):
        line = hunk_lines[index]

        if line.startswith("\\"):
            index += 1
            continue

        if line.startswith(" "):
            content = line[1:]
            rows.append(SideBySideRow(content, content, "context", "context"))
            index += 1
            continue

        if line.startswith("-"):
            dels: list[str] = []
            while index < len(hunk_lines) and hunk_lines[index].startswith("-"):
                dels.append(hunk_lines[index][1:])
                index += 1
            adds: list[str] = []
            while index < len(hunk_lines) and hunk_lines[index].startswith("+"):
                adds.append(hunk_lines[index][1:])
                index += 1
            max_len = max(len(dels), len(adds), 1)
            for offset in range(max_len):
                deleted = dels[offset] if offset < len(dels) else None
                added = adds[offset] if offset < len(adds) else None
                if deleted is not None and added is not None:
                    rows.append(SideBySideRow(deleted, added, "delete", "add"))
                elif deleted is not None:
                    rows.append(SideBySideRow(deleted, "", "delete", "empty"))
                elif added is not None:
                    rows.append(SideBySideRow("", added, "empty", "add"))
            continue

        if line.startswith("+"):
            adds = []
            while index < len(hunk_lines) and hunk_lines[index].startswith("+"):
                adds.append(hunk_lines[index][1:])
                index += 1
            for added in adds:
                rows.append(SideBySideRow("", added, "empty", "add"))
            continue

        index += 1

    return rows


def _parse_file_block(block: str) -> ParsedFileDiff | None:
    lines = block.split("\n")
    if not lines:
        return None

    old_path = ""
    new_path = ""
    is_binary = False
    hunk_lines: list[str] = []
    in_hunk = False

    for line in lines:
        if line.startswith("diff --git "):
            match = re.match(r"^diff --git a/(.+?) b/(.+)$", line)
            if match:
                old_path = match.group(1)
                new_path = match.group(2)
            continue
        if line.startswith("--- "):
            old_path = line[4:].removeprefix("a/")
            if old_path == "/dev/null":
                old_path = ""
            continue
        if line.startswith("+++ "):
            new_path = line[4:].removeprefix("b/")
            if new_path == "/dev/null":
                new_path = ""
            continue
        if "Binary files" in line or line.startswith("GIT binary patch"):
            is_binary = True
            continue
        if line.startswith("@@"):
            in_hunk = True
            continue
        if in_hunk:
            hunk_lines.append(line)

    if not old_path and not new_path:
        old_path = "unknown"
        new_path = "unknown"

    if is_binary:
        return ParsedFileDiff(old_path=old_path or new_path, new_path=new_path or old_path, rows=[], is_binary=True)

    rows = _parse_hunk_lines(hunk_lines)
    if not rows:
        return None

    return ParsedFileDiff(
        old_path=old_path or new_path,
        new_path=new_path or old_path,
        rows=rows,
        is_binary=False,
    )


def parse_unified_diff(diff: str) -> list[ParsedFileDiff]:
    trimmed = (diff or "").strip()
    if not trimmed:
        return []

    blocks = re.split(r"(?m)^diff --git ", trimmed)
    blocks = [block for block in blocks if block.strip()]

    files: list[ParsedFileDiff] = []
    if len(blocks) <= 1 and not trimmed.startswith("diff --git"):
        single = _parse_file_block(trimmed)
        if single:
            files.append(single)
        return files

    for block in blocks:
        parsed = _parse_file_block(f"diff --git {block}")
        if parsed:
            files.append(parsed)
    return files


def code_block_lang(path: str) -> str:
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    mapping = {
        "py": "python",
        "java": "java",
        "js": "javascript",
        "ts": "typescript",
        "tsx": "tsx",
        "jsx": "jsx",
        "go": "go",
        "rs": "rust",
        "sql": "sql",
        "yml": "yaml",
        "yaml": "yaml",
        "sh": "bash",
        "xml": "xml",
        "html": "html",
        "css": "css",
        "json": "json",
    }
    return mapping.get(ext, "")
