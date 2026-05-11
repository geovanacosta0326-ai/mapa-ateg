import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(layout="wide")

with open("mapa_ateg_final.html", "r", encoding="utf-8") as f:
    mapa_html = f.read()

components.html(
    mapa_html,
    height=900,
    scrolling=True
)