"""Tests for the maker-checker orchestrator."""
from __future__ import annotations

import json
import os
import subprocess
import textwrap
from pathlib import Path
from unittest import mock

import pytest

import maker_checker as mc
from maker_checker_app import dashboard as dash
from maker_checker_app import bootstrap as bootstrap
from maker_checker_app import runtime as runtime_mod


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
}


def init_git_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-b", "main"], cwd=path, check=True, capture_output=True, text=True)
    subprocess.run(["git", "add", "."], cwd=path, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
        env=GIT_ENV,
    )


@pytest.fixture()
def tmp_workspace(tmp_path: Path) -> Path:
    """Create a minimal workspace with required dirs and files."""
    (tmp_path / "inputs").mkdir()
    (tmp_path / "inputs" / "task_prompt.txt").write_text("Do the thing.\n")
    (tmp_path / "inputs" / "evaluation_prompt.txt").write_text("Check the thing.\n")
    (tmp_path / "prompts" / "stages").mkdir(parents=True)
    for stage in mc.REQUIRED_STAGES:
        (tmp_path / "prompts" / "stages" / f"{stage}.txt").write_text(
            f"STAGE: {stage}\nCYCLE: {{cycle_index}}\n{{task_prompt}}\n{{recent_run_memory}}\n"
        )
    (tmp_path / "state.txt").write_text("baseline\n")
    (tmp_path / "runs").mkdir()
    init_git_repo(tmp_path)
    return tmp_path


@pytest.fixture()
def minimal_config_toml(tmp_workspace: Path) -> Path:
    """Write a minimal valid config.toml and return its path."""
    cfg = tmp_workspace / "config.toml"
    cfg.write_text(textwrap.dedent(f"""\
        [workflow]
        max_cycles = 2
        artifacts_dir = "{tmp_workspace / 'runs'}"

        [inputs]
        task_prompt_file = "{tmp_workspace / 'inputs' / 'task_prompt.txt'}"
        evaluation_prompt_file = "{tmp_workspace / 'inputs' / 'evaluation_prompt.txt'}"

        [agents.mock]
        command = ["echo", "hello"]
        input_mode = "stdin"
        timeout_sec = 10

        [stages.plan]
        agent = "mock"
        template_file = "{tmp_workspace / 'prompts' / 'stages' / 'plan.txt'}"

        [stages.critique]
        agent = "mock"
        template_file = "{tmp_workspace / 'prompts' / 'stages' / 'critique.txt'}"

        [stages.revise]
        agent = "mock"
        template_file = "{tmp_workspace / 'prompts' / 'stages' / 'revise.txt'}"

        [stages.execute]
        agent = "mock"
        template_file = "{tmp_workspace / 'prompts' / 'stages' / 'execute.txt'}"

        [stages.verify]
        agent = "mock"
        template_file = "{tmp_workspace / 'prompts' / 'stages' / 'verify.txt'}"

        [stages.evaluate]
        agent = "mock"
        template_file = "{tmp_workspace / 'prompts' / 'stages' / 'evaluate.txt'}"
    """))
    return cfg


# ---------------------------------------------------------------------------
# _ensure_list_command
# ---------------------------------------------------------------------------

class TestEnsureListCommand:
    def test_string_command(self):
        assert mc._ensure_list_command("echo hello", "test") == ["echo", "hello"]

    def test_list_command(self):
        assert mc._ensure_list_command(["echo", "hello"], "test") == ["echo", "hello"]

    def test_empty_string_raises(self):
        with pytest.raises(mc.WorkflowError, match="must not be empty"):
            mc._ensure_list_command("", "test")

    def test_empty_list_raises(self):
        with pytest.raises(mc.WorkflowError):
            mc._ensure_list_command([], "test")

    def test_non_string_list_raises(self):
        with pytest.raises(mc.WorkflowError):
            mc._ensure_list_command([1, 2], "test")

    def test_list_with_empty_string_raises(self):
        with pytest.raises(mc.WorkflowError):
            mc._ensure_list_command(["echo", ""], "test")

    def test_integer_raises(self):
        with pytest.raises(mc.WorkflowError):
            mc._ensure_list_command(42, "test")

    def test_string_with_quotes(self):
        result = mc._ensure_list_command('echo "hello world"', "test")
        assert result == ["echo", "hello world"]


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------

class TestLoadConfig:
    def test_valid_config(self, minimal_config_toml: Path):
        cfg = mc.load_config(minimal_config_toml)
        assert cfg.max_cycles == 2
        assert cfg.history_limit == mc.DEFAULT_HISTORY_LIMIT
        assert cfg.git.mode == mc.DEFAULT_GIT_MODE
        assert cfg.git.base_ref == mc.DEFAULT_GIT_BASE_REF
        assert cfg.git.linked_paths == mc.DEFAULT_GIT_LINKED_PATHS
        assert "mock" in cfg.agents
        assert set(cfg.stages.keys()) == set(mc.REQUIRED_STAGES)

    def test_missing_config_file(self, tmp_path: Path):
        with pytest.raises(mc.WorkflowError, match="Config file not found"):
            mc.load_config(tmp_path / "nope.toml")

    def test_max_cycles_zero_raises(self, minimal_config_toml: Path):
        text = minimal_config_toml.read_text().replace("max_cycles = 2", "max_cycles = 0")
        minimal_config_toml.write_text(text)
        with pytest.raises(mc.WorkflowError, match="max_cycles must be >= 1"):
            mc.load_config(minimal_config_toml)

    def test_no_agents_raises(self, tmp_workspace: Path):
        cfg = tmp_workspace / "bad.toml"
        cfg.write_text(textwrap.dedent("""\
            [workflow]
            max_cycles = 1

            [stages.plan]
            agent = "x"
            template_file = "plan.txt"
        """))
        with pytest.raises(mc.WorkflowError, match="No agents configured"):
            mc.load_config(cfg)

    def test_invalid_input_mode_raises(self, tmp_workspace: Path):
        cfg = tmp_workspace / "bad.toml"
        cfg.write_text(textwrap.dedent(f"""\
            [workflow]
            max_cycles = 1

            [agents.a]
            command = "echo hi"
            input_mode = "http"

            [stages.plan]
            agent = "a"
            template_file = "{tmp_workspace / 'prompts' / 'stages' / 'plan.txt'}"

            [stages.critique]
            agent = "a"
            template_file = "{tmp_workspace / 'prompts' / 'stages' / 'critique.txt'}"

            [stages.revise]
            agent = "a"
            template_file = "{tmp_workspace / 'prompts' / 'stages' / 'revise.txt'}"

            [stages.execute]
            agent = "a"
            template_file = "{tmp_workspace / 'prompts' / 'stages' / 'execute.txt'}"

            [stages.verify]
            agent = "a"
            template_file = "{tmp_workspace / 'prompts' / 'stages' / 'verify.txt'}"

            [stages.evaluate]
            agent = "a"
            template_file = "{tmp_workspace / 'prompts' / 'stages' / 'evaluate.txt'}"
        """))
        with pytest.raises(mc.WorkflowError, match="input_mode must be"):
            mc.load_config(cfg)

    def test_missing_stage_raises(self, tmp_workspace: Path):
        cfg = tmp_workspace / "bad.toml"
        cfg.write_text(textwrap.dedent("""\
            [workflow]
            max_cycles = 1

            [agents.a]
            command = "echo hi"

            [stages.plan]
            agent = "a"
            template_file = "plan.txt"
        """))
        with pytest.raises(mc.WorkflowError, match="Missing stage configuration"):
            mc.load_config(cfg)

    def test_unknown_agent_in_stage_raises(self, tmp_workspace: Path):
        cfg = tmp_workspace / "bad.toml"
        stages = ""
        for s in mc.REQUIRED_STAGES:
            stages += f'\n[stages.{s}]\nagent = "nonexistent"\ntemplate_file = "{tmp_workspace / "prompts" / "stages" / f"{s}.txt"}"\n'
        cfg.write_text(textwrap.dedent(f"""\
            [workflow]
            max_cycles = 1

            [agents.a]
            command = "echo hi"
            {stages}
        """))
        with pytest.raises(mc.WorkflowError, match="unknown agent"):
            mc.load_config(cfg)

    def test_relative_paths_resolve_from_config_dir(self, tmp_path: Path):
        (tmp_path / "briefs").mkdir()
        (tmp_path / "briefs" / "task.md").write_text("task\n")
        (tmp_path / "briefs" / "evaluation.md").write_text("eval\n")
        (tmp_path / "templates" / "stages").mkdir(parents=True)
        for stage in mc.REQUIRED_STAGES:
            (tmp_path / "templates" / "stages" / f"{stage}.md").write_text("hello\n")

        cfg = tmp_path / "config.toml"
        cfg.write_text(textwrap.dedent("""\
            [workflow]
            max_cycles = 1
            artifacts_dir = "runs"
            history_dir = "memory"

            [inputs]
            task_prompt_file = "briefs/task.md"
            evaluation_prompt_file = "briefs/evaluation.md"

            [agents.a]
            command = "echo hi"

            [stages.plan]
            agent = "a"
            template_file = "templates/stages/plan.md"

            [stages.critique]
            agent = "a"
            template_file = "templates/stages/critique.md"

            [stages.revise]
            agent = "a"
            template_file = "templates/stages/revise.md"

            [stages.execute]
            agent = "a"
            template_file = "templates/stages/execute.md"

            [stages.verify]
            agent = "a"
            template_file = "templates/stages/verify.md"

            [stages.evaluate]
            agent = "a"
            template_file = "templates/stages/evaluate.md"
        """))

        loaded = mc.load_config(cfg)
        assert loaded.task_prompt_file == (tmp_path / "briefs" / "task.md").resolve()
        assert loaded.evaluation_prompt_file == (tmp_path / "briefs" / "evaluation.md").resolve()
        assert loaded.history_dir == (tmp_path / "memory").resolve()
        assert loaded.git.worktrees_dir == (tmp_path / ".maker-checker" / "worktrees").resolve()

    def test_missing_template_paths_use_packaged_defaults(self, tmp_path: Path):
        (tmp_path / "briefs").mkdir()
        (tmp_path / "briefs" / "task.md").write_text("task\n")
        (tmp_path / "briefs" / "evaluation.md").write_text("eval\n")

        cfg = tmp_path / "config.toml"
        cfg.write_text(textwrap.dedent("""\
            [workflow]
            max_cycles = 1

            [agents.a]
            command = "echo hi"

            [stages.plan]
            agent = "a"

            [stages.critique]
            agent = "a"

            [stages.revise]
            agent = "a"

            [stages.execute]
            agent = "a"

            [stages.verify]
            agent = "a"

            [stages.evaluate]
            agent = "a"
        """))

        loaded = mc.load_config(cfg)
        for stage_name in mc.REQUIRED_STAGES:
            assert loaded.stages[stage_name].template_file.exists()
            assert f"/defaults/templates/stages/{stage_name}.md" in str(loaded.stages[stage_name].template_file)

    def test_custom_git_linked_paths_are_loaded(self, minimal_config_toml: Path):
        text = minimal_config_toml.read_text() + '\n[git]\nlinked_paths = [".env", "config/local.env"]\n'
        minimal_config_toml.write_text(text)
        loaded = mc.load_config(minimal_config_toml)
        assert loaded.git.linked_paths == (".env", "config/local.env")

    def test_git_linked_paths_reject_absolute_paths(self, minimal_config_toml: Path):
        text = minimal_config_toml.read_text() + '\n[git]\nlinked_paths = ["/tmp/secret.env"]\n'
        minimal_config_toml.write_text(text)
        with pytest.raises(mc.WorkflowError, match="relative paths"):
            mc.load_config(minimal_config_toml)


# ---------------------------------------------------------------------------
# read_text_file
# ---------------------------------------------------------------------------

class TestReadTextFile:
    def test_reads_content(self, tmp_path: Path):
        f = tmp_path / "hello.txt"
        f.write_text("  content  \n")
        assert mc.read_text_file(f, "test") == "content"

    def test_missing_file_raises(self, tmp_path: Path):
        with pytest.raises(mc.WorkflowError, match="not found"):
            mc.read_text_file(tmp_path / "nope.txt", "test")

    def test_empty_file_raises(self, tmp_path: Path):
        f = tmp_path / "empty.txt"
        f.write_text("   \n  ")
        with pytest.raises(mc.WorkflowError, match="is empty"):
            mc.read_text_file(f, "test")


class TestRuntimeHelpers:
    def test_find_recent_workspace_activity_prefers_non_ignored_files(self, tmp_path: Path):
        (tmp_path / ".venv").mkdir()
        (tmp_path / ".venv" / "ignored.txt").write_text("ignore me\n")
        (tmp_path / "output").mkdir()
        activity = tmp_path / "output" / "crawl_stdout.log"
        activity.write_text("use me\n")

        relative, mtime = runtime_mod.find_recent_workspace_activity(tmp_path, 0.0)

        assert relative == "output/crawl_stdout.log"
        assert isinstance(mtime, float)


# ---------------------------------------------------------------------------
# render_prompt
# ---------------------------------------------------------------------------

class TestRenderPrompt:
    def test_basic_substitution(self, tmp_path: Path):
        tpl = tmp_path / "tpl.txt"
        tpl.write_text("Hello {name}, cycle {cycle_index}!")
        result = mc.render_prompt(tpl, {"name": "world", "cycle_index": 1})
        assert result == "Hello world, cycle 1!\n"

    def test_missing_key_kept_as_placeholder(self, tmp_path: Path):
        tpl = tmp_path / "tpl.txt"
        tpl.write_text("Hello {name}, {unknown_var}!")
        result = mc.render_prompt(tpl, {"name": "world"})
        assert "{unknown_var}" in result

    def test_missing_template_raises(self, tmp_path: Path):
        with pytest.raises(mc.WorkflowError, match="Template file not found"):
            mc.render_prompt(tmp_path / "nope.txt", {})


# ---------------------------------------------------------------------------
# dedupe_preserve_order
# ---------------------------------------------------------------------------

class TestDedupePreserveOrder:
    def test_dedupes(self):
        assert mc.dedupe_preserve_order(["a", "b", "a", "c"]) == ["a", "b", "c"]

    def test_strips_and_skips_empty(self):
        assert mc.dedupe_preserve_order(["  a  ", "", "  ", "a"]) == ["a"]

    def test_empty_input(self):
        assert mc.dedupe_preserve_order([]) == []

    def test_preserves_order(self):
        assert mc.dedupe_preserve_order(["c", "b", "a"]) == ["c", "b", "a"]


# ---------------------------------------------------------------------------
# extract_first_json
# ---------------------------------------------------------------------------

class TestExtractFirstJson:
    def test_dict(self):
        assert mc.extract_first_json('some text {"a": 1} more') == {"a": 1}

    def test_list(self):
        assert mc.extract_first_json("before [1,2,3] after") == [1, 2, 3]

    def test_no_json(self):
        assert mc.extract_first_json("no json here") is None

    def test_empty_string(self):
        assert mc.extract_first_json("") is None

    def test_nested(self):
        result = mc.extract_first_json('{"a": {"b": [1]}}')
        assert result == {"a": {"b": [1]}}

    def test_invalid_json_skipped(self):
        result = mc.extract_first_json('{bad} {"good": true}')
        assert result == {"good": True}


# ---------------------------------------------------------------------------
# extract_token_totals / extract_reported_session_id
# ---------------------------------------------------------------------------

class TestRuntimeMetadataParsing:
    def test_extract_token_totals_from_nested_usage(self):
        value = '{"usage":{"input_tokens":12,"output_tokens":8,"total_tokens":20}}'
        assert mc.extract_token_totals(value) == {
            "input_tokens": 12,
            "output_tokens": 8,
            "total_tokens": 20,
        }

    def test_extract_token_totals_supports_prompt_completion_aliases(self):
        value = '{"prompt_tokens":5,"completion_tokens":7}'
        assert mc.extract_token_totals(value) == {
            "input_tokens": 5,
            "output_tokens": 7,
            "total_tokens": 12,
        }

    def test_extract_reported_session_id_from_text(self):
        value = "session id: abc-123-session"
        assert mc.extract_reported_session_id(value) == "abc-123-session"


# ---------------------------------------------------------------------------
# parse_assessment
# ---------------------------------------------------------------------------

class TestParseAssessment:
    def test_pass_with_no_issues(self):
        issues, passed = mc.parse_assessment('{"pass": true, "issues": []}')
        assert passed is True
        assert issues == []

    def test_fail_with_issues(self):
        issues, passed = mc.parse_assessment(
            '{"pass": false, "issues": ["bug 1", "bug 2"]}'
        )
        assert passed is False
        assert issues == ["bug 1", "bug 2"]

    def test_status_string_pass(self):
        issues, passed = mc.parse_assessment('{"status": "passed", "issues": []}')
        assert passed is True

    def test_status_string_fail(self):
        issues, passed = mc.parse_assessment('{"status": "fail", "issues": ["x"]}')
        assert passed is False

    def test_issues_as_string(self):
        issues, passed = mc.parse_assessment('{"issues": "single issue"}')
        assert issues == ["single issue"]
        assert passed is False

    def test_list_of_issues(self):
        issues, passed = mc.parse_assessment('["issue1", "issue2"]')
        assert issues == ["issue1", "issue2"]
        assert passed is False

    def test_no_issues_text_fallback(self):
        issues, passed = mc.parse_assessment("no issues found here")
        assert issues == []
        assert passed is True

    def test_deduplicates_issues(self):
        issues, _ = mc.parse_assessment('{"issues": ["dup", "dup", "other"]}')
        assert issues == ["dup", "other"]

    def test_empty_string_issues_filtered(self):
        issues, passed = mc.parse_assessment('{"issues": ["", "  ", "real"]}')
        assert issues == ["real"]
        assert passed is False

    def test_pass_inferred_from_empty_issues(self):
        issues, passed = mc.parse_assessment('{"issues": []}')
        assert passed is True

    def test_pass_false_overrides_empty_issues(self):
        issues, passed = mc.parse_assessment('{"pass": false, "issues": []}')
        assert passed is False

    def test_plain_text_no_json(self):
        issues, passed = mc.parse_assessment("everything looks good")
        assert issues == []
        assert passed is True


# ---------------------------------------------------------------------------
# SafeDict
# ---------------------------------------------------------------------------

class TestSafeDict:
    def test_missing_key_returns_placeholder(self):
        d = mc.SafeDict({"a": "1"})
        assert d["missing"] == "{missing}"

    def test_existing_key_returned(self):
        d = mc.SafeDict({"a": "1"})
        assert d["a"] == "1"


# ---------------------------------------------------------------------------
# build_cycle_context
# ---------------------------------------------------------------------------

class TestBuildCycleContext:
    def test_injects_cycle_info(self):
        ctx = mc.build_cycle_context({"task_prompt": "t"}, {}, 2, 5)
        assert ctx["cycle_index"] == 2
        assert ctx["max_cycles"] == 5

    def test_injects_stage_outputs(self):
        ctx = mc.build_cycle_context({}, {"plan": "the plan"}, 1, 3)
        assert ctx["plan_output"] == "the plan"

    def test_defaults_empty_stage_outputs(self):
        ctx = mc.build_cycle_context({}, {}, 1, 1)
        for stage in mc.REQUIRED_STAGES:
            assert ctx[f"{stage}_output"] == ""

    def test_does_not_mutate_base(self):
        base = {"task_prompt": "t"}
        mc.build_cycle_context(base, {"plan": "p"}, 1, 1)
        assert "plan_output" not in base


# ---------------------------------------------------------------------------
# build_issue_delta
# ---------------------------------------------------------------------------

class TestBuildIssueDelta:
    def test_build_issue_delta_tracks_resolved_and_introduced(self):
        delta = mc.build_issue_delta(["a", "b"], ["b", "c"])
        assert delta["resolved"] == ["a"]
        assert delta["introduced"] == ["c"]
        assert delta["persistent"] == ["b"]
        assert delta["summary"] == "resolved 1, introduced 1, carried 1"


# ---------------------------------------------------------------------------
# run_stage
# ---------------------------------------------------------------------------

class TestRunStage:
    def test_supports_useful_output_watchdog_only_for_codex_json(self):
        assert mc.supports_useful_output_watchdog(["codex", "exec", "--json", "-"]) is True
        assert mc.supports_useful_output_watchdog(["codex", "exec", "-"]) is False
        assert mc.supports_useful_output_watchdog(["claude", "-p"]) is False

    def test_prepare_stage_run_injects_codex_json_flag(self, tmp_path: Path):
        stage = mc.StageConfig(name="plan", agent="codex", template_file=Path("x"))
        agent = mc.AgentConfig(
            name="codex",
            command=["codex", "exec", "-o", "{output_file}", "-"],
            input_mode="stdin",
            timeout_sec=5,
        )
        invocation = mc.prepare_stage_run(stage, agent, "prompt", tmp_path / "stage")
        assert invocation["command"][:3] == ["codex", "exec", "--json"]

    def test_stdin_mode_captures_stdout(self, tmp_path: Path):
        stage = mc.StageConfig(name="test", agent="a", template_file=Path("x"))
        agent = mc.AgentConfig(name="a", command=["cat"], input_mode="stdin", timeout_sec=5)
        stage_dir = tmp_path / "stage"
        output, elapsed = mc.run_stage(stage, agent, "hello from stdin", stage_dir)
        assert output == "hello from stdin"
        assert (stage_dir / "prompt.txt").read_text() == "hello from stdin"
        assert (stage_dir / "exit_code.txt").read_text() == "0"
        assert elapsed >= 0

    def test_file_mode_no_stdin(self, tmp_path: Path):
        stage = mc.StageConfig(name="test", agent="a", template_file=Path("x"))
        agent = mc.AgentConfig(
            name="a", command=["echo", "file-mode-output"], input_mode="file", timeout_sec=5
        )
        stage_dir = tmp_path / "stage"
        output, elapsed = mc.run_stage(stage, agent, "ignored", stage_dir)
        assert output == "file-mode-output"
        assert elapsed >= 0

    def test_nonzero_exit_raises(self, tmp_path: Path):
        stage = mc.StageConfig(name="fail", agent="a", template_file=Path("x"))
        agent = mc.AgentConfig(name="a", command=["false"], input_mode="stdin", timeout_sec=5)
        with pytest.raises(mc.WorkflowError, match="failed with exit code"):
            mc.run_stage(stage, agent, "", tmp_path / "stage")

    def test_command_not_found_raises(self, tmp_path: Path):
        stage = mc.StageConfig(name="test", agent="a", template_file=Path("x"))
        agent = mc.AgentConfig(
            name="a", command=["nonexistent_binary_xyz"], input_mode="stdin", timeout_sec=5
        )
        with pytest.raises(mc.WorkflowError, match="Command not found"):
            mc.run_stage(stage, agent, "", tmp_path / "stage")

    def test_timeout_raises(self, tmp_path: Path):
        stage = mc.StageConfig(name="slow", agent="a", template_file=Path("x"), timeout_sec=1)
        agent = mc.AgentConfig(
            name="a", command=["sleep", "60"], input_mode="stdin", timeout_sec=1
        )
        with pytest.raises(mc.WorkflowError, match="timed out"):
            mc.run_stage(stage, agent, "", tmp_path / "stage")

    def test_codex_like_agent_uses_no_output_watchdog(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        script = tmp_path / "codex"
        script.write_text("#!/usr/bin/env bash\nexec sleep 60\n", encoding="utf-8")
        script.chmod(0o755)

        stage = mc.StageConfig(name="plan", agent="codex", template_file=Path("x"), timeout_sec=5)
        agent = mc.AgentConfig(
            name="codex",
            command=[str(script), "exec", "-"],
            input_mode="stdin",
            timeout_sec=5,
        )
        monkeypatch.setattr(runtime_mod, "INITIAL_USEFUL_OUTPUT_TIMEOUT_SEC", 1)

        with pytest.raises(mc.WorkflowError, match="no useful output"):
            mc.run_stage(stage, agent, "prompt", tmp_path / "stage")

    def test_output_file_preferred_over_stdout(self, tmp_path: Path):
        stage_dir = tmp_path / "stage"
        stage_dir.mkdir(parents=True)
        output_file = stage_dir / "assistant_output.txt"
        output_file.write_text("from file")
        stage = mc.StageConfig(name="test", agent="a", template_file=Path("x"))
        agent = mc.AgentConfig(
            name="a", command=["echo", "from stdout"], input_mode="file", timeout_sec=5
        )
        output, _ = mc.run_stage(stage, agent, "p", stage_dir)
        assert output == "from file"

    def test_placeholder_substitution(self, tmp_path: Path):
        stage = mc.StageConfig(name="test", agent="a", template_file=Path("x"))
        agent = mc.AgentConfig(
            name="a", command=["echo", "{stage_dir}"], input_mode="file", timeout_sec=5
        )
        stage_dir = tmp_path / "stage"
        output, _ = mc.run_stage(stage, agent, "p", stage_dir)
        assert str(stage_dir) in output

    def test_session_id_written(self, tmp_path: Path):
        stage = mc.StageConfig(name="test", agent="a", template_file=Path("x"))
        agent = mc.AgentConfig(name="a", command=["echo", "ok"], input_mode="file", timeout_sec=5)
        stage_dir = tmp_path / "stage"
        mc.run_stage(stage, agent, "p", stage_dir)
        sid = (stage_dir / "session_id.txt").read_text()
        assert len(sid) == 36  # UUID format

    def test_elapsed_sec_written(self, tmp_path: Path):
        stage = mc.StageConfig(name="test", agent="a", template_file=Path("x"))
        agent = mc.AgentConfig(name="a", command=["echo", "ok"], input_mode="file", timeout_sec=5)
        stage_dir = tmp_path / "stage"
        _, elapsed = mc.run_stage(stage, agent, "p", stage_dir)
        saved = float((stage_dir / "elapsed_sec.txt").read_text())
        assert saved == elapsed
        assert elapsed >= 0

    def test_stream_logs_written_to_files(self, tmp_path: Path):
        script = tmp_path / "stream.sh"
        script.write_text(textwrap.dedent("""\
            #!/usr/bin/env bash
            printf 'stdout line 1\\n'
            printf 'stderr line 1\\n' >&2
            printf 'assistant payload\\n' > "$1"
        """))
        script.chmod(0o755)

        stage = mc.StageConfig(name="test", agent="a", template_file=Path("x"))
        agent = mc.AgentConfig(
            name="a",
            command=[str(script), "{output_file}"],
            input_mode="stdin",
            timeout_sec=5,
        )
        stage_dir = tmp_path / "stage"
        output, _ = mc.run_stage(stage, agent, "prompt", stage_dir)
        assert output == "assistant payload"
        assert "stdout line 1" in (stage_dir / "stdout.txt").read_text()
        assert "stderr line 1" in (stage_dir / "stderr.txt").read_text()
        combined = (stage_dir / "combined.log").read_text()
        assert "[stdout] stdout line 1" in combined
        assert "[stderr] stderr line 1" in combined


# ---------------------------------------------------------------------------
# run_workflow
# ---------------------------------------------------------------------------

class TestRunWorkflow:
    def test_smoke_with_echo_agents(self, tmp_workspace: Path):
        """Runs a full workflow where every stage just echoes pass JSON."""
        # Create a shell script that outputs pass JSON for verify/evaluate
        mock_script = tmp_workspace / "mock_pass.sh"
        mock_script.write_text(textwrap.dedent("""\
            #!/usr/bin/env bash
            prompt="$(cat)"
            stage="$(printf '%s\\n' "$prompt" | awk -F': ' '/^STAGE: / {print tolower($2); exit}')"
            case "$stage" in
              verify|evaluate) echo '{"pass": true, "issues": []}' ;;
              *) echo "stage output for $stage" ;;
            esac
        """))
        mock_script.chmod(0o755)

        cfg = mc.WorkflowConfig(
            max_cycles=1,
            artifacts_dir=tmp_workspace / "runs",
            task_prompt_file=tmp_workspace / "inputs" / "task_prompt.txt",
            evaluation_prompt_file=tmp_workspace / "inputs" / "evaluation_prompt.txt",
            agents={"mock": mc.AgentConfig(
                name="mock",
                command=[str(mock_script)],
                input_mode="stdin",
                timeout_sec=10,
            )},
            stages={
                name: mc.StageConfig(
                    name=name,
                    agent="mock",
                    template_file=tmp_workspace / "prompts" / "stages" / f"{name}.txt",
                )
                for name in mc.REQUIRED_STAGES
            },
        )
        run_dir = mc.run_workflow(cfg)
        summary = json.loads((run_dir / "summary.json").read_text())
        assert summary["completed"] is True
        assert summary["cycles"][0]["verify_pass"] is True
        assert summary["cycles"][0]["evaluate_pass"] is True
        assert summary["cycles"][0]["elapsed_sec"] >= 0
        assert set(summary["cycles"][0]["stage_timings_sec"].keys()) == set(mc.REQUIRED_STAGES)
        for stage_time in summary["cycles"][0]["stage_timings_sec"].values():
            assert stage_time >= 0
        assert (run_dir / "final_plan.md").exists()
        assert (run_dir / "task_brief.md").exists()
        assert (run_dir / "evaluation_brief.md").exists()
        assert (run_dir / "status.md").exists()
        assert (run_dir / "status.json").exists()
        assert (run_dir / "run_summary.md").exists()
        assert (tmp_workspace / "memory" / "run_history.md").exists()
        assert (tmp_workspace / "runs" / "latest_status.md").exists()
        assert (tmp_workspace / "runs" / "latest_status.json").exists()
        assert (tmp_workspace / "runs" / "runtime_state.json").exists()
        assert (tmp_workspace / "runs" / "latest_summary.md").exists()
        status_payload = json.loads((run_dir / "status.json").read_text())
        assert status_payload["run_id"] == run_dir.name
        assert status_payload["stage_position"]["total"] == len(mc.REQUIRED_STAGES)
        assert status_payload["recent_events"]
        assert status_payload["runtime_totals"]["seconds_running"] >= 0
        assert "latest_outputs" in status_payload
        assert status_payload["workspace"]["mode"] == "worktree"
        assert Path(status_payload["workspace"]["cwd"]).exists()

    def test_multi_cycle_convergence(self, tmp_workspace: Path):
        """Fail first cycle, pass second cycle."""
        mock_script = tmp_workspace / "mock_converge.sh"
        mock_script.write_text(textwrap.dedent("""\
            #!/usr/bin/env bash
            prompt="$(cat)"
            stage="$(printf '%s\\n' "$prompt" | awk -F': ' '/^STAGE: / {print tolower($2); exit}')"
            cycle="$(printf '%s\\n' "$prompt" | awk -F': ' '/^CYCLE: / {print $2; exit}')"
            case "$stage" in
              verify)
                if [ "$cycle" = "1" ]; then
                  echo '{"pass": false, "issues": ["not done yet"]}'
                else
                  echo '{"pass": true, "issues": []}'
                fi
                ;;
              evaluate)
                if [ "$cycle" = "1" ]; then
                  echo '{"pass": false, "issues": ["missing tests"]}'
                else
                  echo '{"pass": true, "issues": []}'
                fi
                ;;
              *) echo "output for $stage cycle $cycle" ;;
            esac
        """))
        mock_script.chmod(0o755)

        cfg = mc.WorkflowConfig(
            max_cycles=3,
            artifacts_dir=tmp_workspace / "runs",
            task_prompt_file=tmp_workspace / "inputs" / "task_prompt.txt",
            evaluation_prompt_file=tmp_workspace / "inputs" / "evaluation_prompt.txt",
            agents={"mock": mc.AgentConfig(
                name="mock",
                command=[str(mock_script)],
                input_mode="stdin",
                timeout_sec=10,
            )},
            stages={
                name: mc.StageConfig(
                    name=name,
                    agent="mock",
                    template_file=tmp_workspace / "prompts" / "stages" / f"{name}.txt",
                )
                for name in mc.REQUIRED_STAGES
            },
        )
        run_dir = mc.run_workflow(cfg)
        summary = json.loads((run_dir / "summary.json").read_text())
        assert summary["completed"] is True
        assert summary["stopped_at_cycle"] == 2
        assert len(summary["cycles"]) == 2
        assert summary["cycles"][0]["evaluate_pass"] is False
        assert summary["cycles"][1]["evaluate_pass"] is True
        assert summary["cycles"][1]["retry_reason"] == "cycle 1 left 2 unresolved issue(s); verify failed; evaluate failed"
        assert summary["cycles"][1]["issue_delta"]["resolved"] == ["not done yet", "missing tests"]
        assert summary["cycles"][1]["issue_delta"]["introduced"] == []
        assert summary["history_file"].endswith("run_history.md")

    def test_stage_failure_writes_summary(self, tmp_workspace: Path):
        """A failing stage should still write summary.json with failure info."""
        cfg = mc.WorkflowConfig(
            max_cycles=1,
            artifacts_dir=tmp_workspace / "runs",
            task_prompt_file=tmp_workspace / "inputs" / "task_prompt.txt",
            evaluation_prompt_file=tmp_workspace / "inputs" / "evaluation_prompt.txt",
            agents={"mock": mc.AgentConfig(
                name="mock",
                command=["false"],
                input_mode="stdin",
                timeout_sec=5,
            )},
            stages={
                name: mc.StageConfig(
                    name=name,
                    agent="mock",
                    template_file=tmp_workspace / "prompts" / "stages" / f"{name}.txt",
                )
                for name in mc.REQUIRED_STAGES
            },
        )
        with pytest.raises(mc.WorkflowError):
            mc.run_workflow(cfg)

        # Summary should exist with failure info
        run_dirs = [path for path in (tmp_workspace / "runs").iterdir() if path.is_dir()]
        assert len(run_dirs) == 1
        summary = json.loads((run_dirs[0] / "summary.json").read_text())
        assert summary["completed"] is False
        assert summary["failure"] is not None
        assert summary["failure"]["cycle"] == 1
        assert (run_dirs[0] / "status.md").exists()
        assert (run_dirs[0] / "run_summary.md").exists()

    def test_max_cycles_exhausted(self, tmp_workspace: Path):
        """When issues persist, stops at max_cycles."""
        mock_script = tmp_workspace / "mock_always_fail.sh"
        mock_script.write_text(textwrap.dedent("""\
            #!/usr/bin/env bash
            prompt="$(cat)"
            stage="$(printf '%s\\n' "$prompt" | awk -F': ' '/^STAGE: / {print tolower($2); exit}')"
            case "$stage" in
              verify) echo '{"pass": false, "issues": ["still broken"]}' ;;
              evaluate) echo '{"pass": false, "issues": ["still failing"]}' ;;
              *) echo "output" ;;
            esac
        """))
        mock_script.chmod(0o755)

        cfg = mc.WorkflowConfig(
            max_cycles=2,
            artifacts_dir=tmp_workspace / "runs",
            task_prompt_file=tmp_workspace / "inputs" / "task_prompt.txt",
            evaluation_prompt_file=tmp_workspace / "inputs" / "evaluation_prompt.txt",
            agents={"mock": mc.AgentConfig(
                name="mock",
                command=[str(mock_script)],
                input_mode="stdin",
                timeout_sec=10,
            )},
            stages={
                name: mc.StageConfig(
                    name=name,
                    agent="mock",
                    template_file=tmp_workspace / "prompts" / "stages" / f"{name}.txt",
                )
                for name in mc.REQUIRED_STAGES
            },
        )
        run_dir = mc.run_workflow(cfg)
        summary = json.loads((run_dir / "summary.json").read_text())
        assert summary["completed"] is False
        assert len(summary["cycles"]) == 2

    def test_run_name_suffix(self, tmp_workspace: Path):
        mock_script = tmp_workspace / "mock_pass.sh"
        mock_script.write_text(textwrap.dedent("""\
            #!/usr/bin/env bash
            cat > /dev/null
            echo '{"pass": true, "issues": []}'
        """))
        mock_script.chmod(0o755)

        cfg = mc.WorkflowConfig(
            max_cycles=1,
            artifacts_dir=tmp_workspace / "runs",
            task_prompt_file=tmp_workspace / "inputs" / "task_prompt.txt",
            evaluation_prompt_file=tmp_workspace / "inputs" / "evaluation_prompt.txt",
            agents={"mock": mc.AgentConfig(
                name="mock", command=[str(mock_script)], input_mode="stdin", timeout_sec=10
            )},
            stages={
                name: mc.StageConfig(
                    name=name, agent="mock",
                    template_file=tmp_workspace / "prompts" / "stages" / f"{name}.txt",
                ) for name in mc.REQUIRED_STAGES
            },
        )
        run_dir = mc.run_workflow(cfg, run_name="my-test")
        assert "-my-test" in run_dir.name

    def test_second_run_injects_history_context(self, tmp_workspace: Path):
        mock_script = tmp_workspace / "mock_pass.sh"
        mock_script.write_text(textwrap.dedent("""\
            #!/usr/bin/env bash
            prompt="$(cat)"
            stage="$(printf '%s\\n' "$prompt" | awk -F': ' '/^STAGE: / {print tolower($2); exit}')"
            case "$stage" in
              verify|evaluate) echo '{"pass": true, "issues": []}' ;;
              *) echo "output for $stage" ;;
            esac
        """))
        mock_script.chmod(0o755)

        cfg = mc.WorkflowConfig(
            max_cycles=1,
            artifacts_dir=tmp_workspace / "runs",
            task_prompt_file=tmp_workspace / "inputs" / "task_prompt.txt",
            evaluation_prompt_file=tmp_workspace / "inputs" / "evaluation_prompt.txt",
            agents={"mock": mc.AgentConfig(
                name="mock",
                command=[str(mock_script)],
                input_mode="stdin",
                timeout_sec=10,
            )},
            stages={
                name: mc.StageConfig(
                    name=name,
                    agent="mock",
                    template_file=tmp_workspace / "prompts" / "stages" / f"{name}.txt",
                )
                for name in mc.REQUIRED_STAGES
            },
        )

        first_run = mc.run_workflow(cfg, run_name="first")
        second_run = mc.run_workflow(cfg, run_name="second")
        prompt_text = (second_run / "cycle-01" / "02-plan" / "prompt.txt").read_text()

        assert first_run.name in prompt_text
        assert "Outcome:" in prompt_text

    def test_run_executes_inside_isolated_worktree(self, tmp_workspace: Path):
        mock_script = tmp_workspace / "mock_isolated.sh"
        mock_script.write_text(textwrap.dedent("""\
            #!/usr/bin/env bash
            prompt="$(cat)"
            stage="$(printf '%s\\n' "$prompt" | awk -F': ' '/^STAGE: / {print tolower($2); exit}')"
            case "$stage" in
              execute)
                printf 'changed\\n' >> state.txt
                echo "executed in $(pwd)"
                ;;
              verify|evaluate) echo '{"pass": true, "issues": []}' ;;
              *) echo "output for $stage" ;;
            esac
        """))
        mock_script.chmod(0o755)

        cfg = mc.WorkflowConfig(
            max_cycles=1,
            artifacts_dir=tmp_workspace / "runs",
            task_prompt_file=tmp_workspace / "inputs" / "task_prompt.txt",
            evaluation_prompt_file=tmp_workspace / "inputs" / "evaluation_prompt.txt",
            agents={"mock": mc.AgentConfig(
                name="mock",
                command=[str(mock_script)],
                input_mode="stdin",
                timeout_sec=10,
            )},
            stages={
                name: mc.StageConfig(
                    name=name,
                    agent="mock",
                    template_file=tmp_workspace / "prompts" / "stages" / f"{name}.txt",
                )
                for name in mc.REQUIRED_STAGES
            },
        )

        run_dir = mc.run_workflow(cfg, run_name="isolated")
        summary = json.loads((run_dir / "summary.json").read_text())
        worktree_path = Path(summary["workspace"]["cwd"])

        assert summary["workspace"]["mode"] == "worktree"
        assert worktree_path != tmp_workspace
        assert (tmp_workspace / "state.txt").read_text() == "baseline\n"
        assert (worktree_path / "state.txt").read_text() == "baseline\nchanged\n"

    def test_run_links_local_env_files_into_worktree(self, tmp_workspace: Path):
        (tmp_workspace / ".env").write_text("API_KEY=present\n", encoding="utf-8")
        mock_script = tmp_workspace / "mock_linked_env.sh"
        mock_script.write_text(textwrap.dedent("""\
            #!/usr/bin/env bash
            prompt="$(cat)"
            stage="$(printf '%s\\n' "$prompt" | awk -F': ' '/^STAGE: / {print tolower($2); exit}')"
            case "$stage" in
              execute)
                if [ -L .env ] && [ "$(cat .env)" = "API_KEY=present" ]; then
                  echo "linked env visible"
                else
                  echo "linked env missing"
                  exit 1
                fi
                ;;
              verify|evaluate) echo '{"pass": true, "issues": []}' ;;
              *) echo "output for $stage" ;;
            esac
        """))
        mock_script.chmod(0o755)

        cfg = mc.WorkflowConfig(
            max_cycles=1,
            artifacts_dir=tmp_workspace / "runs",
            task_prompt_file=tmp_workspace / "inputs" / "task_prompt.txt",
            evaluation_prompt_file=tmp_workspace / "inputs" / "evaluation_prompt.txt",
            agents={"mock": mc.AgentConfig(
                name="mock",
                command=[str(mock_script)],
                input_mode="stdin",
                timeout_sec=10,
            )},
            stages={
                name: mc.StageConfig(
                    name=name,
                    agent="mock",
                    template_file=tmp_workspace / "prompts" / "stages" / f"{name}.txt",
                )
                for name in mc.REQUIRED_STAGES
            },
        )

        run_dir = mc.run_workflow(cfg, run_name="linked-env")
        summary = json.loads((run_dir / "summary.json").read_text())
        worktree_path = Path(summary["workspace"]["cwd"])

        assert summary["completed"] is True
        assert (worktree_path / ".env").is_symlink()
        assert (worktree_path / ".env").resolve() == (tmp_workspace / ".env").resolve()

    def test_successful_run_can_apply_changes_back_to_base_checkout(self, tmp_workspace: Path):
        mock_script = tmp_workspace / "mock_apply_back.sh"
        mock_script.write_text(textwrap.dedent("""\
            #!/usr/bin/env bash
            prompt="$(cat)"
            stage="$(printf '%s\\n' "$prompt" | awk -F': ' '/^STAGE: / {print tolower($2); exit}')"
            case "$stage" in
              execute)
                printf 'changed\\n' >> state.txt
                echo "applied change"
                ;;
              verify|evaluate) echo '{"pass": true, "issues": []}' ;;
              *) echo "output for $stage" ;;
            esac
        """))
        mock_script.chmod(0o755)
        (tmp_workspace / ".gitignore").write_text("runs/\n.maker-checker/\n", encoding="utf-8")
        subprocess.run(["git", "add", ".gitignore", str(mock_script)], cwd=tmp_workspace, check=True, capture_output=True, text=True)
        subprocess.run(
            ["git", "commit", "-m", "prepare apply-back fixtures"],
            cwd=tmp_workspace,
            check=True,
            capture_output=True,
            text=True,
            env=GIT_ENV,
        )

        cfg = mc.WorkflowConfig(
            max_cycles=1,
            artifacts_dir=tmp_workspace / "runs",
            task_prompt_file=tmp_workspace / "inputs" / "task_prompt.txt",
            evaluation_prompt_file=tmp_workspace / "inputs" / "evaluation_prompt.txt",
            agents={"mock": mc.AgentConfig(
                name="mock",
                command=[str(mock_script)],
                input_mode="stdin",
                timeout_sec=10,
            )},
            stages={
                name: mc.StageConfig(
                    name=name,
                    agent="mock",
                    template_file=tmp_workspace / "prompts" / "stages" / f"{name}.txt",
                )
                for name in mc.REQUIRED_STAGES
            },
            git=mc.GitConfig(
                mode="worktree",
                base_ref="HEAD",
                worktrees_dir=tmp_workspace / ".maker-checker" / "worktrees",
                apply_on_success=True,
            ),
        )

        run_dir = mc.run_workflow(cfg, run_name="apply-back")
        summary = json.loads((run_dir / "summary.json").read_text())

        assert summary["completed"] is True
        assert summary["workspace"]["apply_result"]["status"] == "applied"
        assert (tmp_workspace / "state.txt").read_text() == "baseline\nchanged\n"

    def test_apply_back_ignores_untracked_files_in_base_checkout(self, tmp_workspace: Path):
        mock_script = tmp_workspace / "mock_apply_back_untracked.sh"
        mock_script.write_text(textwrap.dedent("""\
            #!/usr/bin/env bash
            prompt="$(cat)"
            stage="$(printf '%s\\n' "$prompt" | awk -F': ' '/^STAGE: / {print tolower($2); exit}')"
            case "$stage" in
              execute)
                printf 'changed\\n' >> state.txt
                echo "applied change"
                ;;
              verify|evaluate) echo '{"pass": true, "issues": []}' ;;
              *) echo "output for $stage" ;;
            esac
        """))
        mock_script.chmod(0o755)
        (tmp_workspace / "notes.local.txt").write_text("keep me untracked\n", encoding="utf-8")

        cfg = mc.WorkflowConfig(
            max_cycles=1,
            artifacts_dir=tmp_workspace / "runs",
            task_prompt_file=tmp_workspace / "inputs" / "task_prompt.txt",
            evaluation_prompt_file=tmp_workspace / "inputs" / "evaluation_prompt.txt",
            agents={"mock": mc.AgentConfig(
                name="mock",
                command=[str(mock_script)],
                input_mode="stdin",
                timeout_sec=10,
            )},
            stages={
                name: mc.StageConfig(
                    name=name,
                    agent="mock",
                    template_file=tmp_workspace / "prompts" / "stages" / f"{name}.txt",
                )
                for name in mc.REQUIRED_STAGES
            },
            git=mc.GitConfig(
                mode="worktree",
                base_ref="HEAD",
                worktrees_dir=tmp_workspace / ".maker-checker" / "worktrees",
                apply_on_success=True,
            ),
        )

        run_dir = mc.run_workflow(cfg, run_name="apply-back-untracked")
        summary = json.loads((run_dir / "summary.json").read_text())

        assert summary["completed"] is True
        assert summary["workspace"]["apply_result"]["status"] == "applied"
        assert (tmp_workspace / "state.txt").read_text() == "baseline\nchanged\n"
        assert (tmp_workspace / "notes.local.txt").read_text() == "keep me untracked\n"

    def test_regressed_cycle_rolls_back_worktree(self, tmp_workspace: Path):
        mock_script = tmp_workspace / "mock_regress.sh"
        mock_script.write_text(textwrap.dedent("""\
            #!/usr/bin/env bash
            prompt="$(cat)"
            stage="$(printf '%s\\n' "$prompt" | awk -F': ' '/^STAGE: / {print tolower($2); exit}')"
            cycle="$(printf '%s\\n' "$prompt" | awk -F': ' '/^CYCLE: / {print $2; exit}')"
            case "$stage" in
              execute)
                printf 'cycle%s\\n' "$cycle" > state.txt
                echo "executed cycle $cycle"
                ;;
              verify)
                if [ "$cycle" = "1" ]; then
                  echo '{"pass": false, "issues": ["still broken"]}'
                else
                  echo '{"pass": false, "issues": ["still broken", "new regression", "another regression"]}'
                fi
                ;;
              evaluate)
                if [ "$cycle" = "1" ]; then
                  echo '{"pass": false, "issues": ["still broken"]}'
                else
                  echo '{"pass": false, "issues": ["still broken", "new regression", "another regression"]}'
                fi
                ;;
              *) echo "output for $stage cycle $cycle" ;;
            esac
        """))
        mock_script.chmod(0o755)

        cfg = mc.WorkflowConfig(
            max_cycles=2,
            artifacts_dir=tmp_workspace / "runs",
            task_prompt_file=tmp_workspace / "inputs" / "task_prompt.txt",
            evaluation_prompt_file=tmp_workspace / "inputs" / "evaluation_prompt.txt",
            agents={"mock": mc.AgentConfig(
                name="mock",
                command=[str(mock_script)],
                input_mode="stdin",
                timeout_sec=10,
            )},
            stages={
                name: mc.StageConfig(
                    name=name,
                    agent="mock",
                    template_file=tmp_workspace / "prompts" / "stages" / f"{name}.txt",
                )
                for name in mc.REQUIRED_STAGES
            },
        )

        run_dir = mc.run_workflow(cfg, run_name="regress")
        summary = json.loads((run_dir / "summary.json").read_text())
        worktree_path = Path(summary["workspace"]["cwd"])

        assert summary["completed"] is False
        assert summary["cycles"][1]["accepted"] is False
        assert "reverted_to_commit" in summary["cycles"][1]
        assert summary["workspace"]["rollbacks"]
        assert (tmp_workspace / "state.txt").read_text() == "baseline\n"
        assert (worktree_path / "state.txt").read_text() == "cycle1\n"


class TestDashboardHelpers:
    def test_list_runs_and_load_status(self, tmp_workspace: Path):
        mock_script = tmp_workspace / "mock_pass.sh"
        mock_script.write_text(textwrap.dedent("""\
            #!/usr/bin/env bash
            prompt="$(cat)"
            stage="$(printf '%s\\n' "$prompt" | awk -F': ' '/^STAGE: / {print tolower($2); exit}')"
            case "$stage" in
              verify|evaluate) echo '{"pass": true, "issues": []}' ;;
              *) echo "output for $stage" ;;
            esac
        """))
        mock_script.chmod(0o755)

        cfg = mc.WorkflowConfig(
            max_cycles=1,
            artifacts_dir=tmp_workspace / "runs",
            task_prompt_file=tmp_workspace / "inputs" / "task_prompt.txt",
            evaluation_prompt_file=tmp_workspace / "inputs" / "evaluation_prompt.txt",
            agents={"mock": mc.AgentConfig(
                name="mock",
                command=[str(mock_script)],
                input_mode="stdin",
                timeout_sec=10,
            )},
            stages={
                name: mc.StageConfig(
                    name=name,
                    agent="mock",
                    template_file=tmp_workspace / "prompts" / "stages" / f"{name}.txt",
                )
                for name in mc.REQUIRED_STAGES
            },
        )

        run_dir = mc.run_workflow(cfg, run_name="dash")
        runs = dash.list_runs(cfg)
        status = dash.load_status(cfg, run_dir.name)
        state = dash.build_state_payload(cfg)

        assert runs[0]["run_id"] == run_dir.name
        assert status["run_id"] == run_dir.name
        assert status["evaluation_state"]["evaluate_pass"] is True
        assert status["what_happened"]
        assert state["current_run"]["run_id"] == run_dir.name
        assert state["runs"][0]["run_id"] == run_dir.name
        assert "summary_markdown" in status
        stage_detail = dash.load_stage_detail(cfg, run_dir.name, 1, "plan")
        stage_logs = dash.load_stage_logs(cfg, run_dir.name, 1, "plan")
        assert stage_detail["content"]["primary_output"] == "output for plan\n"
        assert stage_detail["content"]["stdout"] == "output for plan\n"
        assert "STAGE: plan" in stage_detail["content"]["prompt"]
        assert "output for plan" in stage_logs["streams"]["stdout"]["text"]
        assert "[stdout]" in stage_logs["streams"]["combined"]["text"]

    def test_load_run_detail_refreshes_live_elapsed_and_events(self, tmp_workspace: Path):
        cfg = mc.WorkflowConfig(
            max_cycles=1,
            artifacts_dir=tmp_workspace / "runs",
            task_prompt_file=tmp_workspace / "inputs" / "task_prompt.txt",
            evaluation_prompt_file=tmp_workspace / "inputs" / "evaluation_prompt.txt",
            agents={"codex": mc.AgentConfig(
                name="codex",
                command=["echo", "hi"],
                input_mode="stdin",
                timeout_sec=10,
            )},
            stages={
                name: mc.StageConfig(
                    name=name,
                    agent="codex",
                    template_file=tmp_workspace / "prompts" / "stages" / f"{name}.txt",
                )
                for name in mc.REQUIRED_STAGES
            },
        )

        run_dir = tmp_workspace / "runs" / "20260312-live"
        stage_dir = run_dir / "cycle-01" / "02-plan"
        stage_dir.mkdir(parents=True)
        (stage_dir / "started_at.txt").write_text("2020-01-01T00:00:00\n")
        (stage_dir / "session_id.txt").write_text("session-1\n")
        (stage_dir / "stdout.txt").write_text("")
        (stage_dir / "stderr.txt").write_text("")
        (stage_dir / "combined.log").write_text("")
        (stage_dir / "heartbeat.json").write_text(json.dumps({
            "updated_at": "2026-03-12T00:28:11",
            "elapsed_sec": 12.0,
            "message": "activity: updated output/postfix/crawl_stdout.log",
        }))

        summary = {
            "started_at": "2020-01-01T00:00:00",
            "cycles": [],
            "completed": False,
            "failure": None,
            "history_loaded": False,
            "workspace": {
                "mode": "worktree",
                "cwd": str(tmp_workspace / ".maker-checker" / "worktrees" / "20260312-live"),
            },
        }
        progress = mc.init_progress(1)
        progress[1]["plan"] = mc.STATUS_RUNNING
        mc.write_status_files(
            config=cfg,
            run_dir=run_dir,
            summary=summary,
            progress=progress,
            state="running",
            active_cycle=1,
            active_stage="plan",
        )
        (run_dir / "run_process.json").write_text(json.dumps({
            "pid": os.getpid(),
            "state": "running",
            "active_cycle": 1,
            "active_stage": "plan",
            "started_at": summary["started_at"],
        }))
        (run_dir / "events.log").write_text(
            "[2026-03-12T00:28:09] cycle 1 started\n"
            "[2026-03-12T00:28:10] cycle 1 stage plan started via codex\n"
        )

        detail = dash.load_run_detail(cfg, run_dir.name)

        assert detail["active_stage"] == "plan"
        assert detail["last_event"] == "[2026-03-12T00:28:10] cycle 1 stage plan started via codex"
        assert detail["current_session"]["last_event"] == "activity: updated output/postfix/crawl_stdout.log"
        assert detail["runtime_totals"]["seconds_running"] > 0
        assert detail["what_happens_next"] == "Next expected step: plan."

    def test_load_run_detail_repairs_orphaned_running_run(self, tmp_workspace: Path):
        cfg = mc.WorkflowConfig(
            max_cycles=1,
            artifacts_dir=tmp_workspace / "runs",
            task_prompt_file=tmp_workspace / "inputs" / "task_prompt.txt",
            evaluation_prompt_file=tmp_workspace / "inputs" / "evaluation_prompt.txt",
            agents={"codex": mc.AgentConfig(
                name="codex",
                command=["echo", "hi"],
                input_mode="stdin",
                timeout_sec=10,
            )},
            stages={
                name: mc.StageConfig(
                    name=name,
                    agent="codex",
                    template_file=tmp_workspace / "prompts" / "stages" / f"{name}.txt",
                )
                for name in mc.REQUIRED_STAGES
            },
        )

        run_dir = tmp_workspace / "runs" / "20260312-stale"
        stage_dir = run_dir / "cycle-01" / "02-plan"
        stage_dir.mkdir(parents=True)
        (stage_dir / "stderr.txt").write_text("")
        (stage_dir / "combined.log").write_text("")

        summary = {
            "started_at": "2020-01-01T00:00:00",
            "cycles": [{
                "cycle": 1,
                "attempt": 1,
                "stages": {"plan": mc.STATUS_RUNNING},
                "issues": [],
                "elapsed_sec": None,
            }],
            "completed": False,
            "failure": None,
            "history_loaded": False,
            "workspace": {
                "mode": "worktree",
                "cwd": str(tmp_workspace / ".maker-checker" / "worktrees" / "20260312-stale"),
            },
        }
        progress = mc.init_progress(1)
        progress[1]["plan"] = mc.STATUS_RUNNING
        mc.write_status_files(
            config=cfg,
            run_dir=run_dir,
            summary=summary,
            progress=progress,
            state="running",
            active_cycle=1,
            active_stage="plan",
        )
        (run_dir / "events.log").write_text("[2026-03-12T00:28:09] cycle 1 stage plan started via codex\n")

        detail = dash.load_run_detail(cfg, run_dir.name)

        assert detail["state"] == "failed"
        assert detail["active_stage"] is None
        assert detail["what_is_happening"] == "Latest completed cycle is 1 with 0 unresolved issue(s)."
        assert detail["last_error"]["error"] == "Run was left in a running state but no workflow or active stage process is still alive."
        assert "dashboard repaired orphaned run" in (run_dir / "events.log").read_text(encoding="utf-8")
        assert json.loads((run_dir / "status.json").read_text(encoding="utf-8"))["state"] == "failed"

    def test_load_stage_logs_filters_codex_banner_noise(self, tmp_workspace: Path):
        cfg = mc.WorkflowConfig(
            max_cycles=1,
            artifacts_dir=tmp_workspace / "runs",
            task_prompt_file=tmp_workspace / "inputs" / "task_prompt.txt",
            evaluation_prompt_file=tmp_workspace / "inputs" / "evaluation_prompt.txt",
            agents={"codex": mc.AgentConfig(
                name="codex",
                command=["echo", "hi"],
                input_mode="stdin",
                timeout_sec=10,
            )},
            stages={
                name: mc.StageConfig(
                    name=name,
                    agent="codex",
                    template_file=tmp_workspace / "prompts" / "stages" / f"{name}.txt",
                )
                for name in mc.REQUIRED_STAGES
            },
        )

        run_dir = tmp_workspace / "runs" / "20260312-logs"
        stage_dir = run_dir / "cycle-01" / "02-plan"
        stage_dir.mkdir(parents=True)
        summary = {
            "started_at": "2020-01-01T00:00:00",
            "cycles": [{
                "cycle": 1,
                "attempt": 1,
                "stages": {"plan": mc.STATUS_COMPLETED},
                "issues": [],
                "elapsed_sec": 1.2,
            }],
            "completed": False,
            "failure": None,
            "history_loaded": False,
            "workspace": None,
        }
        progress = mc.init_progress(1)
        progress[1]["plan"] = mc.STATUS_COMPLETED
        mc.write_status_files(
            config=cfg,
            run_dir=run_dir,
            summary=summary,
            progress=progress,
            state="incomplete",
            active_cycle=None,
            active_stage=None,
        )
        (stage_dir / "stderr.txt").write_text(
            "OpenAI Codex v0.114.0 (research preview)\n"
            "--------\n"
            "workdir: /tmp/work\n"
            "model: gpt-5.4\n"
            "user\n"
            "STAGE: plan\n"
            "Prompt body\n"
            "mcp startup: no servers\n"
            "real stderr line\n"
            "2026-03-11T00:00:00Z  WARN codex_core::shell_snapshot: noisy cleanup\n"
        )
        (stage_dir / "combined.log").write_text(
            "[stderr] OpenAI Codex v0.114.0 (research preview)\n"
            "[stderr] --------\n"
            "[stderr] workdir: /tmp/work\n"
            "[stderr] user\n"
            "[stderr] STAGE: plan\n"
            "[stderr] Prompt body\n"
            "[stderr] mcp startup: no servers\n"
            "[stderr] real stderr line\n"
            "[stdout] useful stdout line\n"
        )

        logs = dash.load_stage_logs(cfg, run_dir.name, 1, "plan")
        detail = dash.load_stage_detail(cfg, run_dir.name, 1, "plan")

        assert "OpenAI Codex" not in logs["streams"]["stderr"]["text"]
        assert "Prompt body" not in logs["streams"]["stderr"]["text"]
        assert "real stderr line" in logs["streams"]["stderr"]["text"]
        assert "[stdout] useful stdout line" in logs["streams"]["combined"]["text"]
        assert "Prompt body" not in logs["streams"]["combined"]["text"]
        assert detail["content"]["stderr"].strip() == "real stderr line"

    def test_load_stage_logs_pretty_formats_codex_json_events(self, tmp_workspace: Path):
        cfg = mc.WorkflowConfig(
            max_cycles=1,
            artifacts_dir=tmp_workspace / "runs",
            task_prompt_file=tmp_workspace / "inputs" / "task_prompt.txt",
            evaluation_prompt_file=tmp_workspace / "inputs" / "evaluation_prompt.txt",
            agents={"codex": mc.AgentConfig(
                name="codex",
                command=["echo", "hi"],
                input_mode="stdin",
                timeout_sec=10,
            )},
            stages={
                name: mc.StageConfig(
                    name=name,
                    agent="codex",
                    template_file=tmp_workspace / "prompts" / "stages" / f"{name}.txt",
                )
                for name in mc.REQUIRED_STAGES
            },
        )

        run_dir = tmp_workspace / "runs" / "20260312-json-logs"
        stage_dir = run_dir / "cycle-01" / "02-plan"
        stage_dir.mkdir(parents=True)
        summary = {
            "started_at": "2020-01-01T00:00:00",
            "cycles": [{
                "cycle": 1,
                "attempt": 1,
                "stages": {"plan": mc.STATUS_RUNNING},
                "issues": [],
                "elapsed_sec": 2.0,
            }],
            "completed": False,
            "failure": None,
            "history_loaded": False,
            "workspace": None,
        }
        progress = mc.init_progress(1)
        progress[1]["plan"] = mc.STATUS_RUNNING
        mc.write_status_files(
            config=cfg,
            run_dir=run_dir,
            summary=summary,
            progress=progress,
            state="running",
            active_cycle=1,
            active_stage="plan",
        )
        (stage_dir / "stdout.txt").write_text(
            '{"type":"thread.started","thread_id":"thread-123"}\n'
            '{"type":"item.started","item":{"type":"command_execution","command":"echo hi","status":"in_progress"}}\n'
            '{"type":"item.completed","item":{"type":"command_execution","command":"echo hi","status":"completed","exit_code":0,"aggregated_output":"hi"}}\n'
            '{"type":"item.completed","item":{"type":"agent_message","text":"Discovery complete."}}\n'
            '{"type":"turn.completed","usage":{"input_tokens":11,"output_tokens":7,"total_tokens":18}}\n',
            encoding="utf-8",
        )
        (stage_dir / "combined.log").write_text(
            '[stdout] {"type":"thread.started","thread_id":"thread-123"}\n'
            '[stdout] {"type":"item.started","item":{"type":"command_execution","command":"echo hi","status":"in_progress"}}\n'
            '[stdout] {"type":"item.completed","item":{"type":"command_execution","command":"echo hi","status":"completed","exit_code":0,"aggregated_output":"hi"}}\n',
            encoding="utf-8",
        )

        logs = dash.load_stage_logs(cfg, run_dir.name, 1, "plan")
        detail = dash.load_stage_detail(cfg, run_dir.name, 1, "plan")

        assert "thread started: thread-123" in logs["streams"]["stdout"]["text"]
        assert "command started: echo hi" in logs["streams"]["stdout"]["text"]
        assert "command completed (exit 0): echo hi" in logs["streams"]["stdout"]["text"]
        assert "Discovery complete." in logs["streams"]["stdout"]["text"]
        assert "turn completed | tokens in 11 out 7 total 18" in logs["streams"]["stdout"]["text"]
        assert "[stdout] thread started: thread-123" in logs["streams"]["combined"]["text"]
        assert detail["content"]["primary_output"].startswith("thread started: thread-123")

    def test_pending_stage_detail_returns_empty_payload(self, tmp_workspace: Path):
        cfg = mc.WorkflowConfig(
            max_cycles=1,
            artifacts_dir=tmp_workspace / "runs",
            task_prompt_file=tmp_workspace / "inputs" / "task_prompt.txt",
            evaluation_prompt_file=tmp_workspace / "inputs" / "evaluation_prompt.txt",
            agents={"mock": mc.AgentConfig(
                name="mock",
                command=["false"],
                input_mode="stdin",
                timeout_sec=1,
            )},
            stages={
                name: mc.StageConfig(
                    name=name,
                    agent="mock",
                    template_file=tmp_workspace / "prompts" / "stages" / f"{name}.txt",
                )
                for name in mc.REQUIRED_STAGES
            },
        )

        status = dash.build_idle_run_detail(cfg)
        assert status["state"] == "idle"


# ---------------------------------------------------------------------------
# parse_args
# ---------------------------------------------------------------------------

class TestParseArgs:
    def test_defaults(self):
        with mock.patch("sys.argv", ["maker_checker.py"]):
            args = mc.parse_args()
            assert args.command == "run"
            assert args.config == mc.DEFAULT_CONFIG_FILE
            assert args.task_file is None
            assert args.max_cycles is None
            assert args.dashboard is True

    def test_old_style_run_flags_still_work(self):
        with mock.patch("sys.argv", [
            "maker_checker.py",
            "--config", "other.toml",
            "--task-file", "t.txt",
            "--max-cycles", "7",
            "--history-limit", "5",
            "--run-name", "test",
        ]):
            args = mc.parse_args()
            assert args.command == "run"
            assert args.config == "other.toml"
            assert args.task_file == "t.txt"
            assert args.max_cycles == 7
            assert args.history_limit == 5
            assert args.run_name == "test"

    def test_init_subcommand(self):
        with mock.patch("sys.argv", ["maker_checker.py", "init", "/tmp/work"]):
            args = mc.parse_args()
            assert args.command == "init"
            assert args.directory == "/tmp/work"

    def test_dashboard_subcommand(self):
        with mock.patch("sys.argv", ["maker_checker.py", "dashboard", "--port", "9999"]):
            args = mc.parse_args()
            assert args.command == "dashboard"
            assert args.port == 9999


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------

class TestMain:
    def test_missing_config_returns_1(self):
        with mock.patch("sys.argv", ["maker_checker.py", "--config", "/nonexistent.toml"]):
            assert mc.main() == 1

    def test_negative_max_cycles_returns_1(self, minimal_config_toml: Path):
        with mock.patch("sys.argv", [
            "maker_checker.py",
            "--config", str(minimal_config_toml),
            "--max-cycles", "-1",
        ]):
            assert mc.main() == 1

    def test_zero_max_cycles_returns_1(self, minimal_config_toml: Path):
        with mock.patch("sys.argv", [
            "maker_checker.py",
            "--config", str(minimal_config_toml),
            "--max-cycles", "0",
        ]):
            assert mc.main() == 1

    def test_zero_history_limit_returns_1(self, minimal_config_toml: Path):
        with mock.patch("sys.argv", [
            "maker_checker.py",
            "--config", str(minimal_config_toml),
            "--history-limit", "0",
        ]):
            assert mc.main() == 1

    def test_run_starts_dashboard_by_default(self, minimal_config_toml: Path):
        server = mock.Mock()
        with mock.patch("maker_checker_app.cli.run_workflow") as run_workflow_mock, mock.patch(
            "maker_checker_app.cli.start_server_in_background",
            return_value=(server, mock.Mock()),
        ) as start_dashboard_mock:
            with mock.patch("sys.argv", [
                "maker_checker.py",
                "--config", str(minimal_config_toml),
            ]):
                assert mc.main() == 0

        start_dashboard_mock.assert_called_once()
        run_workflow_mock.assert_called_once()
        server.shutdown.assert_called_once()
        server.server_close.assert_called_once()

    def test_run_can_disable_dashboard(self, minimal_config_toml: Path):
        with mock.patch("maker_checker_app.cli.run_workflow") as run_workflow_mock, mock.patch(
            "maker_checker_app.cli.start_server_in_background",
        ) as start_dashboard_mock:
            with mock.patch("sys.argv", [
                "maker_checker.py",
                "--config", str(minimal_config_toml),
                "--no-dashboard",
            ]):
                assert mc.main() == 0

        start_dashboard_mock.assert_not_called()
        run_workflow_mock.assert_called_once()

    def test_init_command_creates_hidden_workspace(self, tmp_path: Path):
        with mock.patch("sys.argv", ["maker_checker.py", "init", str(tmp_path)]):
            assert mc.main() == 0
        assert (tmp_path / ".maker-checker" / "config.toml").exists()


class TestDefaultTemplates:
    def test_plan_template_includes_evaluation_brief(self):
        text = mc.default_stage_template_path("plan").read_text(encoding="utf-8")
        assert "## Evaluation Brief" in text
        assert "{evaluation_prompt}" in text

    def test_execute_template_includes_evaluation_brief(self):
        text = mc.default_stage_template_path("execute").read_text(encoding="utf-8")
        assert "## Evaluation Brief" in text
        assert "{evaluation_prompt}" in text


class TestHistoryContext:
    def test_render_history_context_is_compact(self):
        entries = [
            {
                "run_id": "run-1",
                "outcome": "failed",
                "issue_trend": "3 -> 2",
                "improvements": ["Resolved one flaky test."],
                "failures": ["Long failure detail that should not become a multi-bullet dump in prompt memory."],
                "next_run_notes": ["Tighten the brief around invalid input handling before retrying."],
                "task_excerpt": "should be ignored",
                "evaluation_excerpt": "should be ignored",
            },
            {
                "run_id": "run-2",
                "outcome": "completed",
                "issue_trend": "1 -> 0",
                "improvements": ["Run finished cleanly."],
                "failures": [],
                "next_run_notes": ["Reuse this prompt structure; the run converged successfully."],
            },
        ]

        rendered = mc.render_history_context(entries, limit=2)

        assert rendered.count("### ") == 2
        assert "- Outcome: failed; Issue trend: 3 -> 2" in rendered
        assert "- Carry forward: Tighten the brief around invalid input handling before retrying." in rendered
        assert "task_excerpt" not in rendered
        assert "evaluation_excerpt" not in rendered
        assert "Improved:" not in rendered
        assert "Failed:" not in rendered

    def test_build_history_entry_omits_brief_excerpts(self, tmp_path: Path):
        run_dir = tmp_path / "run-1"
        run_dir.mkdir()
        summary = {
            "completed": True,
            "cycles": [
                {
                    "cycle": 1,
                    "issues": ["missing test"],
                },
                {
                    "cycle": 2,
                    "issues": [],
                },
            ],
            "ended_at": "2026-03-11T22:00:00",
        }

        entry = mc.build_history_entry(run_dir, summary)

        assert "task_excerpt" not in entry
        assert "evaluation_excerpt" not in entry
        assert entry["next_run_notes"] == ["Reuse this prompt structure; the run converged successfully."]


class TestBootstrapWorkspace:
    def test_init_workspace_creates_files(self, tmp_path: Path):
        created = bootstrap.init_workspace(tmp_path)
        workspace_dir = tmp_path / ".maker-checker"
        assert (workspace_dir / "config.toml").exists()
        assert (workspace_dir / "briefs" / "task.md").exists()
        assert (workspace_dir / "briefs" / "evaluation.md").exists()
        assert (workspace_dir / "templates" / "stages" / "plan.md").exists()
        assert (workspace_dir / "runs").exists()
        assert (workspace_dir / "memory").exists()
        assert len(created) == 3 + len(mc.REQUIRED_STAGES)
        config_text = (workspace_dir / "config.toml").read_text()
        assert '[git]' in config_text
        assert 'mode = "worktree"' in config_text
        assert 'worktrees_dir = "worktrees"' in config_text
        assert '[stages.execute]\nagent = "codex"' in config_text
        assert '[stages.execute]\nagent = "codex"\ntemplate_file = "templates/stages/execute.md"\ntimeout_sec = 1200' in config_text
        assert '[stages.verify]\nagent = "codex"\ntemplate_file = "templates/stages/verify.md"\ntimeout_sec = 1800' in config_text
        assert 'template_file = "templates/stages/plan.md"' in config_text
        assert "history_limit = 2" in config_text
        assert '"--json"' in config_text
        assert 'model_reasoning_effort=\\"high\\"' in config_text

    def test_init_workspace_refuses_to_overwrite_without_force(self, tmp_path: Path):
        bootstrap.init_workspace(tmp_path)
        with pytest.raises(mc.WorkflowError, match="Refusing to overwrite existing files"):
            bootstrap.init_workspace(tmp_path)

    def test_bootstrap_main_returns_1_on_overwrite_conflict(self, tmp_path: Path):
        bootstrap.init_workspace(tmp_path)
        with mock.patch("sys.argv", ["maker-checker-init", str(tmp_path)]):
            assert bootstrap.main() == 1
