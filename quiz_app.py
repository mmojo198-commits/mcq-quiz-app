# ... [Previous code remains the same up to the Sidebar] ...

# --- SIDEBAR: Timer & Map ---
with st.sidebar:
    st.markdown("### ⏳ Timer")
    
    # ... [Timer logic remains the same] ...
    
    # ... [Question Map logic remains the same] ...
    
    st.divider()
    
    if st.button("🏁 Finish Quiz", use_container_width=True, type="secondary"):
        # ... [Finish logic remains the same] ...

# =================================================================
# ⚡ MOVED AUTO-ACTION LOGIC HERE (BEFORE UI RENDERING)
# =================================================================
# This prevents the "double button" glitch by checking timeout 
# and rerunning *before* drawing the navigation buttons.
if time_allowed is not None and not is_submitted:
    if remaining is not None and remaining <= 0:
        st.session_state.time_spent[i] = time_allowed
        st.session_state.submitted_q[i] = True
        st.session_state.show_feedback_for = i
        
        # We must fetch the current selection safely before rerunning
        # Note: We can't rely on st.session_state.get(f"selected_option_{i}") here 
        # because the widget hasn't been rendered in this run yet if we moved this block up.
        # HOWEVER: Since we are re-running, the widget state from the *previous* run 
        # should still be in session_state if the user interacted with it.
        # If this is a fresh timeout with no interaction, it will be None.
        
        current_selection = st.session_state.get(f"selected_option_{i}")
        st.session_state.answers[i] = current_selection
        update_score()
        st.warning("⏰ Time's Up!")
        time.sleep(1)
        st.rerun()
    elif remaining is not None and remaining > 0:
        # If you want a live countdown, we need to rerun.
        # But doing it at the end of the script causes the visual glitch.
        # We use a placeholder or just rely on the sidebar update.
        # To keep the timer ticking smoothly without duplicating UI:
        time.sleep(1.0)
        st.rerun()

# --- MAIN CONTENT ---
st.markdown(f"#### Question {i + 1} of {total_q}")
st.progress((i) / total_q)

# ... [Rest of the UI code: Question container, Options, Feedback] ...

# ... [Footer Nav buttons code] ...

# Remove the Auto-Action block from the very bottom of the file.
