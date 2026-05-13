"""Bit-layout interop tests across Python and Cairo.

The interop guarantee per `docs/spec/07-testing-strategy.md` §"F-9" is that
the Python and Cairo serialisers produce *byte-identical* output for the same
gate-list input, and that both sides decode the same 256-bit state from the
same `x_hex` bytes.

This module exercises three layers of the agreement:

1. **The same expected byte sequence is pinned on both sides.** A meta-test
   reads the Cairo source for `serialise_four_gate_regression_vector` and
   the Python `test_regression_vector_four_gates`, extracts the byte
   assertions from each, and asserts the two are byte-equal.

2. **Cairo's test suite still passes.** A pytest invokes
   `scarb cairo-test --filter serialise` and asserts the runner exits 0.
   If Cairo's serialiser drifts away from Python's expected vector, this
   test catches it on the Python side too.

3. **Python serialiser produces the same bytes the Cairo test pins.** The
   Python `grover_tax.serialise.serialise()` call on the canonical 4-gate
   vector emits the exact byte sequence both sides agree on.

The Rust side has only stub binaries today (#19); the third-party agreement
extends once SP1's witness-construction code lands (#25..#27).
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

from grover_tax.paths import repo_root
from grover_tax.serialise import UNUSED_CTRL, Gate, Opcode, serialise

CAIRO_SERIALISE_TEST = (
    repo_root() / "stwo-side" / "cairo" / "src" / "serialise.cairo"
)
CAIRO_DIR = repo_root() / "stwo-side" / "cairo"


def _canonical_four_gate_list() -> list[Gate]:
    """The 4-gate vector both serialisers agree on."""
    return [
        Gate(opcode=Opcode.NOT, target=0, ctrl_a=UNUSED_CTRL, ctrl_b=UNUSED_CTRL),
        Gate(opcode=Opcode.CNOT, target=1, ctrl_a=0, ctrl_b=UNUSED_CTRL),
        Gate(opcode=Opcode.TOFFOLI, target=2, ctrl_a=0, ctrl_b=1),
        Gate(opcode=Opcode.NOP, target=UNUSED_CTRL, ctrl_a=UNUSED_CTRL, ctrl_b=UNUSED_CTRL),
    ]


def _canonical_expected_bytes() -> bytes:
    """The exact 40-byte expected output, pinned identically on both sides."""
    return (
        b"GTV1"                                   # magic
        + b"\x04\x00\x00\x00"                     # n_gates = 4 (LE)
        + b"\x01\x00\x00\x00\xff\xff\xff\xff"     # NOT t=0 a=NO b=NO
        + b"\x02\x00\x01\x00\x00\x00\xff\xff"     # CNOT t=1 a=0 b=NO
        + b"\x03\x00\x02\x00\x00\x00\x01\x00"     # TOFFOLI t=2 a=0 b=1
        + b"\x00\x00\xff\xff\xff\xff\xff\xff"     # NOP t=NO a=NO b=NO
    )


def test_python_serialise_matches_canonical_bytes() -> None:
    """Python's `serialise()` of the 4-gate vector matches the agreed bytes."""
    actual = serialise(_canonical_four_gate_list())
    assert actual == _canonical_expected_bytes()


def _extract_cairo_byte_asserts(source: Path, test_name: str) -> list[tuple[int, int]]:
    """Scan a Cairo `.cairo` file for `bytes.at(N) == VALUE` assertions
    *inside* the body of the test function named `test_name`. Returns
    `(index, expected_byte_value)` tuples.

    VALUE can be a char-literal `'X'`, a `0x..` hex, or a decimal `N_u8`.
    The function only parses the fully-resolved decimal / hex / char
    forms; symbolic expressions are silently skipped, so a refactor that
    introduces named constants will surface as a *missing* assertion in
    `test_cairo_regression_test_pins_same_bytes_as_python` (the
    completeness check there hard-fails on any unpinned byte index).
    """
    text = source.read_text(encoding="utf-8")
    body = _locate_test_body(text, test_name)
    if body is None:
        raise AssertionError(
            f"could not locate Cairo test function `fn {test_name}` in {source}"
        )

    found: list[tuple[int, int]] = []
    pattern = re.compile(
        r"\*bytes\.at\((\d+)\)\s*==\s*(.+?)\s*\)",
        re.DOTALL,
    )
    for match in pattern.finditer(body):
        idx = int(match.group(1))
        raw_value = match.group(2).strip()
        value = _parse_cairo_byte_literal(raw_value)
        if value is None:
            continue
        found.append((idx, value))
    return found


def _locate_test_body(text: str, test_name: str) -> str | None:
    """Return the body of `fn <test_name>(...) { ... }`, or None if not found.

    Naive brace-balanced extraction — sufficient for our Cairo source, which
    doesn't embed nested function definitions inside test bodies.
    """
    marker = f"fn {test_name}"
    start = text.find(marker)
    if start == -1:
        return None
    brace_start = text.find("{", start)
    if brace_start == -1:
        return None
    depth = 1
    i = brace_start + 1
    while i < len(text):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[brace_start + 1 : i]
        i += 1
    return None


def _parse_cairo_byte_literal(raw: str) -> int | None:
    """Parse `'X'`, `0xNN_u8`, `0xNN`, `N_u8`, or `N` into an int.

    Returns `None` for any other shape; the caller treats those as
    non-byte-assertion matches and skips them.
    """
    raw = raw.strip().rstrip(",")
    # char literal
    if len(raw) == 3 and raw.startswith("'") and raw.endswith("'"):
        return ord(raw[1])
    # strip _u8 suffix
    if raw.endswith("_u8"):
        raw = raw[: -3]
    elif raw.endswith("u8"):
        raw = raw[: -2]
    raw = raw.strip()
    try:
        if raw.startswith(("0x", "0X")):
            return int(raw, 16)
        return int(raw, 10)
    except ValueError:
        return None


def test_cairo_regression_test_pins_same_bytes_as_python() -> None:
    """The byte assertions in Cairo's `serialise_four_gate_regression_vector`
    match Python's `_canonical_expected_bytes()` byte-for-byte.

    This is the load-bearing cross-impl interop guarantee for the gate-list
    serialiser: if either side ever drifts on the same input, this test
    surfaces the disagreement immediately.
    """
    asserts = _extract_cairo_byte_asserts(
        CAIRO_SERIALISE_TEST,
        test_name="serialise_four_gate_regression_vector",
    )
    expected = _canonical_expected_bytes()
    # The Cairo test asserts at least one byte per offset 0..39 in the
    # regression vector. (Some offsets may appear in multiple test functions
    # of the same file; we deduplicate by index.)
    pinned_indexes = {idx for idx, _ in asserts}
    for i in range(len(expected)):
        assert i in pinned_indexes, (
            f"Cairo test does not pin byte index {i} of the regression vector"
        )
    # Each pinned index must agree with Python's expected byte.
    for idx, cairo_byte in asserts:
        if idx < len(expected):
            py_byte = expected[idx]
            assert cairo_byte == py_byte, (
                f"interop drift at byte {idx}: Cairo pins {cairo_byte:#04x}, "
                f"Python expects {py_byte:#04x}"
            )


@pytest.mark.skipif(shutil.which("scarb") is None, reason="scarb not installed")
def test_scarb_cairo_test_serialise_passes() -> None:
    """End-to-end: `scarb cairo-test` for the serialise module exits 0.

    If Cairo's serialiser stops producing the agreed byte sequence — either
    because the implementation drifted *or* because the pinned expected
    constants drifted — the Cairo test fails and this Python test catches
    it.
    """
    result = subprocess.run(
        [
            "scarb",
            "--manifest-path",
            str(CAIRO_DIR / "Scarb.toml"),
            "cairo-test",
            "--filter",
            "serialise",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"scarb cairo-test --filter serialise failed:\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    # Sanity-check the runner output names at least the four-gate regression
    # test — if the filter ever stops matching, this would silently green-light.
    assert "serialise_four_gate_regression_vector" in result.stdout


@pytest.mark.skipif(shutil.which("scarb") is None, reason="scarb not installed")
def test_scarb_cairo_test_c_t_suite_passes() -> None:
    """`scarb cairo-test --filter c_t4` runs the suite-level C-T4
    canonical-serialisation regression. Same agreement, named at the
    spec layer."""
    result = subprocess.run(
        [
            "scarb",
            "--manifest-path",
            str(CAIRO_DIR / "Scarb.toml"),
            "cairo-test",
            "--filter",
            "c_t4",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, (
        f"scarb cairo-test --filter c_t4 failed:\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    assert "c_t4_canonical_serialisation_regression" in result.stdout


def test_python_bit_layout_decodes_canonical_x_hex() -> None:
    """The Python BitVector decode of a known 32-byte `x_hex` chunk matches
    the bit-by-bit expectation from `docs/spec/03-data-model.md` §"Fixture":

      bit `i` lives at byte `i // 8`, bit-position `i % 8`, LSB-first.

    The Cairo `State` uses a different *internal* representation (limbs
    of 31 bits) but exposes the same logical bit-`i` semantics via
    `get_bit(s, i)` — this is the cross-impl property the spec pins.
    """
    from grover_tax.sim_reference import BitVector
    # Known input: a byte string where bit 0 is 1, bit 9 is 1, bit 255 is 1.
    raw = bytearray(32)
    raw[0] = 0b00000001
    raw[1] = 0b00000010
    raw[31] = 0b10000000
    bv = BitVector(bytes(raw))
    assert bv.get(0) == 1
    assert bv.get(9) == 1
    assert bv.get(255) == 1
    # All other bits are 0.
    for i in range(256):
        if i not in {0, 9, 255}:
            assert bv.get(i) == 0


def test_canonical_byte_sequence_is_forty_bytes() -> None:
    """8-byte header plus 4 gates at 8 bytes each = 40 bytes. Pinned on both sides."""
    assert len(_canonical_expected_bytes()) == 40
