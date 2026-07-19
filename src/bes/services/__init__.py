"""Application service layer.

Framework-agnostic orchestration extracted from the Streamlit views so that
both the Streamlit UI and the (future) FastAPI backend call one single source
of truth. Services return raw numeric data — never formatted strings or
framework objects.
"""
