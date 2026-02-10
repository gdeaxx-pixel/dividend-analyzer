import streamlit as st

st.set_page_config(page_title="Debug Mode", page_icon="🔧")

st.title("✅ App Started!")
st.write("The Streamlit container is healthy and responding.")
st.write("This confirms the issue was with the application startup logic or dependencies, not the cloud environment itself.")

if st.button("Load Main Dashboard (Experimental)"):
    st.info("Loading full dashboard...")
    try:
        # Dynamic import to load the real app on demand
        import dashboard
        # Check if dashboard has a main function to run, or if importing it runs the script.
        # Since the original app.py was a script, importing it runs it.
        # However, set_page_config is likely called again inside dashboard.
        # We might need to suppress that or just accept the warning/error for this debug step.
    except Exception as e:
        st.error(f"Failed to load dashboard: {e}")
