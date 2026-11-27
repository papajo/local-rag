"""Plain-English behaviour specs (Gherkin) for the ask router — stdlib only.

The `features/*.feature` files say, in words a non-programmer can check,
what `local-rag ask` must do on the bundled (fictional) sample corpora:
which questions it answers, which it declines, what it cites, and which
route it takes. This module reads those files and runs every scenario
against the real router (`route_answer`), with no extra dependency
(no behave / pytest-bdd).

Idea borrowed from Matt Wynne's "software factory" talk (Modern Software
Engineering, 2026-11-25): the human owns the behaviour specs and reads
every word; the code can change underneath as long as the specs pass.

Supported steps (one per line, Given/When/Then/And/But all work):
  Given the documents in "<corpus folder>"
  Given the previous question was "<question>"
  When I ask "<question>"
  Then it answers | Then it declines | Then it may answer or decline
  Then it cites "<file>"                    (at least this file)
  Then it cites one of "<a>", "<b>"         (at least one of them)
  Then it cites all of "<a>", "<b>"         (every one of them)
  Then it cites nothing
  Then the answer comes from the "<route>" route
  Then the cited section is "<heading>"     (on a citation of an expected file)
  Then it does not use the "<route>" route
  Then it does not cite "<file>"
  Then it does not quote the section "<heading>"
Every scenario also checks, without a step, that each quote is word-for-
word inside the passage it cites.

A scenario tagged @known-failure is a real failure kept visible (see
BACKLOG.md). It is reported every run but does not fail the run; if one
starts passing, the run says so, so it can be moved off the backlog.
An unknown step is an error, never silently skipped.

Run:  python -m local_rag.specs        (exit 0 = every gated scenario passes)
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from local_rag.agent import route_answer
from local_rag.config import find_demo_dir
from local_rag.hybrid import HybridIndex, load_corpus

KEYWORDS = ("Given ", "When ", "Then ", "And ", "But ")
QUOTED = re.compile(r'"((?:[^"\\]|\\.)*)"')  # "..." with \" escapes


@dataclass
class Scenario:
    name: str
    feature: str
    file: str
    line: int
    tags: list[str] = field(default_factory=list)
    steps: list[str] = field(default_factory=list)

    @property
    def known_failure(self) -> bool:
        return "@known-failure" in self.tags

    @property
    def case_ids(self) -> list[str]:
        """Eval case ids this scenario covers (tags like @N2, @Q10)."""
        return [t[1:] for t in self.tags if re.fullmatch(r"@[A-Z]+\d+", t)]


class SpecError(Exception):
    """A malformed feature file or an unknown step."""


def parse_feature(path: Path) -> list[Scenario]:
    feature = ""
    background: list[str] = []
    scenarios: list[Scenario] = []
    pending_tags: list[str] = []
    current: list[str] | None = None
    for n, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("@"):
            pending_tags += line.split()
        elif line.startswith("Feature:"):
            feature = line[len("Feature:"):].strip()
            pending_tags = []
            current = None
        elif line.startswith("Background:"):
            current = background
        elif line.startswith("Scenario:"):
            sc = Scenario(name=line[len("Scenario:"):].strip(), feature=feature,
                          file=path.name, line=n, tags=pending_tags)
            pending_tags = []
            scenarios.append(sc)
            current = sc.steps
        elif line.startswith(KEYWORDS) and current is not None:
            current.append(line.split(" ", 1)[1].strip())
        elif current is None and feature:
            continue  # free-text description under the Feature line
        else:
            raise SpecError(f"{path.name}:{n}: cannot read line: {line}")
    for sc in scenarios:
        sc.steps = background + sc.steps
    return scenarios


def load_specs(features_dir: Path | None = None) -> list[Scenario]:
    features_dir = features_dir or find_demo_dir("features")
    files = sorted(features_dir.glob("*.feature"))
    if not files:
        raise SpecError(f"no .feature files in {features_dir}")
    out: list[Scenario] = []
    for f in files:
        out += parse_feature(f)
    return out


_indexes: dict[str, HybridIndex] = {}


def _index(corpus: str) -> HybridIndex:
    if corpus not in _indexes:
        _indexes[corpus] = HybridIndex(load_corpus(find_demo_dir(corpus)))
    return _indexes[corpus]


def run_scenario(sc: Scenario) -> tuple[bool, list[str]]:
    """Run one scenario. Returns (passed, failure messages)."""
    corpus = previous = None
    result = None
    expected_files: set[str] = set()
    failures: list[str] = []

    def need_result(step: str):
        if result is None:
            raise SpecError(f"{sc.file}:{sc.line}: '{step}' comes before 'When I ask'")
        return result

    for step in sc.steps:
        args = [a.replace('\\"', '"') for a in QUOTED.findall(step)]
        shape = QUOTED.sub('""', step)  # step with every quoted value emptied
        if re.fullmatch(r'the documents in ""', shape):
            corpus = args[0]
        elif re.fullmatch(r'the previous question was ""', shape):
            previous = args[0]
        elif re.fullmatch(r'I ask ""', shape):
            if corpus is None:
                raise SpecError(f"{sc.file}:{sc.line}: no 'Given the documents in' step")
            result = route_answer(args[0], _index(corpus), top_k=3,
                                  previous_question=previous)
            for c in result.citations:  # implicit: quotes are word-for-word
                quote = " ".join(c.quote.rstrip("…").split())
                if quote not in " ".join(c.chunk_text.split()):
                    failures.append(f"quote from {c.source} is not word-for-word")
        elif step == "it answers":
            if need_result(step).status != "answered":
                failures.append(f"expected an answer, got {result.status}")
        elif step == "it declines":
            if need_result(step).status != "declined":
                failures.append(f"expected a decline, got an answer citing "
                                f"{sorted({c.source for c in result.citations})}")
        elif step == "it may answer or decline":
            need_result(step)
        elif re.fullmatch(r'it cites( one of| all of)? ""(, "")*', shape):
            r = need_result(step)
            expected_files = set(args)
            cited = {c.source for c in r.citations}
            if r.status == "declined" and "may answer or decline" in " ".join(sc.steps):
                if cited:
                    failures.append(f"declined but still cited {sorted(cited)}")
            elif step.startswith("it cites all of"):
                missing = expected_files - cited
                if missing:
                    failures.append(f"missing citations: {sorted(missing)}")
            elif not expected_files & cited:
                failures.append(f"expected a citation from {sorted(expected_files)}, "
                                f"got {sorted(cited) or 'none'}")
        elif step == "it cites nothing":
            cited = {c.source for c in need_result(step).citations}
            if cited:
                failures.append(f"expected no citations, got {sorted(cited)}")
        elif re.fullmatch(r'the answer comes from the "" route', shape):
            if need_result(step).path != args[0]:
                failures.append(f"expected route {args[0]}, got {result.path}")
        elif re.fullmatch(r'the cited section is ""', shape):
            r = need_result(step)
            if not any(c.section == args[0] and (not expected_files or c.source in expected_files)
                       for c in r.citations):
                got = sorted({f"{c.source} › {c.section}" for c in r.citations})
                failures.append(f"expected section '{args[0]}', got {got or 'none'}")
        elif re.fullmatch(r'it does not use the "" route', shape):
            if need_result(step).path == args[0]:
                failures.append(f"used the forbidden route {args[0]}")
        elif re.fullmatch(r'it does not cite ""', shape):
            if any(c.source == args[0] for c in need_result(step).citations):
                failures.append(f"cited the forbidden file {args[0]}")
        elif re.fullmatch(r'it does not quote the section ""', shape):
            if any(c.section == args[0] for c in need_result(step).citations):
                failures.append(f"quoted the forbidden section '{args[0]}'")
        else:
            raise SpecError(f"{sc.file}:{sc.line}: unknown step: {step}")
    if result is None:
        raise SpecError(f"{sc.file}:{sc.line}: scenario never asks a question")
    return (not failures), failures


def eval_ids_missing(scenarios: list[Scenario]) -> list[str]:
    """Eval case ids (eval/test_set*.json) that no scenario is tagged with.
    Keeps the plain-English specs and the JSON eval from drifting apart."""
    import json
    covered = {i for sc in scenarios for i in sc.case_ids}
    ids: list[str] = []
    for name in ("test_set.json", "test_set_extended.json"):
        ids += [q["id"] for q in json.loads(
            (find_demo_dir("eval") / name).read_text(encoding="utf-8"))["questions"]]
    return [i for i in ids if i not in covered]


def run_specs(features_dir: Path | None = None) -> dict:
    rows = []
    scenarios = load_specs(features_dir)
    missing = eval_ids_missing(scenarios)
    for sc in scenarios:
        ok, why = run_scenario(sc)
        rows.append({"name": sc.name, "file": sc.file, "known_failure": sc.known_failure,
                     "ids": sc.case_ids, "ok": ok, "why": why})
    gated = [r for r in rows if not r["known_failure"]]
    known = [r for r in rows if r["known_failure"]]
    return {"rows": rows, "summary": {
        "scenarios": len(rows),
        "gated_passed": f"{sum(r['ok'] for r in gated)}/{len(gated)}",
        "known_failures_still_failing": sum(not r["ok"] for r in known),
        "known_failures_now_passing": sum(r["ok"] for r in known),
        "eval_cases_without_a_spec": missing,
        "all_gated_pass": all(r["ok"] for r in gated) and not missing,
    }}


def print_report(report: dict) -> None:
    current = None
    for r in report["rows"]:
        if r["file"] != current:
            current = r["file"]
            print(f"  {current}")
        if r["known_failure"]:
            mark = "KNOWN-FAIL  " if not r["ok"] else "KNOWN-NOW-OK"
        else:
            mark = "OK  " if r["ok"] else "FAIL"
        print(f"    {mark} {r['name']}")
        if not r["ok"]:
            for w in r["why"]:
                print(f"           - {w}")
    for k, v in report["summary"].items():
        print(f"  {k}: {v}")


def main() -> int:
    try:
        report = run_specs()
    except SpecError as e:
        print(f"SPEC ERROR: {e}")
        return 2
    print("Behaviour specs (features/*.feature)")
    print_report(report)
    ok = report["summary"]["all_gated_pass"]
    print(f"\nRESULT: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
