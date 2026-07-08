import importlib.util
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[1]
    / "rpa-project-bootstrap"
    / "scripts"
    / "init_rpa_project.py"
)


def load_bootstrap_module():
    spec = importlib.util.spec_from_file_location("init_rpa_project", SCRIPT_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_copy_template_keeps_documented_examples(tmp_path):
    module = load_bootstrap_module()
    src = tmp_path / "template"
    dst = tmp_path / "target"
    examples = src / "docs" / "examples"
    examples.mkdir(parents=True)
    (examples / "input_calc_summary.json").write_text("{}", encoding="utf-8")
    (src / "input_runtime.json").write_text("{}", encoding="utf-8")
    (src / "input.json").write_text("{}", encoding="utf-8")
    (src / "runner_runtime.json").write_text("{}", encoding="utf-8")
    (src / "README.md").write_text("# 开发模板\n", encoding="utf-8")

    module.copy_template(src, dst)

    assert (dst / "docs" / "examples" / "input_calc_summary.json").exists()
    assert not (dst / "input_runtime.json").exists()
    assert not (dst / "input.json").exists()
    assert not (dst / "runner_runtime.json").exists()


def test_replace_project_name_preserves_canonical_repositories(tmp_path):
    module = load_bootstrap_module()
    readme = tmp_path / "README.md"
    readme.write_text(
        "\n".join(
            [
                "# RPA Python 开发模板",
                "https://github.com/redballoom/rpa-dev-template",
                "https://github.com/redballoom/rpa-dev-template-skills",
                "https://github.com/redballoom/rpa-dev-template/schemas/input.schema.json",
            ]
        ),
        encoding="utf-8",
    )

    changed = module.replace_project_name(tmp_path, "客户项目")
    text = readme.read_text(encoding="utf-8")

    assert changed == 1
    assert "# RPA Python 客户项目" in text
    assert "https://github.com/redballoom/rpa-dev-template" in text
    assert "https://github.com/redballoom/rpa-dev-template-skills" in text
    assert "https://github.com/redballoom/rpa-dev-template/schemas/input.schema.json" in text
    assert "客户项目-skills" not in text
