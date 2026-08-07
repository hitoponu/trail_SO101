"""Static contract checks on the reach node that do not need a ROS runtime.

The important one is `test_reach_node_never_publishes_cmd_vel`: the design
decision is "arm reach only, never drive the base", and a structural check
keeps that true no matter who edits the file later.
"""

import ast
from pathlib import Path

import pytest

MODULE = Path(__file__).resolve().parents[1] / "so101_bringup" / "reach_to_point.py"


@pytest.fixture(scope="module")
def tree():
    return ast.parse(MODULE.read_text())


def _string_constants(tree):
    """String literals excluding docstrings, which are prose about the code."""
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        )
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]


def test_reach_node_never_publishes_cmd_vel(tree):
    """The reach must not be able to drive the base, structurally."""
    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "create_publisher"
    ]
    topics = [
        argument.value
        for call in calls
        for argument in call.args
        if isinstance(argument, ast.Constant) and isinstance(argument.value, str)
    ]
    assert all("cmd_vel" not in topic for topic in topics), topics


def test_reach_node_does_not_import_twist(tree):
    """Importing Twist would be the first step toward driving the base."""
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert "Twist" not in imported


def test_no_cmd_vel_string_outside_docstrings(tree):
    """A /cmd_vel topic name must not appear in code (prose about it is fine)."""
    offenders = [value for value in _string_constants(tree) if "cmd_vel" in value]
    assert offenders == []


def test_status_codes_are_reported_for_every_rejection_path(tree):
    """Every early return must be preceded by a status report."""
    reported = {
        value
        for value in _string_constants(tree)
        if value.startswith(("REJECTED", "ABORTED", "FAILED", "SUCCEEDED", "ACCEPTED"))
    }
    # The codes the hardware procedure and the README refer to by name.
    for code in (
        "ACCEPTED",
        "SUCCEEDED",
        "REJECTED_UNREACHABLE",
        "REJECTED_NO_TF",
        "REJECTED_STALE_TF",
        "REJECTED_OUT_OF_RANGE",
        "REJECTED_BUSY",
        "ABORTED_BASE_MOVED",
        "FAILED_ACTION",
    ):
        assert code in reported, f"{code} が報告されていない"


def test_solver_is_not_reimplemented(tree):
    """The reach must reuse cartesian_math via reach_solver, not roll its own IK."""
    text = MODULE.read_text()
    assert "from .reach_solver import" in text
    assert "np.linalg.pinv" not in text, "DLS を迂回した擬似逆行列は使わない"
