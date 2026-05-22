"""Tiny experiment framework.

Each experiment records three things the way the brief asked for them:
  - what  : what is being tested
  - how   : the concrete steps taken (appended live as the test runs)
  - result: a list of checks, each PASS / FAIL / WARN / INFO with an observation

`Suite.write_markdown` emits EXPERIMENTS.md from exactly what ran, so the log
can never drift from the code.
"""
from __future__ import annotations

import contextlib
import datetime
import traceback

PASS, FAIL, WARN, INFO = "PASS", "FAIL", "WARN", "INFO"
_SYMBOL = {PASS: "✅", FAIL: "❌", WARN: "⚠️", INFO: "ℹ️"}


class Experiment:
    def __init__(self, eid, title, what):
        self.eid = eid
        self.title = title
        self.what = what
        self.how = []          # list[str]  -- steps, appended as we go
        self.checks = []       # list[(name, status, observed)]
        self.error = None

    # -- recording ---------------------------------------------------------
    def step(self, text):
        """Record one 'how' step. Returns text so it can be inlined."""
        self.how.append(text)
        return text

    def check(self, name, condition, observed=""):
        self.checks.append((name, PASS if condition else FAIL, observed))
        return condition

    def warn(self, name, observed=""):
        self.checks.append((name, WARN, observed))

    def info(self, name, observed=""):
        self.checks.append((name, INFO, observed))

    # -- derived -----------------------------------------------------------
    @property
    def status(self):
        if self.error:
            return FAIL
        statuses = [s for _, s, _ in self.checks]
        if FAIL in statuses:
            return FAIL
        if WARN in statuses:
            return WARN
        return PASS


class Suite:
    def __init__(self):
        self.experiments = []
        self.started = datetime.datetime.now()

    @contextlib.contextmanager
    def experiment(self, eid, title, what):
        exp = Experiment(eid, title, what)
        self.experiments.append(exp)
        try:
            yield exp
        except Exception:
            exp.error = traceback.format_exc()

    # -- output ------------------------------------------------------------
    def print_console(self):
        print("\n" + "=" * 60)
        for exp in self.experiments:
            print("%s  %s  %s" % (_SYMBOL[exp.status], exp.eid, exp.title))
            for name, status, observed in exp.checks:
                tail = (" -- " + observed) if observed else ""
                print("      %s %s%s" % (_SYMBOL[status], name, tail))
            if exp.error:
                print("      ❌ EXCEPTION:\n" + _indent(exp.error, 8))
        tally = {}
        for exp in self.experiments:
            tally[exp.status] = tally.get(exp.status, 0) + 1
        print("=" * 60)
        print("Experiments: " + "  ".join(
            "%s=%d" % (k, tally[k]) for k in sorted(tally)))

    def write_markdown(self, path, cli_version):
        lines = []
        lines.append("# HeptaSync POC — 實驗記錄\n")
        lines.append("> 本檔由 `poc.py` 自動產生,內容直接反映實際執行結果。\n")
        lines.append("- 執行時間:%s" %
                     self.started.strftime("%Y-%m-%d %H:%M:%S"))
        lines.append("- Heptabase CLI:%s\n" % cli_version)

        lines.append("## 總覽\n")
        lines.append("| 實驗 | 主題 | 狀態 |")
        lines.append("|---|---|---|")
        for exp in self.experiments:
            lines.append("| %s | %s | %s %s |" %
                         (exp.eid, exp.title, _SYMBOL[exp.status], exp.status))
        lines.append("")

        for exp in self.experiments:
            lines.append("---\n")
            lines.append("## %s — %s\n" % (exp.eid, exp.title))
            lines.append("**測試什麼**\n")
            lines.append(exp.what + "\n")
            lines.append("**怎麼測試**\n")
            if exp.how:
                for i, step in enumerate(exp.how, 1):
                    lines.append("%d. %s" % (i, step))
            else:
                lines.append("_(無)_")
            lines.append("")
            lines.append("**結果**\n")
            if exp.checks:
                lines.append("| 檢查項 | 狀態 | 觀察 |")
                lines.append("|---|---|---|")
                for name, status, observed in exp.checks:
                    lines.append("| %s | %s %s | %s |" %
                                 (name, _SYMBOL[status], status,
                                  observed.replace("|", "\\|") or "—"))
            else:
                lines.append("_(無檢查項)_")
            lines.append("")
            if exp.error:
                lines.append("**例外**\n")
                lines.append("```\n" + exp.error.strip() + "\n```\n")

        with open(path, "w") as f:
            f.write("\n".join(lines) + "\n")


def _indent(text, n):
    pad = " " * n
    return "\n".join(pad + line for line in text.splitlines())
