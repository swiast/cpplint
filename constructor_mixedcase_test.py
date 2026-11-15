"""Research-only constructor template comparison regressions.

These contain Python splitter checks and optional C++17 compiler validation.
"""

import itertools
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


# Research-only bounded differential stress checks, independently source-reviewed.
# These exercise the parser's top-level comma grouping; they do not establish
# exhaustive C++ grammar correctness.
_GRID_NAMES = ("Value", "kCount", "isEnabled", "Count", "N", "MAX_N", "threshold")
_GRID_RIGHTS = ("2", "Limit", "1", "MAX_N")
_GRID_TYPES = (
    "int",
    "long",
    "std::vector<int>",
    "std::pair<int, int>",
    "std::array<int, 2>",
    "std::vector<std::pair<int, int>>",
    "std::vector<std::vector<int>>",
)
_BALANCED_LEFT_TYPES = (
    "Bar<int>",
    "Bar<Bar<int>>",
    "Bar < int >",
    "Bar<std::vector<int>>",
    "std::pair<int,int>",
    "std::vector<std::array<int,2>>",
    "FooTwo<int, Bar<double>>",
    "Bar<Value>",
)
_BALANCED_RIGHT_TYPES = (
    "int",
    "std::vector<int>",
    "std::pair<int,int>",
    "std::vector<std::pair<int,int>>",
    "std::array<int, 2>",
)


def test_generated_nested_type_comparison_grid():
    """196 outer two-parameter comparisons must survive nested type closers."""
    for symbol, rhs, nested_type in itertools.product(
        _GRID_NAMES, _GRID_RIGHTS, _GRID_TYPES
    ):
        declaration = f"Foo<{symbol} < {rhs}, {nested_type}> value"
        actual = cpplint.SplitConstructorArguments(declaration + ", int code")
        assert actual == [declaration, " int code"], (
            f"{symbol=}, {rhs=}, {nested_type=}: {actual!r}"
        )


def test_generated_balanced_nested_template_controls():
    """Forty real template openers must not be mistaken for a comparison."""
    for left, right in itertools.product(_BALANCED_LEFT_TYPES, _BALANCED_RIGHT_TYPES):
        declaration = f"Outer<{left}, {right}> value"
        actual = cpplint.SplitConstructorArguments(declaration + ", int code")
        assert actual == [declaration, " int code"], (left, right, actual)


@pytest.mark.parametrize("compiler", ["g++", "clang++"])
def test_generated_nested_comparison_grid_compiles_cpp17(compiler):
    """Compile the same 196 unambiguous comparisons in one translation unit."""
    compiler_path = shutil.which(compiler)
    if compiler_path is None:
        pytest.skip(f"{compiler} is unavailable")
    declarations = [
        "#include <vector>",
        "#include <utility>",
        "#include <array>",
        "template<bool, class T> struct Foo {};",
        "constexpr int Value=1, kCount=1, isEnabled=1, Count=1;",
        "constexpr int N=1, MAX_N=2, threshold=1, Limit=2;",
    ]
    for index, (symbol, rhs, nested_type) in enumerate(
        itertools.product(_GRID_NAMES, _GRID_RIGHTS, _GRID_TYPES)
    ):
        declarations.append(
            f"struct Case{index} {{ Case{index}("
            f"Foo<{symbol} < {rhs}, {nested_type}> value, int code); }};"
        )
    result = subprocess.run(
        [compiler_path, "-std=c++17", "-x", "c++", "-fsyntax-only", "-"],
        input="\n".join(declarations) + "\n",
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
