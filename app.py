import streamlit as st
import sys
import subprocess

st.set_page_config(page_title="Debug Mode v2", page_icon="🔧")

st.title("✅ App Started (Debug v2)")
st.write(f"Python Version: {sys.version}")

st.subheader("📦 Installed Packages")
try:
    # Run pip freeze to see what's actually installed
    result = subprocess.run([sys.executable, "-m", "pip", "freeze"], capture_output=True, text=True)
    st.code(result.stdout)
except Exception as e:
    st.error(f"Failed to run pip freeze: {e}")

st.subheader("🔄 Attempting to Import 'yfinance'")
try:
    import yfinance
    st.success(f"yfinance imported successfully! Version: {yfinance.__version__}")
except ImportError as e:
    st.error(f"Import failed: {e}")
    
    # Emergency Install Attempt (Not recommended for prod, but good for debug)
    if st.button("🚑 Emergency Install yfinance"):
        with st.spinner("Installing yfinance..."):
            try:
                subprocess.check_call([sys.executable, "-m", "pip", "install", "yfinance"])
                st.success("Installed! Please reload the page.")
            except Exception as install_error:
                st.error(f"Install failed: {install_error}")

if st.button("Load Main Dashboard"):
    try:
        import dashboard
    except Exception as e:
        st.error(f"Still failed: {e}")
