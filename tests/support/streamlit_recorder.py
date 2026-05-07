"""Test doubles for Streamlit page assertions.

Extensions added for the ingestion page (``app/pages/3_📥_Ingestion.py``):

- ``columns(spec)`` returns a list of ``StreamlitContext`` instances so the
  page can do ``cols = st.columns(3); with cols[0]: ...``.  The page uses
  ``st.columns`` to render the legal-tag/ACL input row and the run-status
  metric row.
- ``status(label, expanded=...)`` returns a :class:`StreamlitStatusContext`
  that behaves as a context manager AND exposes ``update(label=, state=)``
  so the page's ``status_box.update(...)`` calls inside ``with status_box:``
  blocks are recorded.

Extensions added for the legal tags page (``app/pages/4_🏷️_Legal_Tags.py``):

- ``toggle(label, value=False, ...)`` returns the configured widget value
  (or ``value`` default) so the "Show only valid tags" toggle's bool flow
  is observable.
- ``selectbox(label, options, index=0, ...)`` returns the configured widget
  value or ``options[index]``; used both for the table-row selection and the
  create-form classification dropdowns.
- ``multiselect(label, options, default=None, ...)`` returns the configured
  widget value (list) or ``default``; used for country dropdowns.
- ``date_input(label, value=None, ...)`` returns the configured widget value
  or ``value``; used for the create-form expiration field.
- ``text_area(label, value="", ...)`` returns the configured widget value or
  ``value``; used for the description fields.

All five lookups consult ``self.widget_values[label]`` first, then fall back
to the page's supplied default. Existing tests keep working — these are
additive on top of the ``__getattr__`` no-op fallback.
"""

from __future__ import annotations

from collections.abc import Callable
from types import ModuleType
from typing import Any, Literal, NamedTuple


class StreamlitCall(NamedTuple):
    """Represent one recorded Streamlit API call."""

    name: str
    args: tuple[Any, ...]
    kwargs: dict[str, Any]


class StreamlitContext:
    """Simple context manager used for forms and spinners."""

    def __init__(
        self,
        recorder: StreamlitRecorder,
        name: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> None:
        self._recorder = recorder
        self._recorder.calls.append(
            StreamlitCall(name=name, args=args, kwargs=kwargs)
        )

    def __enter__(self) -> StreamlitRecorder:
        return self._recorder

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> Literal[False]:
        return False


class StreamlitStatusContext(StreamlitContext):
    """``st.status`` context manager with a recorded ``.update(...)``.

    The ingestion page's ``status_box.update(label=..., state=...)`` calls
    inside ``with status_box:`` get appended to the recorder under the
    name ``status_update`` AND tracked on the instance so a single test
    can assert "the final state was 'error'".
    """

    def __init__(
        self,
        recorder: StreamlitRecorder,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> None:
        super().__init__(recorder, "status", args, kwargs)
        self.updates: list[dict[str, Any]] = []

    def update(self, **kwargs: Any) -> None:
        """Record a status update without altering recorder semantics."""
        self.updates.append(kwargs)
        self._recorder.calls.append(
            StreamlitCall(name="status_update", args=(), kwargs=kwargs)
        )


class QueryParamsRecorder(dict[str, object]):
    """Record query-param clearing while behaving like Streamlit query params."""

    def __init__(self) -> None:
        super().__init__()
        self.clear_count = 0

    def clear(self) -> None:
        """Clear all query params and record that a clear happened."""
        self.clear_count += 1
        super().clear()


class StreamlitRecorder(ModuleType):
    """Record Streamlit API calls for page-level tests."""

    def __init__(self) -> None:
        super().__init__("streamlit")
        self.calls: list[StreamlitCall] = []
        self.session_state: dict[str, object] = {}
        self.query_params = QueryParamsRecorder()
        self.widget_values: dict[str, Any] = {}
        self.submit_responses: dict[str, bool] = {}
        self.button_responses: dict[str, bool] = {}

    def form(self, key: str, **kwargs: Any) -> StreamlitContext:
        """Return a context manager for a Streamlit form."""
        return StreamlitContext(self, "form", (key,), kwargs)

    def spinner(self, text: str, **kwargs: Any) -> StreamlitContext:
        """Return a context manager for a Streamlit spinner."""
        return StreamlitContext(self, "spinner", (text,), kwargs)

    def expander(self, label: str, **kwargs: Any) -> StreamlitContext:
        """Return a context manager for a Streamlit expander."""
        return StreamlitContext(self, "expander", (label,), kwargs)

    def columns(self, spec: int | list[int], **kwargs: Any) -> list[StreamlitContext]:
        """Return ``N`` context managers for ``with cols[i]:`` blocks.

        ``spec`` may be an int column count or a list of relative widths.
        Each returned context records its own ``column`` call when entered
        so we can still assert "the page rendered three columns" without
        coupling tests to the underlying widget order.
        """
        count = spec if isinstance(spec, int) else len(spec)
        self.calls.append(
            StreamlitCall(name="columns", args=(spec,), kwargs=kwargs)
        )
        return [
            StreamlitContext(self, "column", (index,), {})
            for index in range(count)
        ]

    def status(self, label: str, **kwargs: Any) -> StreamlitStatusContext:
        """Return a context manager that also exposes ``.update(...)``."""
        return StreamlitStatusContext(self, (label,), kwargs)

    def text_input(self, label: str, value: str = "", **kwargs: Any) -> str:
        """Record a text input and return the configured widget value."""
        self.calls.append(
            StreamlitCall(
                name="text_input",
                args=(label,),
                kwargs={"value": value, **kwargs},
            )
        )
        widget_value = self.widget_values.get(label, value)
        return str(widget_value)

    def radio(
        self,
        label: str,
        options: list[Any],
        index: int = 0,
        **kwargs: Any,
    ) -> Any:
        """Record a radio input and return the configured widget value."""
        self.calls.append(
            StreamlitCall(
                name="radio",
                args=(label, options),
                kwargs={"index": index, **kwargs},
            )
        )
        return self.widget_values.get(label, options[index])

    def form_submit_button(self, label: str, **kwargs: Any) -> bool:
        """Record a form submit button and return its configured response."""
        self.calls.append(
            StreamlitCall(
                name="form_submit_button",
                args=(label,),
                kwargs=kwargs,
            )
        )
        if kwargs.get("disabled"):
            return False
        return self.submit_responses.get(label, False)

    def button(self, label: str, **kwargs: Any) -> bool:
        """Record a button and return its configured response."""
        self.calls.append(
            StreamlitCall(
                name="button",
                args=(label,),
                kwargs=kwargs,
            )
        )
        if kwargs.get("disabled"):
            return False
        return self.button_responses.get(label, False)

    def toggle(
        self, label: str, value: bool = False, **kwargs: Any
    ) -> bool:
        """Record a toggle and return the configured widget value (bool)."""
        self.calls.append(
            StreamlitCall(
                name="toggle",
                args=(label,),
                kwargs={"value": value, **kwargs},
            )
        )
        return bool(self.widget_values.get(label, value))

    def selectbox(
        self,
        label: str,
        options: list[Any],
        index: int = 0,
        **kwargs: Any,
    ) -> Any:
        """Record a selectbox and return the configured value or options[index]."""
        self.calls.append(
            StreamlitCall(
                name="selectbox",
                args=(label, options),
                kwargs={"index": index, **kwargs},
            )
        )
        if label in self.widget_values:
            return self.widget_values[label]
        if not options:
            return None
        try:
            return options[index]
        except (IndexError, TypeError):
            return options[0] if options else None

    def multiselect(
        self,
        label: str,
        options: list[Any],
        default: list[Any] | None = None,
        **kwargs: Any,
    ) -> list[Any]:
        """Record a multiselect and return the configured value (list)."""
        self.calls.append(
            StreamlitCall(
                name="multiselect",
                args=(label, options),
                kwargs={"default": default, **kwargs},
            )
        )
        if label in self.widget_values:
            return list(self.widget_values[label])
        return list(default) if default else []

    def date_input(
        self, label: str, value: Any = None, **kwargs: Any
    ) -> Any:
        """Record a date_input and return the configured value or default."""
        self.calls.append(
            StreamlitCall(
                name="date_input",
                args=(label,),
                kwargs={"value": value, **kwargs},
            )
        )
        return self.widget_values.get(label, value)

    def text_area(
        self, label: str, value: str = "", **kwargs: Any
    ) -> str:
        """Record a text_area and return the configured value or default."""
        self.calls.append(
            StreamlitCall(
                name="text_area",
                args=(label,),
                kwargs={"value": value, **kwargs},
            )
        )
        return str(self.widget_values.get(label, value))

    def __getattr__(self, name: str) -> Callable[..., None]:
        """Return a recorder for any accessed Streamlit API function."""

        def _record(*args: Any, **kwargs: Any) -> None:
            self.calls.append(StreamlitCall(name=name, args=args, kwargs=kwargs))

        return _record

    def calls_named(self, name: str) -> list[StreamlitCall]:
        """Return all recorded calls with the given name."""
        return [call for call in self.calls if call.name == name]
