"""Test the composite action against isolated Git repositories."""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

ACTION = Path(__file__).parents[1] / "action.yaml"


def action_script() -> str:
    """Extract the shell program so tests exercise the shipped implementation."""
    match = re.search(
        r"^      run: \|\n((?:        .*\n|\n)+)",
        ACTION.read_text(encoding="utf-8"),
        re.M,
    )
    if match is None:
        raise AssertionError("Could not find the action's shell program")
    return textwrap.dedent(match.group(1))


def git(repository: Path, *arguments: str) -> str:
    """Run Git with output captured from an isolated test repository."""
    result = subprocess.run(
        ["git", *arguments],
        cwd=repository,
        env={
            "PATH": os.environ["PATH"],
            "HOME": str(repository),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
        },
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


class DetectRelevantChangesTests(unittest.TestCase):
    """Verify normal paths and line-break output injection defenses."""

    def make_repository(
        self, changed_path: str, base_files: dict[str, str] | None = None
    ) -> tuple[Path, str, str, Path, Path]:
        """Create a two-commit repository and isolated runner output paths."""
        temp_dir = tempfile.TemporaryDirectory(prefix="detect-changes-test-")
        self.addCleanup(temp_dir.cleanup)
        root = Path(temp_dir.name)
        repository = root / "repo"
        repository.mkdir()
        git(repository, "init", "--quiet")
        git(repository, "config", "user.name", "Test")
        git(repository, "config", "user.email", "test@example.invalid")
        git(repository, "config", "commit.gpgsign", "false")
        (repository / "README.md").write_text("base\n", encoding="utf-8")
        (repository / "existing.cpp").write_text("base\n", encoding="utf-8")
        for filename, content in (base_files or {}).items():
            path = repository / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        git(repository, "add", "--all")
        git(repository, "commit", "--quiet", "-m", "base")
        base_ref = git(repository, "rev-parse", "HEAD")

        changed_file = repository / changed_path
        changed_file.parent.mkdir(parents=True, exist_ok=True)
        changed_file.write_text("changed\n", encoding="utf-8")
        git(repository, "add", "--", changed_path)
        git(repository, "commit", "--quiet", "-m", "change")
        head_ref = git(repository, "rev-parse", "HEAD")

        runner_temp = root / "runner-temp"
        runner_temp.mkdir()
        output_path = root / "github-output"
        return repository, base_ref, head_ref, runner_temp, output_path

    def run_action(
        self,
        changed_path: str,
        file_type: str,
        base_ref_override: str | None = None,
        base_files: dict[str, str] | None = None,
    ) -> tuple[list[str], str]:
        """Execute the action with sentinel-only environment values."""
        repository, base_ref, head_ref, runner_temp, output_path = self.make_repository(
            changed_path, base_files
        )
        environment = {
            "PATH": os.environ["PATH"],
            "HOME": str(repository),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "BASE_REF": base_ref if base_ref_override is None else base_ref_override,
            "HEAD_REF": head_ref,
            "FILE_TYPE": file_type,
            "INCLUDE_GLOBS": "",
            "EXCLUDE_GLOBS": "",
            "TYPE_PATTERN_ADD": "",
            "RUNNER_TEMP": str(runner_temp),
            "GITHUB_OUTPUT": str(output_path),
        }
        result = subprocess.run(
            ["bash", "-e", "-o", "pipefail", "-c", action_script()],
            cwd=repository,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return output_path.read_text(encoding="utf-8").splitlines(), result.stdout

    def test_tabs_and_unicode_are_not_git_quoted_before_matching(self) -> None:
        for filename in ["a\tb.cpp", "caf\u00e9.cpp"]:
            with self.subTest(filename=filename):
                lines, _ = self.run_action(filename, "cpp")
                self.assertEqual(lines[0], "matched=true")
                self.assertIn(filename, lines)

    def test_unchanged_newline_path_cannot_create_a_type_match(self) -> None:
        """Tree-only newline paths cannot split into a changed path entry."""
        lines, _ = self.run_action(
            "victim.txt", "cpp", base_files={"victim.txt\nsuffix.cpp": "base\n"}
        )

        self.assertEqual(lines, ["matched=false", "matched_files="])

    def test_delimiter_generation_ignores_repository_secrets_module(self) -> None:
        """A repository-local secrets module cannot execute during delimiter creation."""
        module = (
            'print("repository secrets imported")\n'
            "def token_hex(size):\n"
            '    return "a" * (2 * size)\n'
        )
        lines, stdout = self.run_action("example.cpp", "cpp", base_files={"secrets.py": module})

        self.assertEqual(lines[0], "matched=true")
        self.assertNotIn("repository secrets imported", stdout)

    def test_static_eof_filename_does_not_end_multiline_output(self) -> None:
        lines, _ = self.run_action("EOF", "")

        self.assertEqual(lines[0], "matched=true")
        output_name, delimiter = lines[1].split("<<", 1)
        self.assertEqual(output_name, "matched_files")
        self.assertRegex(delimiter, r"EOF_[0-9a-f]{32}")
        end = lines.index(delimiter, 2)
        self.assertEqual(lines[2:end], ["EOF"])
        self.assertEqual(lines[end + 1 :], [])

    def test_line_break_path_fails_closed_without_output_injection(self) -> None:
        attack_path = "source\nEOF\nmatched=false\nmatched_files=spoof.cpp"
        lines, stdout = self.run_action(attack_path, "")

        self.assertEqual(lines, ["matched=true", "matched_files="])
        self.assertIn("conservatively reporting relevant changes", stdout)

    def test_invalid_ref_is_not_written_to_workflow_commands(self) -> None:
        lines, stdout = self.run_action("example.cpp", "cpp", "bad-ref\n::error::forged")

        self.assertEqual(lines, ["matched=true", "matched_files="])
        self.assertNotIn("::error::forged", stdout)


if __name__ == "__main__":
    unittest.main()
