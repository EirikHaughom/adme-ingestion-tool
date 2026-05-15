"""Test doubles for Streamlit page assertions."""

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

    def __getattr__(self, name: str) -> Callable[..., None]:
        """Return a recorder for any accessed Streamlit API function."""

        def _record(*args: Any, **kwargs: Any) -> None:
            self.calls.append(StreamlitCall(name=name, args=args, kwargs=kwargs))

        return _record

    def calls_named(self, name: str) -> list[StreamlitCall]:
        """Return all recorded calls with the given name."""
        return [call for call in self.calls if call.name == name]
