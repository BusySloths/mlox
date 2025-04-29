import streamlit as st


st.write("# User profile")


if not st.session_state.get("is_admin", False):
    if st.button("Make me admin"):
        st.session_state["is_admin"] = True
        st.rerun()

else:
    if st.button("Don't want to be admin"):
        st.session_state["is_admin"] = False
        st.rerun()
