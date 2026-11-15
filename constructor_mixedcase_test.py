"""Research-only constructor template comparison regressions.

These are Python-level splitter checks, not independent C++ compilation.
"""

import pytest

import cpplint


@pytest.mark.parametrize("symbol", ["Value", "kCount", "isEnabled", "Count"])
def test_mixed_case_constant_comparisons_preserve_required_arguments(symbol):
    """An identifier-led comparison must not swallow the outer parameter comma."""
    source = f"Foo<{symbol} < 2, int> value, int code"
    assert cpplint.SplitConstructorArguments(source) == [
        f"Foo<{symbol} < 2, int> value",
        " int code",
    ]


@pytest.mark.parametrize(
    "source",
    [
        "Foo<Bar<T>, int> value, int code",
        "Foo<Bar < T >, int> value, int code",
        "Foo<N<M, int>, int> value, int code",
        "Foo<N < 2, int> value, int code",
        "Foo<'a' < 'b', int> value, int code",
        "int code, Foo<T<U>, N<M> value",
    ],
)
def test_mixed_case_recovery_preserves_nested_template_controls(source):
    """Retain established nested-template and previously repaired scanner behavior."""
    if source.startswith("int code,"):
        expected = ["int code", " Foo<T<U>, N<M> value"]
    else:
        expected = [source.split(" value,")[0] + " value", " int code"]
    assert cpplint.SplitConstructorArguments(source) == expected
