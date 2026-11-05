#!/usr/bin/env python3
"""ONE naming convention for a `\u00a7N` citation, shared by every leg that judges one.

Origin (issue #614), ruled at ledger `n=4744`. Two gates judge citations and they MUST
agree about what naming means, or a row passes one and reds the other on the same
sentence:

* `tests/test_ledger_citation_declared.py` -- a ledger row's `\u00a7N` must name something a
  reader can follow.
* `tests/test_citation_clause_titles.py` -- a source file's `\u00a7<title>` must resolve in the
  law corpus, and its `\u00a7N` must name a document.

Until #614 that convention was a markdown token and NOTHING else, `([A-Za-z0-9_./-]+\\.md)`,
declared twice in prose as "one convention, both legs". It was one convention and it was
too narrow by one token type: `TEMPLATE/tools/questions`'s selftest `\u00a77` names a CODE
ARTIFACT's numbered comment block, and no `*.md` token can exist there because the
artifact is not markdown. The predicate read a precise, greppable, in-tree citation as
bare. The row it reddened (n=4723) had to be excused, and an exemption for a citation that
is CORRECT is debt with a dated deletion -- this module is that deletion.

WHAT CHANGED, AND THE HALF THAT DID NOT. The markdown token keeps its EXACT former
behaviour: accepted on SHAPE alone, whether or not this tree carries the document, because
a citation into a member's `fleet-directives.md` still names something a reader can follow
and the clause-title leg treats a non-carried document as unresolvable-but-exempt rather
than as a defect. The widening is strictly ADDITIVE, so nothing that passed before this
module can fail after it -- a property the gates rely on, and the reason the markdown half
was not folded into the carriage rule along with everything else.

A path token of any other kind is accepted only when it clears TWO tests, and both are
load-bearing. First, this tree must actually CARRY it: a pure shape test on
`[A-Za-z0-9_.-]+(/[A-Za-z0-9_.-]+)+` also matches `origin/main`, `Europe/Moscow` and
`TOPIC/ROLE`, and each of those would launder a bare citation that names no artifact at
all -- the #184 harm shape this whole gate family exists to red on. Second, the number must
ATTACH to the token (`OWNED_GAP`): carriage alone was measured to launder seven rows that
name a real artifact which is not the cited document, so the module records that measurement
beside the rule rather than leaving it to be rediscovered.

CARRIAGE, defined. A token resolves when it names, in this tree: a file by its path; a
directory by its path; a path under `TEMPLATE/` whose TEMPLATE-stripped form is carried (a
member tree receives `TEMPLATE/tools/questions` as `tools/questions`, and a row may name
either form); or a basename that is UNIQUE in the tree, since a reader holding the tree can
resolve an unambiguous name and nothing else can collide with it. A basename carried more
than once does NOT resolve -- `registry.py` names two different files, so it names neither.
"""

from __future__ import annotations

import re
from pathlib import Path

# A MARKDOWN document token. Unchanged from the convention both legs shipped before #614,
# and accepted on SHAPE ALONE -- see the module docstring for why the carriage rule is not
# applied to it. `SKILL` with no extension is deliberately NOT a token: every factory
# carries its own copy with its own numbering (#184).
MARKDOWN_TOKEN = re.compile(r"([A-Za-z0-9_./-]+\.md)")

# A PATH token: at least one separator. This is a CANDIDATE, never a verdict -- `origin/main`
# and `Europe/Moscow` match it too, and `resolves` is what rejects them.
PATH_TOKEN = re.compile(r"([A-Za-z0-9_.+-]+(?:/[A-Za-z0-9_.+-]+)+)")

# A code artifact named by FILENAME with an extension of any kind. Also a CANDIDATE: the
# shape admits prose debris (`e.g`) and regex fragments (`try.py`), and the carriage test
# is what separates a real artifact from either.
CODE_TOKEN = re.compile(r"([A-Za-z0-9_.-]+\.[A-Za-z0-9]+)")

# A token's trailing punctuation is not part of its name: `TEMPLATE/tools/questions.` ends
# a sentence, and `(registry/gates.json)` is parenthesised.
TRAILING = ".,;:)]}>\u2019'\""

# OWNERSHIP: a number belongs to a token only when the token OWNS it. Everything between
# the token and the `\u00a7` must be nothing (whitespace, a backtick, a list comma) or a
# POSSESSIVE -- optionally reached through a line reference (`file.py:740's "\u00a711"`).
#
# Carriage alone is NOT enough, and this is measured rather than argued (2026-11-05, before
# this rule existed): asked of the tree, the loose predicate newly qualified TEN rows and
# only THREE of them own their number. The other seven are the exact laundering shape the
# module exists to prevent, each naming a real artifact that is not the cited document --
# `registry/gates.json re-derived under \u00a75.2` (the clause belongs to the SKILL, the JSON
# file carries no sections), `tests/gate_registry.py, DOES differ but is NOT one of \u00a72's
# eleven` (that \u00a72 is the DOC's), and `tests/test_gate_registration.py:2134 carried a bare
# \u00a75.2` -- a row REPORTING a bare citation, where the path names the file the quote came
# from and naming the document would defeat the sentence. Two of those seven were already
# excused with a hand-written referent, so the loose rule would have turned real debt into a
# silent clean read: the gate would have stopped printing the referent it had been carrying.
#
# The rule is grammatical, not a word list, so it does not rot: "X's selftest \u00a77" and
# "`X` \u00a77" attach the number to X, while "X re-derived under \u00a75.2" attaches it to
# something the sentence never names.
OWNED_GAP = re.compile(r"^[`\s]*[,;:]?\s*$|^[`\s]*(?::\d+)?[`\s]*['\u2019]s\b")

# Built once per repository per process. The walk is ~0.4 s over this tree and the ledger
# leg asks the question for every `\u00a7N` in every governed row, so an uncached index would
# make the gate quadratic for no gain.
_INDEX_CACHE: dict[str, tuple[frozenset[str], frozenset[str], frozenset[str]]] = {}


def artifact_index(repo: Path | str) -> tuple[frozenset[str], frozenset[str], frozenset[str]]:
    """(files, dirs, unique basenames) this tree carries, cached per repository.

    `__pycache__` is skipped: a compiled bytecode file is not an artifact a citation may
    name, and including it would let bytecode-shaped debris resolve.
    """
    key = str(Path(repo).resolve())
    cached = _INDEX_CACHE.get(key)
    if cached is not None:
        return cached
    root = Path(key)
    files: set[str] = set()
    dirs: set[str] = set()
    basenames: dict[str, list[str]] = {}
    for path in root.rglob("*"):
        if ".git" in path.parts or "__pycache__" in path.parts:
            continue
        try:
            rel = path.relative_to(root).as_posix()
        except ValueError:  # pragma: no cover - rglob yields only descendants
            continue
        if path.is_dir():
            dirs.add(rel)
        elif path.is_file():
            files.add(rel)
            basenames.setdefault(path.name, []).append(rel)
    unique = frozenset(name for name, holders in basenames.items() if len(holders) == 1)
    out = (frozenset(files), frozenset(dirs), unique)
    _INDEX_CACHE[key] = out
    return out


def resolves(token: str, index: tuple[frozenset[str], frozenset[str], frozenset[str]]) -> bool:
    """Does `token` name an artifact THIS tree carries? See the module docstring."""
    files, dirs, unique = index
    name = token.strip().rstrip(TRAILING)
    if not name:
        return False
    if name in files or name in dirs:
        return True
    if name.startswith("TEMPLATE/") and name[len("TEMPLATE/"):] in files:
        return True
    if name.endswith("/") and name.rstrip("/") in dirs:
        return True
    if "/" not in name and name in unique:
        return True
    return False


def names_artifact(
    before: str, index: tuple[frozenset[str], frozenset[str], frozenset[str]]
) -> str | None:
    """The first token in `before` that OWNS the citation and names a resolvable artifact.

    `before` is the text PRECEDING a citation, and the direction is the house convention
    both legs already state: a citation names its document first.

    A markdown token is returned on SHAPE alone (see the module docstring). A path or code
    token must clear BOTH tests: this tree must carry it (`resolves`), and the number must
    attach to it (`OWNED_GAP`). Carriage without ownership is the laundering case.
    """
    markdown = MARKDOWN_TOKEN.search(before)
    if markdown:
        return markdown.group(1)
    for pattern in (PATH_TOKEN, CODE_TOKEN):
        for match in pattern.finditer(before):
            if not resolves(match.group(1), index):
                continue
            if not OWNED_GAP.match(before[match.end():]):
                continue
            return match.group(1).rstrip(TRAILING)
    return None
