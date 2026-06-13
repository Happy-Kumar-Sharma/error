"""Smart repr policies for large objects appearing in local variables.

Produces compact, informative summaries for numpy arrays, pandas frames,
torch/tensorflow tensors (detected via duck-typing -- the libraries are
never imported here) and oversized builtin collections, while leaving
short plain values rendered exactly as ``repr()`` would.
"""
from itertools import islice
from typing import Any

# Collections larger than this are summarized without computing their full
# repr (anything above this size is guaranteed to exceed the default
# 200-char truncation anyway, so behavior matches "repr too long").
_BIG_COLLECTION_LEN = 100
_PREVIEW_ITEMS = 3
_PREVIEW_ITEM_LEN = 24
_ARRAY_PREVIEW_LEN = 60

# Module prefixes that identify tensor-like objects we summarize by
# shape/dtype instead of dumping their values.
_TENSOR_MODULE_ROOTS = ("torch", "tensorflow", "tf", "jax", "jaxlib", "keras")


def _truncate(text: str, max_len: int) -> str:
    """Truncates text to max_len characters, appending an ellipsis."""
    if len(text) > max_len:
        return text[: max(max_len - 3, 1)] + "..."
    return text


def _safe_shape(value: Any) -> str:
    """Renders a .shape attribute as a plain tuple string, best-effort."""
    shape = getattr(value, "shape", None)
    try:
        return str(tuple(shape))
    except Exception:
        return str(shape)


def _preview_sequence(value: Any) -> str:
    """Builds a short preview of the first few items of an iterable."""
    parts = []
    for item in islice(iter(value), _PREVIEW_ITEMS):
        try:
            parts.append(_truncate(repr(item), _PREVIEW_ITEM_LEN))
        except Exception:
            parts.append("<?>")
    return ", ".join(parts)


def _preview_mapping(value: Any) -> str:
    """Builds a short preview of the first few key/value pairs of a dict."""
    parts = []
    for k, v in islice(value.items(), _PREVIEW_ITEMS):
        try:
            parts.append(
                "{}: {}".format(
                    _truncate(repr(k), _PREVIEW_ITEM_LEN),
                    _truncate(repr(v), _PREVIEW_ITEM_LEN),
                )
            )
        except Exception:
            parts.append("<?>")
    return ", ".join(parts)


def _smart_repr_inner(value: Any, max_len: int) -> str:
    module = getattr(type(value), "__module__", "") or ""
    module_root = module.split(".")[0]
    type_name = getattr(type(value), "__name__", "object")

    # --- numpy arrays: shape + dtype + tiny value preview -----------------
    if module_root == "numpy":
        shape = getattr(value, "shape", None)
        dtype = getattr(value, "dtype", None)
        if shape is not None and dtype is not None:
            try:
                preview = " ".join(str(value).split())
            except Exception:
                preview = "..."
            return "{} shape={} dtype={} {}".format(
                type_name, _safe_shape(value), dtype, _truncate(preview, _ARRAY_PREVIEW_LEN)
            )

    # --- pandas DataFrame / Series ----------------------------------------
    if module_root == "pandas":
        shape = getattr(value, "shape", None)
        columns = getattr(value, "columns", None)
        if columns is not None and shape is not None and len(shape) == 2:
            col_names = [str(c) for c in islice(iter(columns), 5)]
            try:
                more = ", ..." if shape[1] > len(col_names) else ""
            except Exception:
                more = ""
            return "{} {}x{} cols=[{}{}]".format(
                type_name, shape[0], shape[1], ", ".join(col_names), more
            )
        if shape is not None and len(shape) == 1:
            dtype = getattr(value, "dtype", "?")
            return "{} len={} dtype={}".format(type_name, shape[0], dtype)

    # --- torch / tensorflow / jax tensors: never dump values --------------
    if module_root in _TENSOR_MODULE_ROOTS:
        shape = getattr(value, "shape", None)
        if shape is not None:
            dtype = getattr(value, "dtype", "?")
            return "{} shape={} dtype={}".format(type_name, _safe_shape(value), dtype)

    # --- big builtin collections -------------------------------------------
    if isinstance(value, (list, tuple, set, frozenset)):
        n = len(value)
        if n <= _BIG_COLLECTION_LEN:
            full = repr(value)
            if len(full) <= max_len:
                return full
        opener, closer = "[", "]"
        if isinstance(value, tuple):
            opener, closer = "(", ")"
        elif isinstance(value, (set, frozenset)):
            opener, closer = "{", "}"
        return "{} len={} {}{}, ...{}".format(
            type_name, n, opener, _preview_sequence(value), closer
        )

    if isinstance(value, dict):
        n = len(value)
        if n <= _BIG_COLLECTION_LEN:
            full = repr(value)
            if len(full) <= max_len:
                return full
        return "{} len={} {{{}, ...}}".format(type_name, n, _preview_mapping(value))

    # --- bytes / bytearray ---------------------------------------------------
    if isinstance(value, (bytes, bytearray)):
        full = repr(value)
        if len(full) <= max_len:
            return full
        head = repr(bytes(value[:16]))
        return "{} len={} {}...".format(type_name, len(value), head)

    # --- everything else: plain repr, truncated -------------------------------
    return _truncate(repr(value), max_len)


def smart_repr(value: Any, max_len: int = 200) -> str:
    """Returns a compact, informative repr of any value. Never raises."""
    try:
        return _smart_repr_inner(value, max_len)
    except Exception:
        try:
            return "<unrepresentable {}>".format(type(value).__name__)
        except Exception:
            return "<unrepresentable>"
