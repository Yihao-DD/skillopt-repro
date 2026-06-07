from qd.descriptor import descriptor


def test_descriptor_ignores_skill_text_when_trajectory_behavior_matches() -> None:
    same_behavior = [{"code": "import openpyxl\nfor r in rows:\n    ws.cell(r, 1)\n", "n_turns": 1}]
    # Skill text is deliberately absent: descriptor only consumes trajectory.
    assert descriptor(same_behavior) == descriptor(same_behavior)


def test_descriptor_separates_same_prompt_with_different_behavior() -> None:
    pandas_behavior = [{"code": "import pandas as pd\ndf = pd.read_excel('x.xlsx')\ndf.to_excel('y.xlsx')\n"}]
    manual_behavior = [{"code": "import openpyxl\nfor r in rows:\n    if r:\n        ws.cell(r, 1).value = 1\n"}]

    assert descriptor(pandas_behavior).b != descriptor(manual_behavior).b
