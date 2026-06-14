#!/usr/bin/env python3
"""Zero-dependency tests for skill_lint. Run: python3 test_skill_lint.py"""
import os
import tempfile

import skill_lint as sl


def _write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def _codes(findings):
    return {f.code for f in findings}


def test_frontmatter_parsing():
    fm, body = sl.parse_frontmatter('---\nname: a\ndescription: "x: y"\n---\nbody\nmore\n')
    assert fm == {"name": "a", "description": "x: y"}, fm
    assert body == 2, body


def test_block_scalar_description():
    fm, _ = sl.parse_frontmatter('---\nname: a\ndescription: >-\n  one two\n  three\n---\n')
    assert fm["description"] == "one two three", fm


def test_no_frontmatter_is_error():
    with tempfile.TemporaryDirectory() as d:
        _write(os.path.join(d, "x.md"), "# no frontmatter here\n")
        res = sl.lint_skill(os.path.join(d, "x.md"), d,
                            sl.DEFAULT_MAX_DESC, sl.DEFAULT_MAX_BODY, [])
        assert "no-frontmatter" in _codes(res)


def test_clean_skill_has_no_findings():
    with tempfile.TemporaryDirectory() as d:
        _write(os.path.join(d, "good.md"),
               "---\nname: good\ndescription: A clear, trigger-oriented description of what this does.\n---\n# Good\nshort body\n")
        res = sl.lint_skill(os.path.join(d, "good.md"), d,
                            sl.DEFAULT_MAX_DESC, sl.DEFAULT_MAX_BODY, [])
        assert res == [], [f.as_dict() for f in res]


def test_long_description_and_name_mismatch():
    with tempfile.TemporaryDirectory() as d:
        _write(os.path.join(d, "x.md"),
               "---\nname: wrong\ndescription: " + ("z" * 400) + "\n---\nbody\n")
        res = sl.lint_skill(os.path.join(d, "x.md"), d,
                            sl.DEFAULT_MAX_DESC, sl.DEFAULT_MAX_BODY, [])
        assert "long-description" in _codes(res)
        assert "name-mismatch" in _codes(res)


def test_dead_reference():
    with tempfile.TemporaryDirectory() as d:
        _write(os.path.join(d, "x.md"),
               "---\nname: x\ndescription: ok description here for triggering reliably.\n---\nSee [ref](reference/missing.md)\n")
        res = sl.lint_skill(os.path.join(d, "x.md"), d,
                            sl.DEFAULT_MAX_DESC, sl.DEFAULT_MAX_BODY, [])
        assert "dead-reference" in _codes(res)


def test_stale_model_id():
    import re
    res_pat = [re.compile(p) for p in sl.STALE_MODEL_PATTERNS]
    with tempfile.TemporaryDirectory() as d:
        _write(os.path.join(d, "x.md"),
               "---\nname: x\ndescription: ok description here for triggering reliably.\n---\nuse claude-3-haiku-20240307\n")
        res = sl.lint_skill(os.path.join(d, "x.md"), d,
                            sl.DEFAULT_MAX_DESC, sl.DEFAULT_MAX_BODY, res_pat)
        assert "stale-model-id" in _codes(res)


def test_current_model_id_not_flagged():
    import re
    res_pat = [re.compile(p) for p in sl.STALE_MODEL_PATTERNS]
    with tempfile.TemporaryDirectory() as d:
        _write(os.path.join(d, "x.md"),
               "---\nname: x\ndescription: ok description here for triggering reliably.\n---\nuse claude-opus-4-8 and claude-sonnet-4-6 and claude-haiku-4-5\n")
        res = sl.lint_skill(os.path.join(d, "x.md"), d,
                            sl.DEFAULT_MAX_DESC, sl.DEFAULT_MAX_BODY, res_pat)
        assert "stale-model-id" not in _codes(res)


def test_find_skill_files_whitelist():
    with tempfile.TemporaryDirectory() as d:
        _write(os.path.join(d, "top.md"), "---\nname: top\ndescription: d\n---\n")
        _write(os.path.join(d, "dir", "SKILL.md"), "---\nname: dir\ndescription: d\n---\n")
        _write(os.path.join(d, "dir", "reference", "x.md"), "content")  # must be ignored
        _write(os.path.join(d, "README.md"), "# readme")               # must be ignored
        found = {sl.skill_label(p, d) for p in sl.find_skill_files(d)}
        assert found == {"top", "dir"}, found


def main():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  ok   {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
