import streamlit as st
import pandas as pd
import time
import re
from pathlib import Path

# ---------------------------
# Config
# ---------------------------
st.set_page_config(page_title="MCQ Quiz", page_icon="🎯", layout="wide")

LOCAL_UPLOADED_FILE_PATH = "/mnt/data/f8416257-dc87-4746-a6b6-00755d7ca1d9.png"

# ---------------------------
# Helpers
# ---------------------------
def normalize_text(s):
    if pd.isna(s):
        return ""
    # Convert to string, lowercase, remove extra whitespace, and remove common punctuation
    text = str(s).strip().lower()
    # Remove multiple spaces and normalize
    text = " ".join(text.split())
    # Remove trailing periods and commas that might differ
    text = text.rstrip('.,;:')
    return text

def extract_letter(s):
    if s is None:
        return None
    s_str = str(s).strip().upper()
    if s_str in {"A", "B", "C", "D"}:
        return s_str
    m = re.match(r"^([A-D])[\.\:\)\-\s]*", s_str)
    if m:
        return m.group(1)
    m2 = re.search(r"OPTION\s*([A-D])", s_str)
    if m2:
        return m2.group(1)
    return None

def find_correct_letter(row):
    """Find which option letter (A, B, C, D) matches the correct answer."""
    corr_let = extract_letter(row["Correct Answer"])
    if not corr_let:
        # No letter found, match by exact text comparison (case-insensitive, whitespace-normalized)
        correct_text_norm = normalize_text(row["Correct Answer"])
        
        # First pass: Try exact match
        for letter in ["A", "B", "C", "D"]:
            option_text = row.get(f"Option {letter}")
            if pd.notna(option_text):
                option_text_norm = normalize_text(option_text)
                # Must be exact match
                if option_text_norm == correct_text_norm:
                    return letter
        
        # Second pass: If no exact match, try finding best substring match
        # This handles cases where there might be minor differences
        best_match = None
        best_match_score = 0
        
        for letter in ["A", "B", "C", "D"]:
            option_text = row.get(f"Option {letter}")
            if pd.notna(option_text):
                option_text_norm = normalize_text(option_text)
                
                # Calculate similarity: if one contains the other completely
                if correct_text_norm in option_text_norm:
                    # Correct answer is subset of option
                    score = len(correct_text_norm) / len(option_text_norm)
                    if score > best_match_score:
                        best_match = letter
                        best_match_score = score
                elif option_text_norm in correct_text_norm:
                    # Option is subset of correct answer
                    score = len(option_text_norm) / len(correct_text_norm)
                    if score > best_match_score:
                        best_match = letter
                        best_match_score = score
        
        if best_match and best_match_score > 0.9:  # Only accept if 90%+ match
            corr_let = best_match
    
    return corr_let

def is_correct(selected, correct_raw):
    if not selected:
        return False
    
    # Extract the selected letter (A, B, C, D)
    selected_letter = selected.split(":", 1)[0].strip().upper()
    
    # Try to extract letter from correct answer
    correct_letter = extract_letter(correct_raw)
    
    if correct_letter:
        # If we have a letter in the correct answer, compare letters directly
        return selected_letter == correct_letter
    
    # If no letter in correct answer, compare the full text
    # Extract the text after the colon from selected answer
    if ":" in selected:
        selected_text = selected.split(":", 1)[1].strip()
        # Must be exact match of the full text
        return normalize_text(selected_text) == normalize_text(correct_raw)
    
    return False

def parse_rationale(rationale_text, selected_letter):
    """Extract the rationale for the selected wrong answer."""
    if pd.isna(rationale_text):
        return None
    
    # Split by pipe to get individual explanations
    parts = str(rationale_text).split("|")
    
    for part in parts:
        part = part.strip()
        # Check if this part is for the selected option
        # Format: "Option A: explanation" or "Small Finance Banks: explanation"
        if part.upper().startswith(f"OPTION {selected_letter}:") or \
           part.upper().startswith(f"{selected_letter}:"):
            # Extract the explanation after the colon
            if ":" in part:
                return part.split(":", 1)[1].strip()
        # Also check if the part starts with the actual option text
        # This handles cases like "Small Finance Banks: explanation"
        else:
            # Try to match by checking if part contains the selected option text
            # We'll return this if we find a match
            continue
    
    # If we didn't find a match by option letter, try another approach
    # Look for explanations that match option text
    for part in parts:
        part = part.strip()
        if part and ":" in part:
            option_prefix = part.split(":", 1)[0].strip()
            # If the prefix doesn't start with "Option", it might be the actual option text
            if not option_prefix.upper().startswith("OPTION"):
                # This might be a match - return it if no better match found
                # For now, we'll try to match this later
                pass
    
    return None

def read_quiz_df(df):
    expected = ["Question", "Option A", "Option B", "Option C", "Option D", "Correct Answer", "Hint"]
    missing = [c for c in expected if c not in df.columns]
    if missing:
        st.error(f"Missing columns in Excel: {missing}. Columns found: {list(df.columns)}")
        return pd.DataFrame()
    
    # Include Rationale column if it exists
    cols_to_keep = expected.copy()
    if "Rationale (Wrong Answers)" in df.columns:
        cols_to_keep.append("Rationale (Wrong Answers)")
    
    return df[cols_to_keep].copy()

# ---------------------------
# Session State
# ---------------------------
if "quiz_started" not in st.session_state:
    st.session_state.quiz_started = False
if "questions" not in st.session_state:
    st.session_state.questions = None
if "index" not in st.session_state:
    st.session_state.index = 0
if "answers" not in st.session_state:
    st.session_state.answers = {}
if "time_spent" not in st.session_state:
    st.session_state.time_spent = {} 
if "submitted_q" not in st.session_state:
    st.session_state.submitted_q = {}
if "timer_per_question" not in st.session_state:
    st.session_state.timer_per_question = None
if "question_start_time" not in st.session_state:
    st.session_state.question_start_time = None
if "shuffle" not in st.session_state:
    st.session_state.shuffle = True
if "timer_choice" not in st.session_state:
    st.session_state.timer_choice = 30
if "finished" not in st.session_state:
    st.session_state.finished = False
if "score" not in st.session_state:
    st.session_state.score = 0

def update_score():
    sc = 0
    for idx in range(len(st.session_state.questions)):
        ans = st.session_state.answers.get(idx)
        if ans and is_correct(ans, st.session_state.questions.iloc[idx]["Correct Answer"]):
            sc += 1
    st.session_state.score = sc

def save_time_state():
    """Updates the time spent for the current question."""
    i = st.session_state.index
    if st.session_state.question_start_time is not None:
        elapsed = time.time() - st.session_state.question_start_time
        current_total = st.session_state.time_spent.get(i, 0)
        
        if st.session_state.timer_per_question is None:
            # No cap if 'No timer' is selected
            st.session_state.time_spent[i] = current_total + elapsed
        else:
            # Cap at max time allowed
            st.session_state.time_spent[i] = min(st.session_state.timer_per_question, current_total + elapsed)

# ---------------------------
# Navigation Handler
# ---------------------------
def handle_navigation(new_index):
    """Handles saving state before navigating to a different question."""
    i = st.session_state.index
    
    # 1. Save time
    save_time_state()
    
    # 2. Save answer if not already submitted (auto-save draft)
    current_selected = st.session_state.get(f"radio_{i}")
    if not st.session_state.submitted_q.get(i, False):
        st.session_state.answers[i] = current_selected

    # 3. Update pointer
    st.session_state.index = new_index
    st.session_state.question_start_time = time.time()
    st.rerun()

# ---------------------------
# State 1: File Upload
# ---------------------------
if st.session_state.questions is None:
    st.title("📘 Interactive MCQ Quiz")
    
    with st.container(border=True):
        st.write("### 📤 Upload Quiz Data")
        st.write("Upload an Excel file (.xlsx) with columns: `Question`, `Option A`, `Option B`, `Option C`, `Option D`, `Correct Answer`, `Hint`, `Rationale (Wrong Answers)`")
        
        uploaded_file = st.file_uploader("Choose file", type=["xlsx"], label_visibility="collapsed")
        
        df = None
        if uploaded_file is None:
            # Fallback logic for demo or local testing
            p = Path("/mnt/data")
            if p.exists():
                xlsx_files = sorted(p.glob("*.xlsx"))
                if xlsx_files:
                    fallback_path = xlsx_files[0].as_posix()
                    st.info(f"Auto-detected file: `{fallback_path}`")
                    if st.button("Load Auto-detected File"):
                        try:
                            df_raw = pd.read_excel(fallback_path)
                            df = read_quiz_df(df_raw)
                        except Exception as e:
                            st.error(f"Error: {e}")
        else:
            try:
                df_raw = pd.read_excel(uploaded_file)
                df = read_quiz_df(df_raw)
            except Exception as e:
                st.error(f"Error: {e}")
                df = None

        if df is not None and not df.empty:
            st.session_state.questions = df.reset_index(drop=True)
            st.session_state.quiz_started = False
            st.success(f"✅ Loaded {len(st.session_state.questions)} questions!")
            time.sleep(1)
            st.rerun()
    st.stop()

# ---------------------------
# State 2: Setup
# ---------------------------
if st.session_state.questions is not None and not st.session_state.quiz_started:
    st.title("⚙️ Quiz Setup")
    
    with st.container(border=True):
        st.write(f"**Total Questions:** {len(st.session_state.questions)}")
        
        TIMER_OPTIONS = ["No timer", 10, 15, 20, 30, 45, 60]
        
        # Determine default index
        try:
            default_idx = TIMER_OPTIONS.index(st.session_state.timer_choice)
        except ValueError:
            default_idx = TIMER_OPTIONS.index(30)

        col1, col2 = st.columns(2)
        with col1:
            st.session_state.shuffle = st.checkbox("Shuffle Questions", value=st.session_state.shuffle)
        with col2:
            st.session_state.timer_choice = st.selectbox(
                "Time per question (seconds)", 
                TIMER_OPTIONS, 
                index=default_idx
            )

        st.divider()
        
        if st.button("🚀 Start Quiz", use_container_width=True, type="primary"):
            questions_df = st.session_state.questions
            if st.session_state.shuffle:
                st.session_state.questions = questions_df.sample(frac=1, random_state=int(time.time())).reset_index(drop=True)
            else:
                st.session_state.questions = questions_df.reset_index(drop=True)
                
            st.session_state.index = 0
            st.session_state.answers = {}
            st.session_state.time_spent = {}
            st.session_state.submitted_q = {}
            
            # Set timer config
            if st.session_state.timer_choice == "No timer":
                st.session_state.timer_per_question = None
            else:
                st.session_state.timer_per_question = int(st.session_state.timer_choice)
                
            st.session_state.question_start_time = time.time()
            st.session_state.quiz_started = True
            st.session_state.finished = False
            st.session_state.score = 0
            st.rerun()
            
        if st.button("🔄 Reset File"):
            st.session_state.questions = None
            st.rerun()
    st.stop()

# ---------------------------
# State 3: Results
# ---------------------------
if st.session_state.finished:
    st.title("🏆 Quiz Results")
    
    total_q = len(st.session_state.questions)
    percentage = (st.session_state.score / total_q) * 100
    
    col_res1, col_res2 = st.columns([1, 3])
    with col_res1:
        st.metric("Final Score", f"{st.session_state.score} / {total_q}")
    with col_res2:
        st.progress(st.session_state.score / total_q)
        st.caption(f"Accuracy: {percentage:.1f}%")

    st.divider()
    
    # Summary Table
    results_data = []
    for idx in range(total_q):
        q = st.session_state.questions.iloc[idx]
        user_ans = st.session_state.answers.get(idx)
        correct_raw = q["Correct Answer"]
        
        is_corr = False
        if user_ans:
            is_corr = is_correct(user_ans, correct_raw)
            
        results_data.append({
            "No.": idx + 1,
            "Question": q["Question"],
            "Your Answer": user_ans if user_ans else "Skipped",
            "Correct Answer": correct_raw,
            "Result": "✅" if is_corr else "❌"
        })
    
    st.dataframe(pd.DataFrame(results_data), use_container_width=True, hide_index=True)
    
    col_act1, col_act2 = st.columns(2)
    with col_act1:
        if st.button("🔁 Retry Same Questions", use_container_width=True):
            st.session_state.quiz_started = False
            st.session_state.finished = False
            st.rerun()
    with col_act2:
        if st.button("📂 Upload New File", use_container_width=True):
            for k in list(st.session_state.keys()):
                del st.session_state[k]
            st.rerun()
    st.stop()

# ---------------------------
# State 4: Active Quiz UI
# ---------------------------
questions = st.session_state.questions
i = st.session_state.index
total_q = len(questions)
row = questions.iloc[i]
is_submitted = st.session_state.submitted_q.get(i, False)
time_allowed = st.session_state.timer_per_question

# --- SIDEBAR: Timer & Map ---
with st.sidebar:
    st.markdown("### ⏳ Timer")
    
    # Initialize Time if needed
    if st.session_state.question_start_time is None:
        st.session_state.question_start_time = time.time()
        
    # --- Logic for Timer Display ---
    if time_allowed is None:
        # NO TIMER MODE
        st.markdown("<h3 style='text-align: center; color: green; margin: 0;'>Unlimited</h3>", unsafe_allow_html=True)
        st.progress(1.0)
        remaining = None # Flag as none
    else:
        # TIMER MODE
        if is_submitted:
            time_spent = st.session_state.time_spent.get(i, 0)
        else:
            elapsed = time.time() - st.session_state.question_start_time
            previous_time = st.session_state.time_spent.get(i, 0)
            time_spent = min(time_allowed, previous_time + elapsed)
            
        remaining = max(0, time_allowed - time_spent)
        
        timer_color = "red" if remaining < 5 else "blue"
        st.markdown(f"<h1 style='text-align: center; color: {timer_color}; margin: 0;'>{int(remaining)}s</h1>", unsafe_allow_html=True)
        st.progress(min(1.0, max(0.0, remaining / time_allowed)))

    st.divider()
    st.markdown("### 🗺️ Question Map")
    
    # Dynamic Grid
    cols_per_row = 4
    for r in range(0, total_q, cols_per_row):
        cols = st.columns(cols_per_row)
        for c_idx, q_idx in enumerate(range(r, min(r + cols_per_row, total_q))):
            with cols[c_idx]:
                # Determine styling
                btn_type = "secondary"
                lbl = str(q_idx + 1)
                
                if q_idx == i:
                    btn_type = "primary"
                    lbl = f"▶ {q_idx+1}"
                elif st.session_state.submitted_q.get(q_idx):
                    # Check if correct
                    hist_ans = st.session_state.answers.get(q_idx)
                    if hist_ans and is_correct(hist_ans, st.session_state.questions.iloc[q_idx]["Correct Answer"]):
                        lbl = f"✓ {q_idx+1}"
                    else:
                        lbl = f"✗ {q_idx+1}"
                
                if st.button(lbl, key=f"nav_{q_idx}", use_container_width=True, type=btn_type):
                     handle_navigation(q_idx)
                     
    st.divider()
    # Finish Button in Sidebar
    can_finish = (i == total_q - 1) or is_submitted
    if st.button("🏁 Finish Quiz", use_container_width=True, type="primary" if i == total_q - 1 else "secondary"):
        save_time_state()
        curr = st.session_state.get(f"radio_{i}")
        if not is_submitted:
            st.session_state.answers[i] = curr
            st.session_state.submitted_q[i] = True
            
        update_score()
        st.session_state.finished = True
        st.rerun()

# --- MAIN CONTENT ---
st.markdown(f"#### Question {i + 1} of {total_q}")
st.progress((i) / total_q)

with st.container(border=True):
    st.markdown(f"### {row['Question']}")
    
    options = [
        ("A", row["Option A"]), ("B", row["Option B"]),
        ("C", row["Option C"]), ("D", row["Option D"]),
    ]
    display_options = [f"{letter}: {text}" for letter, text in options if pd.notna(text)]

    # Persist Selection logic
    saved_ans = st.session_state.answers.get(i, None)
    
    radio_idx = None
    if saved_ans in display_options:
        radio_idx = display_options.index(saved_ans)
        
    selected = st.radio(
        "Select your answer:", 
        display_options, 
        index=radio_idx, 
        key=f"radio_{i}", 
        disabled=is_submitted
    )

    # Feedback Area
    if is_submitted:
        st.divider()
        if saved_ans:
            # Get fresh row data
            current_row = st.session_state.questions.iloc[i]
            
            if is_correct(saved_ans, current_row["Correct Answer"]):
                st.success("✅ Correct!")
            else:
                # Find which option matches the correct answer
                corr_let = find_correct_letter(current_row)
                
                if corr_let:
                    corr_txt = current_row.get(f"Option {corr_let}", str(current_row["Correct Answer"]))
                    st.error(f"❌ Incorrect. Correct Answer: **{corr_let}: {corr_txt}**")
                else:
                    st.error(f"❌ Incorrect. Correct Answer: **{current_row['Correct Answer']}**")
                
                # DEBUG: Show what was compared (remove this after testing)
                with st.expander("🔍 Debug Info (for testing)"):
                    st.write(f"**Your selection:** {saved_ans}")
                    st.write(f"**Your Selected Letter:** {saved_ans.split(':', 1)[0].strip().upper()}")
                    st.write(f"**Correct Answer from Excel:** `{current_row['Correct Answer']}`")
                    st.write(f"**Correct Answer (normalized):** `{normalize_text(current_row['Correct Answer'])}`")
                    st.write(f"**Detected Correct Letter:** {corr_let}")
                    
                    # Test find_correct_letter again with debugging
                    st.write("---")
                    st.write("**Testing find_correct_letter() step-by-step:**")
                    test_correct_norm = normalize_text(current_row['Correct Answer'])
                    st.write(f"Correct answer normalized: `{test_correct_norm}`")
                    st.write(f"Length: {len(test_correct_norm)}")
                    
                    for letter in ["A", "B", "C", "D"]:
                        opt = current_row.get(f"Option {letter}")
                        if pd.notna(opt):
                            opt_norm = normalize_text(opt)
                            is_exact_match = (opt_norm == test_correct_norm)
                            st.write(f"**Option {letter}:**")
                            st.write(f"  - Text: `{opt}`")
                            st.write(f"  - Normalized: `{opt_norm}`")
                            st.write(f"  - Length: {len(opt_norm)}")
                            st.write(f"  - Exact match (==): {is_exact_match}")
                            if is_exact_match:
                                st.success(f"  ✅ This should be the match!")
                    
                    st.write("---")
                    st.write("**All Options (with normalized text):**")
                    for letter in ["A", "B", "C", "D"]:
                        opt = current_row.get(f"Option {letter}")
                        if pd.notna(opt):
                            opt_norm = normalize_text(opt)
                            match_indicator = "✅ MATCH" if opt_norm == normalize_text(current_row['Correct Answer']) else ""
                            st.write(f"  - **{letter}:** {opt}")
                            st.write(f"    *Normalized:* `{opt_norm}` {match_indicator}")
                    
                    # Show comparison result
                    st.write("---")
                    st.write(f"**is_correct() returned:** {is_correct(saved_ans, current_row['Correct Answer'])}")
                
                # Show rationale for wrong answer
                selected_letter = saved_ans.split(":", 1)[0].strip().upper()
                if "Rationale (Wrong Answers)" in current_row and pd.notna(current_row["Rationale (Wrong Answers)"]):
                    rationale_text = str(current_row["Rationale (Wrong Answers)"])
                    
                    # Parse rationale to find explanation for the selected wrong option
                    parts = rationale_text.split("|")
                    found_rationale = None
                    
                    for part in parts:
                        part = part.strip()
                        # Check various formats
                        if part.upper().startswith(f"OPTION {selected_letter}:"):
                            found_rationale = part.split(":", 1)[1].strip()
                            break
                        elif part.startswith(f"{selected_letter}:"):
                            found_rationale = part.split(":", 1)[1].strip()
                            break
                        # Check if it starts with the actual option text
                        elif part.startswith(current_row.get(f"Option {selected_letter}", "")):
                            if ":" in part:
                                found_rationale = part.split(":", 1)[1].strip()
                                break
                    
                    if found_rationale:
                        st.info(f"**Why this is wrong:** {found_rationale}")
        else:
            # Handle timed out or skipped
            st.warning("⌛ Answer locked.")
            
            # Find which option matches the correct answer
            corr_let = find_correct_letter(row)
            
            if corr_let:
                corr_txt = row.get(f"Option {corr_let}", str(row["Correct Answer"]))
                st.markdown(f"**Correct Answer:** {corr_let}: {corr_txt}")
            else:
                st.markdown(f"**Correct Answer:** {row['Correct Answer']}")

    if not is_submitted:
        if pd.notna(row.get("Hint")) and st.checkbox("Show Hint"):
            st.info(f"💡 Hint: {row['Hint']}")

# --- FOOTER NAV ---
col_prev, col_submit, col_next = st.columns([1, 2, 1])

with col_prev:
    if st.button("⬅️ Previous", disabled=(i == 0), use_container_width=True):
        handle_navigation(i - 1)

with col_submit:
    if not is_submitted:
        if st.button("🔒 Submit Answer", type="primary", use_container_width=True):
            save_time_state()
            st.session_state.answers[i] = selected
            st.session_state.submitted_q[i] = True
            update_score()
            st.rerun()

with col_next:
    if st.button("Next ➡️", disabled=(i == total_q - 1), use_container_width=True):
        handle_navigation(i + 1)

# --- AUTO-ACTION (ONLY IF TIMER EXISTS) ---
if time_allowed is not None:
    # If timer is active, check for timeout
    if remaining is not None and remaining <= 0 and not is_submitted:
        st.session_state.time_spent[i] = time_allowed
        st.session_state.submitted_q[i] = True
        current_selection = st.session_state.get(f"radio_{i}")
        st.session_state.answers[i] = current_selection
        update_score()
        st.warning("⏰ Time's Up!")
        time.sleep(1)
        st.rerun()

    elif not is_submitted:
        # Heartbeat for timer refresh (only needed if timer is running)
        time.sleep(1.0) 
        st.rerun()
