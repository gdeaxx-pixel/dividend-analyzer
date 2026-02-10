import streamlit as st
import sys
import subprocess
import time

st.set_page_config(page_title="Debug Mode v3", page_icon="🕵️")

st.title("🕵️ Debug v3: Force Install & Log")
st.write(f"**Python Version:** `{sys.version}`")
st.write("**Goal:** Force install `yfinance` to capture the compilation error.")

if st.button("🚀 Run Verbose Install (pip install -v yfinance)"):
    st.info("Starting installation... This might take 30-60 seconds.")
    
    # Create a placeholder for logs
    log_container = st.empty()
    full_output = []
    
    try:
        # Run pip install with verbose output
        process = subprocess.Popen(
            [sys.executable, "-m", "pip", "install", "-v", "yfinance==0.2.36"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        # Stream output
        while True:
            output = process.stdout.readline()
            if output == '' and process.poll() is not None:
                break
            if output:
                full_output.append(output)
                # Ensure we don't lag browser too much
                if len(full_output) % 10 == 0:
                    log_container.code("".join(full_output[-20:]), language="bash") # Show last 20 lines
        
        # Capture stderr
        stderr_output = process.stderr.read()
        full_output.append(stderr_output)
        
        rc = process.poll()
        
        st.subheader("🏁 Result")
        if rc == 0:
            st.success("Installation Successful!")
        else:
            st.error(f"Installation Failed with code {rc}")
            
        with st.expander("📜 Full Installation Log", expanded=True):
            st.code("".join(full_output))
            
    except Exception as e:
        st.error(f"Subprocess failed: {e}")

if st.button("Load Main Dashboard"):
    try:
        import dashboard
        st.success("Dashboard loaded!")
    except ImportError as e:
        st.error(f"Import Failed: {e}")
