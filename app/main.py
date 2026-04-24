"""Entry point for the ADME control plane Streamlit app."""

import streamlit as st


def main() -> None:
    st.set_page_config(
        page_title="ADME Control Plane",
        page_icon="⚡",
        layout="wide",
    )
    st.title("ADME Control Plane")
    st.markdown(
        "Operator dashboard for Azure Data Manager for Energy (ADME)."
    )


if __name__ == "__main__":
    main()
