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


# Valid C++17 constant-expression operator combinations. These control
# whether nested templates and relational operators are parsed together.
_COMPOUND_EXPR_CASES = (
    "Value < 2 && Count < 3",
    "Value < 2 || Count < 3",
    "Value < Limit ? true : false",
    "(Value < 2) ? true : false",
    "N < (Limit + 1)",
    "N < (Limit << 1)",
    "Value < 2 && kCount < Limit",
    "Value < 2 || (kCount < Limit)",
    "Value < 2 && (Count < 3)",
    "Value < (2 + Count)",
    "Value < 2 && Count < 3 && N < Limit",
)


@pytest.mark.parametrize("expression", _COMPOUND_EXPR_CASES)
def test_compound_nttp_comparison_preserves_outer_parameter(expression):
    """Boolean, conditional and arithmetic operands must keep the second arg."""
    declaration = f"Foo<{expression}, std::vector<int>> value"
    actual = cpplint.SplitConstructorArguments(declaration + ", int code")
    assert actual == [declaration, " int code"], (expression, actual)


@pytest.mark.parametrize("compiler", ["g++", "clang++"])
def test_compound_nttp_expression_grid_compiles_cpp17(compiler):
    """Compile every compound-expression test in an independent C++17 TU."""
    compiler_path = shutil.which(compiler)
    if compiler_path is None:
        pytest.skip(f"{compiler} is unavailable")
    declarations = [
        "#include <vector>",
        "template<bool, class T> struct Foo {};",
        "constexpr int Value=1, Count=1, N=1, Limit=2, kCount=1;",
    ]
    for index, expression in enumerate(_COMPOUND_EXPR_CASES):
        declarations.append(
            f"struct ExpressionCase{index} {{ ExpressionCase{index}("
            f"Foo<{expression}, std::vector<int>> value, int code); }};"
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


# Named parameter forms accepted by C++17 compilers, but mishandled by
# the previous terminal-closer pattern which demanded whitespace+name.
_CVREF_NAMED_CASES = (
    "Foo<Value < 2, std::vector<int>> value",
    "const Foo<Value < 2, std::vector<int>>& value",
    "Foo<Value < 2, std::vector<int>> const& value",
    "Foo<Value < 2, std::vector<int>> const & value",
    "Foo<Value < 2, std::vector<int>>& value",
    "Foo<Value < 2, std::vector<int>>&& value",
    "Foo<Value < 2, std::vector<int>>* value",
    "Foo<Value < 2, std::vector<int>> *const value",
    "Foo<Value < 2, std::vector<int>>* const value",
    "Foo<Value < 2, std::vector<int>> volatile value",
    "Foo<Value < 2, std::vector<int>> const volatile& value",
    "Foo<Value < 2, std::vector<int>> const* value",
)

# Research recovery for unnamed template-typed constructor parameters:
# allow only a narrowly recognized, simple named next parameter.
_CVREF_UNNAMED_CASES = (
    "Foo<Value < 2, std::vector<int>>",
    "Foo<Value < 2, std::vector<int>> const&",
    "Foo<Value < 2, std::vector<int>>&",
    "Foo<Value < 2, std::vector<int>>*",
    "Foo<Value < 2, std::vector<int>> const*",
    "const Foo<Value < 2, std::vector<int>>&",
)


@pytest.mark.parametrize("declaration", _CVREF_NAMED_CASES)
def test_nttp_cvref_named_parameter_preserves_argument(declaration):
    """CV/ref/pointer parameter suffixes must not swallow the outer comma."""
    assert cpplint.SplitConstructorArguments(declaration + ", int code") == [
        declaration, " int code"
    ]


@pytest.mark.parametrize("declaration", _CVREF_UNNAMED_CASES)
def test_nttp_cvref_unnamed_parameter_preserves_argument(declaration):
    """Recover unnamed templates before a simple named next parameter."""
    assert cpplint.SplitConstructorArguments(declaration + ", int code") == [
        declaration, " int code"
    ]


@pytest.mark.parametrize("compiler", ["g++", "clang++"])
def test_nttp_cvref_named_and_unnamed_are_valid_cpp17(compiler):
    """Compiler oracle for all eighteen CV/ref/pointer declarations."""
    compiler_path = shutil.which(compiler)
    if compiler_path is None:
        pytest.skip(f"{compiler} is unavailable")
    declarations = [
        "#include <vector>",
        "template<bool, class T> struct Foo {};",
        "constexpr int Value=1;",
    ]
    for index, declaration in enumerate(
        _CVREF_NAMED_CASES + _CVREF_UNNAMED_CASES
    ):
        declarations.append(
            f"struct CvRefCase{index} {{ CvRefCase{index}("
            f"{declaration}, int code); }};"
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


# These compiler-accepted three-template-parameter declarations demonstrate
# why a blanket '>' followed by comma is not a safe terminal-closer rule.
# The first three must remain grouped; the last three expose an older
# limitation that this narrow unnamed-parameter change must not worsen.
_MULTI_TEMPLATE_SAFE_GUARDS = (
    "Outer<Value < 2, Inner<int>, Last<int>> value",
    "Outer<Value < 2, std::vector<int>, std::pair<int, int>> value",
    "Outer<Value < 2, Inner<int>, std::array<int, 2>> value",
)
_MULTI_TEMPLATE_EXISTING_LIMITATIONS = (
    "Outer<Value < 2, Inner<int>, Another> value",
    "Outer<Value < 2, Inner<int>, int> value",
    "Outer<Value < 2, Inner<Last<int>>, Another> value",
)


@pytest.mark.parametrize("declaration", _MULTI_TEMPLATE_SAFE_GUARDS)
def test_unnamed_recovery_does_not_split_inner_template_commas(declaration):
    """The inner nested-type comma is not a constructor argument delimiter."""
    assert cpplint.SplitConstructorArguments(declaration + ", int code") == [
        declaration, " int code"
    ]


@pytest.mark.xfail(
    strict=True,
    reason="Existing limitation: constant comparison plus non-nested final type argument",
)
@pytest.mark.parametrize("declaration", _MULTI_TEMPLATE_EXISTING_LIMITATIONS)
def test_multi_template_final_plain_type_known_limitation(declaration):
    """Track known multi-argument templates rather than imply a full C++ parser."""
    assert cpplint.SplitConstructorArguments(declaration + ", int code") == [
        declaration, " int code"
    ]


@pytest.mark.parametrize("compiler", ["g++", "clang++"])
def test_multi_template_comma_guard_compiles_as_cpp17(compiler):
    """Validate all six three-template-argument declarations with C++17."""
    compiler_path = shutil.which(compiler)
    if compiler_path is None:
        pytest.skip(f"{compiler} is unavailable")
    declarations = [
        "#include <array>",
        "#include <utility>",
        "#include <vector>",
        "constexpr int Value=1;",
        "using Another=int;",
        "template<class T> struct Inner {};",
        "template<class T> struct Last {};",
        "template<bool B, class T, class U> struct Outer {};",
    ]
    for index, declaration in enumerate(
        _MULTI_TEMPLATE_SAFE_GUARDS + _MULTI_TEMPLATE_EXISTING_LIMITATIONS
    ):
        declarations.append(
            f"struct MultiTypeCase{index} {{ MultiTypeCase{index}("
            f"{declaration}, int code); }};"
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
