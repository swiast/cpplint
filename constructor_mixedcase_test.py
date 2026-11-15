"""Research-only constructor template comparison regressions.

These are Python-level splitter checks, not independent C++ compilation.
"""

import shutil
import subprocess

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


# Both C++17 compilers accept these unparenthesized constant-expression
# comparisons even when the second template argument is itself a template.
# RED on this research head: the closest-'>' recovery shortcut misses the
# final outer template closer and merges the constructor's two parameters.
_NESTED_SECOND_TYPE_CASES = (
    ("Value < 2", "std::vector<int>"),
    ("kCount < 2", "std::pair<int, int>"),
    ("N < Limit", "std::array<int, 2>"),
)


@pytest.mark.parametrize(("expression", "nested_type"), _NESTED_SECOND_TYPE_CASES)
def test_nested_second_template_type_with_relational_constant(expression, nested_type):
    """A comparison and nested second template type must retain two arguments."""
    declaration = f"Foo<{expression}, {nested_type}> value"
    assert cpplint.SplitConstructorArguments(declaration + ", int code") == [
        declaration,
        " int code",
    ]


@pytest.mark.parametrize("compiler", ["g++", "clang++"])
@pytest.mark.parametrize(("expression", "nested_type"), _NESTED_SECOND_TYPE_CASES)
def test_nested_second_type_comparison_compiles_as_cpp17(compiler, expression, nested_type):
    """Prove the new RED fixtures are valid under both C++17 frontends."""
    compiler_path = shutil.which(compiler)
    if compiler_path is None:
        pytest.skip(f"{compiler} is unavailable")
    source = (
        "#include <vector>\n"
        "#include <utility>\n"
        "#include <array>\n"
        "template<bool, class T> struct Foo {};\n"
        "constexpr int Value=1, kCount=1, N=1, Limit=2;\n"
        f"struct A {{ A(Foo<{expression}, {nested_type}> value, int code); }};\n"
    )
    result = subprocess.run(
        [compiler_path, "-std=c++17", "-x", "c++", "-fsyntax-only", "-"],
        input=source,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr


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


@pytest.mark.parametrize("compiler", ["g++", "clang++"])
@pytest.mark.parametrize("symbol", ["Value", "kCount", "isEnabled", "Count"])
def test_mixed_case_constexpr_expression_compiles(compiler, symbol):
    """Verify the regressions use syntactically valid C++17 constructors."""
    compiler_path = shutil.which(compiler)
    if compiler_path is None:
        pytest.skip(f"{compiler} is unavailable")
    source = (
        "template<bool, class T> struct Flag {};\n"
        f"constexpr int {symbol} = 1;\n"
        f"struct A {{ A(Flag<{symbol} < 2, int> value, int code); }};\n"
    )
    result = subprocess.run(
        [compiler_path, "-std=c++17", "-x", "c++", "-fsyntax-only", "-"],
        input=source,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
