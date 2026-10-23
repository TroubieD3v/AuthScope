from pathlib import Path

import yaml

from authscope.cli import main
from authscope.config import ProjectConfig

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "demo.authscope.yaml"


def test_example_config_is_valid_and_matches_demo_builder():
    cfg = ProjectConfig.model_validate(yaml.safe_load(EXAMPLE.read_text(encoding="utf-8")))
    assert len(cfg.endpoints) == 12 and {i.name for i in cfg.identities} == {"guest", "alice", "bob", "carol", "admin"}
    assert cfg.identity("alice").token_env == "AUTHSCOPE_TOKEN_ALICE"
    assert cfg.identity("carol").login and cfg.identity("carol").password_env == "AUTHSCOPE_PASSWORD_CAROL"


def _config_for(url: str, tmp_path: Path) -> Path:
    data = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    data["target"]["base_url"] = url
    data["target"]["rate_limit_rps"] = 100
    path = tmp_path / "cfg.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def _tokens(monkeypatch):
    env = Path(__file__).resolve().parents[1] / "examples" / "demo.env"
    monkeypatch.delenv("AUTHSCOPE_TOKEN_CAROL", raising=False)
    for line in env.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#"):
            key, value = line.split("=", 1)
            monkeypatch.setenv(key, value)


def test_cli_exit_code_reflects_violations(demo_url, tmp_path, monkeypatch, capsys):
    _tokens(monkeypatch)
    cfg = _config_for(demo_url, tmp_path)
    out = tmp_path / "report.json"

    monkeypatch.delenv("DEMO_VULNS", raising=False)
    assert main(["run", "-c", str(cfg), "-f", "json", "-o", str(out), "-q"]) == 1
    report = out.read_text(encoding="utf-8")
    assert '"violation"' in report and '"identity": "carol"' in report and "carol-demo-pass" not in report

    monkeypatch.setenv("DEMO_VULNS", "")
    assert main(["run", "-c", str(cfg), "-f", "md", "-o", str(tmp_path / "ok.md"), "-m", "bola", "-q"]) == 0
    assert "No violations or review items" in (tmp_path / "ok.md").read_text(encoding="utf-8")


def test_cli_refuses_mutating_without_reset(tmp_path, monkeypatch):
    data = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
    data["target"].pop("reset")
    path = tmp_path / "noreset.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    assert main(["run", "-c", str(path), "--allow-mutating", "-q"]) == 2


def test_serve_refuses_public_bind():
    assert main(["serve", "--host", "0.0.0.0"]) == 2
