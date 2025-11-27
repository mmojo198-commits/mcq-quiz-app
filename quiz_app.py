import streamlit as st
import pandas as pd
import time
import re
from pathlib import Path

st.set_page_config(page_title="MCQ Quiz", page_icon="🎯", layout="wide")

# ---------------------------
# Helpers
# ---------------------------
def normalize_text(s):
    if pd.isna(s):
        return ""
    return " ".join(str(s).strip().lower().split())

def extract_letter(s):
    """Extract option letter (A, B, C, D) from text, avoiding false matches in words."""
    if s is None:
        return None
    s_str = str(s).strip().upper()
    
    # First check if it's just a single letter
    if s_str in {"A", "B", "C", "D"}:
        return s_str
    
    # Regex to find A., A), A- etc. avoiding false positives like "Apple"
    m = re.match(r"^([A-D])[\.\:\)\-]\s*", s_str)
    if m:
        return m.group(1)
    
    # Match "Option A" format with proper boundary
    m2 = re.search(r"^OPTION\s+([A-D])(?:\s|$|[\.\:\)])", s_str)
    if m2:
        return m2.group(1)
    
    return None

def find_correct_letter(row):
    """Find which option letter (A, B, C, D) matches the correct answer."""
    corr_let = extract_letter(row["Correct Answer"])
    if not corr_let:
        # No letter found, match by text
        correct_text_norm = normalize_text(row["Correct Answer"])
        for letter in ["A", "B", "C", "D"]:
            option_text = row.get(f"Option {letter}")
            if pd.notna(option_text) and normalize_text(option_text) == correct_text_norm:
                corr_let = letter
                break
    return corr_let

def is_correct(selected, correct_raw):
    """Check if the selected answer matches the correct answer."""
    if not selected:
        return False
    
    # Extract letter from selected option (format: "A: Option Text")
    selected_letter = selected.split(":", 1)[0].strip().upper() if ":" in selected else selected.strip().upper()
    
    # Get correct letter
    correct_letter = extract_letter(correct_raw)
    
    # If we couldn't extract a letter from correct_raw, try text matching
    if not correct_letter:
        selected_text = selected.split(":", 1)[1].strip() if ":" in selected else ""
        return normalize_text(selected_text) == normalize_text(correct_raw)
    
    # Primary check: compare by letter
    if selected_letter in ["A", "B", "C", "D"]:
        return selected_letter == correct_letter
    
    return False

def read_quiz_df(df):
    """Read and validate quiz DataFrame."""
    expected = ["Question", "Option A", "Option B", "Option C", "Option D", "Correct Answer", "Hint"]
    missing = [c for c in expected if c not in df.columns]
    if missing:
        st.error(f"Missing columns in Excel: {missing}. Columns found: {list(df.columns)}")
        return pd.DataFrame()
    
    cols_to_keep = expected.copy()
    for letter in ["A", "B", "C", "D"]:
        if f"Rationale {letter}" in df.columns:
            cols_to_keep.append(f"Rationale {letter}")
    
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
# Create a placeholder for the main content to control re-rendering
if "main_content_placeholder" not in st.session_state:
    st.session_state.main_content_placeholder = None

def update_score():
    """Calculate and update the current score."""
    sc = 0
    for idx in range(len(st.session_state.questions)):
        ans = st.session_state.answers.get(idx)
        q_row = st.session_state.questions.iloc[idx]
        if ans and is_correct(ans, q_row['Correct Answer']):
            sc += 1
    st.session_state.score = sc

def save_time_state():
    """Updates the time spent for the current question."""
    i = st.session_state.index
    if st.session_state.question_start_time is not None:
        elapsed = time.time() - st.session_state.question_start_time
        current_total = st.session_state.time_spent.get(i, 0)
        
        if st.session_state.timer_per_question is None:
            st.session_state.time_spent[i] = current_total + elapsed
        else:
            st.session_state.time_spent[i] = min(st.session_state.timer_per_question, current_total + elapsed)

def handle_navigation(new_index):
    """Handles saving state before navigating to a different question."""
    i = st.session_state.index
    
    # Save time
    save_time_state()
    
    # Save answer if not already submitted (auto-save draft)
    current_selected = st.session_state.get(f"radio_{i}")
    if not st.session_state.submitted_q.get(i, False):
        st.session_state.answers[i] = current_selected
    
    # Update pointer
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
        st.write("Upload an Excel file (.xlsx) with columns: `Question`, `Option A`, `Option B`, `Option C`, `Option D`, `Correct Answer`, `Hint`, and `Rationale [A-D]`")
        
        uploaded_file = st.file_uploader("Choose file", type=["xlsx"], label_visibility="collapsed")
        
        df = None
        if uploaded_file is None:
            # Fallback logic for demo or local testing
            p = Path("cleaned_quiz_full_rationale.xlsx")
            if p.exists():
                fallback_path = p.as_posix()
                st.info(f"Auto-detected file: `{fallback_path}`")
                if st.button("Load Auto-detected File"):
                    try:
                        df_raw = pd.read_excel(fallback_path)
                        df = read_quiz_df(df_raw)
                    except Exception as e:
                        st.error(f"Error: {e}")
            else:
                pass # No fallback available, let user upload
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
    # We don't need the placeholder logic here, as we are stopping the quiz state
    st.title("🏆 Quiz Results")
    
    total_q = len(st.session_state.questions)
    percentage = (st.session_state.score / total_q) * 100 if total_q > 0 else 0
    
    col_res1, col_res2 = st.columns([1, 3])
    with col_res1:
        st.metric("Final Score", f"{st.session_state.score} / {total_q}")
    with col_res2:
        st.progress(st.session_state.score / total_q if total_q > 0 else 0)
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
    
    if st.session_state.question_start_time is None:
        st.session_state.question_start_time = time.time()
        
    if time_allowed is None:
        st.markdown("<h3 style='text-align: center; color: green; margin: 0;'>Unlimited</h3>", unsafe_allow_html=True)
        st.progress(1.0)
        remaining = None
    else:
        if is_submitted:
            time_spent = st.session_state.time_spent.get(i, 0)
        else:
            elapsed = time.time() - st.session_state.question_start_time
            previous_time = st.session_state.time_spent.get(i, 0)
            time_spent = min(time_allowed, previous_time + elapsed)
            
        remaining = max(0, time_allowed - time_spent)
        
        timer_color = "red" if remaining < 5 else "blue"
        st.markdown(f"<h1 style='text-align: center; color: {timer_color}; margin: 0;'>{int(remaining)}s</h1>", unsafe_allow_html=True)
        st.progress(min(1.0, max(0.0, remaining / time_allowed if time_allowed > 0 else 0)))

    st.divider()
    st.markdown("### 🗺️ Question Map")
    
    cols_per_row = 4
    for r in range(0, total_q, cols_per_row):
        cols = st.columns(cols_per_row)
        for c_idx, q_idx in enumerate(range(r, min(r + cols_per_row, total_q))):
            with cols[c_idx]:
                btn_type = "secondary"
                lbl = str(q_idx + 1)
                
                if q_idx == i:
                    btn_type = "primary"
                    lbl = f"▶ {q_idx+1}"
                elif st.session_state.submitted_q.get(q_idx):
                    hist_ans = st.session_state.answers.get(q_idx)
                    if hist_ans and is_correct(hist_ans, st.session_state.questions.iloc[q_idx]["Correct Answer"]):
                        lbl = f"✓ {q_idx+1}"
                    else:
                        lbl = f"✗ {q_idx+1}"
                
                # Check the state of the button before rendering
                is_current = (q_idx == i)
                # Use a unique key for the button itself
                if st.button(lbl, key=f"nav_{q_idx}", use_container_width=True, type=btn_type):
                    handle_navigation(q_idx)
                    
    st.divider()
    
    if st.button("🏁 Finish Quiz", key="sidebar_finish", use_container_width=True, type="secondary"):
        save_time_state()
        curr = st.session_state.get(f"radio_{i}")
        if not is_submitted:
            st.session_state.answers[i] = curr
            st.session_state.submitted_q[i] = True
            
        update_score()
        st.session_state.finished = True
        st.rerun()

# --- MAIN CONTENT PLACEHOLDER LOGIC ---
# Create the placeholder on the first run, or retrieve it
if st.session_state.main_content_placeholder is None:
    st.session_state.main_content_placeholder = st.empty()

# Clear the placeholder to ensure no previous elements linger
placeholder = st.session_state.main_content_placeholder
placeholder.empty()

# Render all of the question content inside the placeholder
with placeholder.container():
    st.markdown(f"#### Question {i + 1} of {total_q}")
    st.progress((i) / total_q)

    with st.container(border=True):
        st.markdown(f"### {row['Question']}")
        
        options = [
            ("A", row["Option A"]), ("B", row["Option B"]),
            ("C", row["Option C"]), ("D", row["Option D"]),
        ]
        display_options = [f"{letter}: {text}" for letter, text in options if pd.notna(text)]

        # Restore selection by letter prefix
        saved_ans = st.session_state.answers.get(i, None)
        
        radio_idx = None
        if saved_ans:
            if ":" in saved_ans:
                saved_letter = saved_ans.split(":", 1)[0].strip().upper()
                for idx, opt in enumerate(display_options):
                    if opt.startswith(f"{saved_letter}:"):
                        radio_idx = idx
                        break
            elif saved_ans in display_options:
                radio_idx = display_options.index(saved_ans)
                
        # This radio button key MUST be unique per question index
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
            corr_let = find_correct_letter(row)

            if saved_ans:
                if is_correct(saved_ans, row["Correct Answer"]):
                    st.success("✅ Correct!")
                    if corr_let and f"Rationale {corr_let}" in row and pd.notna(row[f"Rationale {corr_let}"]):
                        st.info(f"**Rationale:** {row[f'Rationale {corr_let}']}")
                else:
                    if corr_let:
                        corr_txt = row.get(f"Option {corr_let}", str(row["Correct Answer"]))
                        st.error(f"❌ Incorrect. Correct Answer: **{corr_let}: {corr_txt}**")
                    else:
                        st.error(f"❌ Incorrect. Correct Answer: **{row['Correct Answer']}**")
                    
                    selected_letter = saved_ans.split(":", 1)[0].strip().upper()
                    
                    if selected_letter in ["A", "B", "C", "D"] and f"Rationale {selected_letter}" in row and pd.notna(row[f"Rationale {selected_letter}"]):
                        st.warning(f"**Not Quite ({selected_letter}):** {row[f'Rationale {selected_letter}']}")

                    if corr_let and f"Rationale {corr_let}" in row and pd.notna(row[f"Rationale {corr_let}"]):
                        st.info(f"**Rationale for correct answer ({corr_let}):** {row[f'Rationale {corr_let}']}")
            else:
                st.warning("⌛ Answer locked (no answer submitted).")
                if corr_let:
                    corr_txt = row.get(f"Option {corr_let}", str(row["Correct Answer"]))
                    st.markdown(f"**Correct Answer:** {corr_let}: {corr_txt}")
                    if f"Rationale {corr_let}" in row and pd.notna(row[f"Rationale {corr_let}"]):
                        st.info(f"**Rationale for correct answer ({corr_let}):** {row[f'Rationale {corr_let}']}")
                else:
                    st.markdown(f"**Correct Answer:** {row['Correct Answer']}")

        if not is_submitted:
            # Added key=f"hint_{i}" to ensure hint state doesn't leak to next question
            if pd.notna(row.get("Hint")) and st.checkbox("Show Hint", key=f"hint_{i}"):
                st.info(f"💡 Hint: {row['Hint']}")

    # --- FOOTER NAV (Rendered inside the placeholder to ensure it's cleared) ---
    col_prev, col_submit, col_next = st.columns([1, 2, 1])

    with col_prev:
        if st.button("⬅️ Previous", disabled=(i == 0), use_container_width=True, key=f"prev_{i}"):
            handle_navigation(i - 1)

    with col_submit:
        if not is_submitted:
            if st.button("🔒 Submit Answer", type="primary", use_container_width=True, key=f"submit_{i}"):
                save_time_state()
                st.session_state.answers[i] = selected
                st.session_state.submitted_q[i] = True
                update_score()
                st.rerun()

    with col_next:
        if i < total_q - 1:
            if st.button("Next ➡️", use_container_width=True, key=f"next_{i}"):
                handle_navigation(i + 1)
        else:
            if st.button("🏁 Finish Quiz", type="primary", use_container_width=True, key=f"finish_{i}"):
                save_time_state()
                curr = st.session_state.get(f"radio_{i}")
                if not is_submitted:
                    st.session_state.answers[i] = curr
                    st.session_state.submitted_q[i] = True
                update_score()
                st.session_state.finished = True
                st.rerun()

# --- AUTO-ACTION (ONLY IF TIMER EXISTS) ---
if time_allowed is not None:
    # Check for timeout
    if remaining is not None and remaining <= 0 and not is_submitted:
        st.session_state.time_spent[i] = time_allowed
        st.session_state.submitted_q[i] = True
        current_selection = st.session_state.get(f"radio_{i}")
        st.session_state.answers[i] = current_selection
        update_score()
        # NOTE: Do not use st.warning here, use placeholder to display timeout message temporarily
        # st.warning("⏰ Time's Up!") 
        # Rerunning directly will handle the feedback display
        time.sleep(1)
        st.rerun()
    elif not is_submitted:
        # Refresh every second to update timer UI
        time.sleep(1.0)
        st.rerun()
