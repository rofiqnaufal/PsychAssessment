import streamlit as st
import pandas as pd, os, datetime, random, string
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from scoring import compute_domain_means, compute_im_score, inconsistency_index, max_longstring, adjust_for_im
import gspread
from google.oauth2.service_account import Credentials

# ======= PAGE CONFIG & STYLING =======
st.set_page_config(page_title="FOOTPSY Assessment", layout="wide")

primary_green = "#4CAF50"
st.markdown(f"""
<style>
/* Force dark mode on all devices */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

* {{
    font-family: 'Inter', sans-serif;
}}

/* Main container dark theme */
.main {{
    background-color: #111111;
    color: #FFFFFF;
}}

/* Target mobile-specific Streamlit classes */
section[data-testid="stSidebar"],
div[data-testid="stSidebar"] {{
    background-color: #111111 !important;
}}

/* Header and text elements */
.stMarkdown, .stTitle, .stHeader, .stSubheader {{
    color: #FFFFFF !important;
}}

/* Form elements */
.stRadio > div {{
    background-color: #1E1E1E !important;
}}

.stRadio label {{
    color: #FFFFFF !important;
}}

/* Buttons */
.stButton>button {{
    background-color: {primary_green} !important;
    color: white !important;
    border: none !important;
    border-radius: 6px !important;
    padding: 8px 16px !important;
    font-weight: 500 !important;
}}

.stButton>button:hover {{
    background-color: #66BB6A !important;
    color: white !important;
}}

/* Text inputs */
.stTextInput input {{
    background-color: #1E1E1E !important;
    color: #FFFFFF !important;
    border: 1px solid #333 !important;
}}

.stTextInput label {{
    color: #FFFFFF !important;
}}

/* Date input */
.stDateInput input {{
    background-color: #1E1E1E !important;
    color: #FFFFFF !important;
    border: 1px solid #333 !important;
}}

.stDateInput label {{
    color: #FFFFFF !important;
}}

/* Disabled inputs */
.stTextInput input:disabled {{
    background-color: #2A2A2A !important;
    color: #888 !important;
}}

/* Radio buttons - ensure text is visible */
div[role="radiogroup"] label {{
    color: white !important;
    background-color: #1E1E1E !important;
}}

/* Mobile-specific media query */
@media (max-width: 768px) {{
    .main {{
        background-color: #111111 !important;
    }}

    div[data-testid="stVerticalBlock"] {{
        background-color: #111111 !important;
    }}

    section.main {{
        background-color: #111111 !important;
    }}

    /* Ensure all text is visible on mobile */
    .stMarkdown, .stTitle, .stHeader, .stSubheader {{
        color: #FFFFFF !important;
    }}
}}

/* Warning text */
div[data-testid="stMarkdownContainer"] p {{
    color: #FFFFFF !important;
}}

/* Make sure the warning red is visible */
div[style*="color:red"] {{
    color: #FF6B6B !important;
}}

/* Caption text */
.stCaption {{
    color: #CCCCCC !important;
}}

/* Metric cards */
.stMetric {{
    background-color: #1E1E1E !important;
    color: #FFFFFF !important;
    border: 1px solid #333 !important;
    border-radius: 8px !important;
}}

/* Success/error messages */
.stAlert {{
    background-color: #1E1E1E !important;
    color: #FFFFFF !important;
}}
</style>
""", unsafe_allow_html=True)

# ======= GOOGLE SHEETS HELPER =======
def log_to_gsheet(player_info, domain_scores, validity_scores):
    """Append one assessment result to Google Sheets with proper column order"""
    try:
        # Define Google API scopes
        SCOPES = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = Credentials.from_service_account_info(
            st.secrets["google_service_account"],
            scopes=SCOPES
        )
        client = gspread.authorize(creds)

        # Open your Google Sheet
        sheet = client.open("Footpsy - Football Psychological Assessment Database").sheet1

        # --- Column order as per your Google Sheet ---
        ordered_domains = [
            "Drive & Commitment",
            "Competitive Edge",
            "Resilience Under Pressure",
            "Learning & Adaptability",
            "Focus & Game Intelligence",
            "Team Orientation & Coachability",
            "Emotional Regulation"
        ]

        # --- Build the row in the same order as your sheet header ---
        row = [
            datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            player_info.get("name", "N/A"),
            player_info.get("id", "N/A"),
            player_info.get("team", "N/A"),
            player_info.get("position", "N/A"),
            player_info.get("dob", "N/A"),
            player_info.get("age", "N/A"),
        ]

        # Add domain scores in the correct order
        for domain in ordered_domains:
            val = domain_scores.get(domain, "")
            row.append(round(val, 2) if isinstance(val, (int, float)) else "")

        # Add validity & quality checks
        row.extend([
            validity_scores.get("IM", ""),
            validity_scores.get("Inconsistency", ""),
            validity_scores.get("Longstring", ""),
            validity_scores.get("AttentionPass", "")
        ])

        # Append the row
        sheet.append_row(row)
        st.session_state["log_status"] = "success"

    except Exception as e:
        st.session_state["log_status"] = f"failed: {e}"


# ======= SETUP =======
BASE = os.path.dirname(__file__)
mapping = pd.read_csv(os.path.join(BASE, "assets", "scales_mapping.csv"))
map_dict = {}
for _, r in mapping.iterrows():
    map_dict.setdefault(r['Scale'], []).append(int(r['Item']))

reverse_items = [2,6,7,10,14,16,20,21,22,26,31,36,38,42,45,50,54,59,13,43]
im_items = map_dict.get("Impression Management", [])
inconsistency_pairs = [(1,42),(2,47),(15,22),(16,18)]

# --- Sample Questions ---
questions = {
1:"I can stay calm when my team concedes a goal late in the game.",
2:"I sometimes lose focus when training becomes repetitive.",
3:"I am always fair and respectful to everyone on and off the pitch.",
4:"I stay aware of my positioning even when I’m tired.",
5:"I recover quickly from mistakes during a match.",
6:"I never lose my temper, no matter what happens.",
7:"I get frustrated when others don’t play the way I want.",
8:"I am answering this questionnaire honestly and carefully.",
9:"I enjoy competing against players who are better than me.",
10:"I find it hard to regain confidence after a poor performance.",
11:"I’m willing to make personal sacrifices to improve as a player.",
12:"I encourage teammates even when I’m not playing well.",
13:"I’ve never made a mistake that cost my team a goal.",
14:"I look for new ways to stay ahead technically and tactically.",
15:"I can control my emotions when opponents try to provoke me.",
16:"I resist tactical changes because they confuse me.",
17:"I mentally prepare myself to outwork and outthink my opponent.",
18:"I’m open to trying new playing styles or positions if the team needs it.",
19:"I stay motivated even when I’m not in the starting lineup.",
20:"I sometimes make impulsive decisions under pressure.",
21:"I never disagree with my coach.",
22:"I sometimes lose my temper when things go wrong.",
23:"I hate being second best.",
24:"I always give my full effort, even in routine training sessions.",
25:"I respect my teammates regardless of their ability level.",
26:"I lose focus easily when things aren’t going my way.",
27:"I can quickly shift my mindset after making a mistake.",
28:"I’m quick to adapt when tactics change during a game.",
29:"I’ve never missed a training session without a valid reason.",
30:"I can read the flow of the game and anticipate what’s next.",
31:"I stick to what’s comfortable rather than learning new skills.",
32:"I know how to calm myself before important matches.",
33:"I handle setbacks and criticism without losing focus.",
34:"I enjoy being where the action is.",
35:"I am organized and keep myself disciplined.",
36:"I have never complained or felt frustrated during tough training.",
37:"I adapt my playstyle to suit what the team needs.",
38:"I sometimes lose motivation during long training periods.",
39:"I act on my instincts when I have to make quick decisions.",
40:"I feel proud when I outperform stronger opponents.",
41:"I help lift the team’s mood after setbacks.",
42:"I let small setbacks affect my confidence for too long.",
43:"I push myself to maintain high fitness levels all year round.",
44:"I take care not to injure opponents.",
45:"I find it hard to accept tactical instructions I don’t agree with.",
46:"I’m confident in my ability to perform under pressure.",
47:"I always give 100% effort in every single session.",
48:"I can quickly switch my focus between attack and defense.",
49:"I know how to calm my nerves before kickoff.",
50:"I act selfishly to get ahead in my career.",
51:"I handle pressure situations better than most players.",
52:"I can quickly adapt when the coach changes tactics mid-game.",
53:"I follow a healthy lifestyle.",
54:"I get angry when referees make unfair decisions.",
55:"I ask my coaches for feedback on how I can improve.",
56:"I’m able to laugh at myself after a bad performance.",
57:'Please select "Agree" for this item.',
58:"I like to give orders and take charge when needed.",
59:"I feel anxious before important matches.",
60:"I show total commitment to developing as a footballer."
}

# ======= SESSION STATE =======
if 'page' not in st.session_state: st.session_state.page = 1
if 'qpage' not in st.session_state: st.session_state.qpage = 1

# ======= PAGE 1: ATHLETE INFO =======
if st.session_state.page == 1:
    st.title("🏆 FOOTPSY — Football Psychological Assessment")

    logo_path = os.path.join(BASE, "assets", "footpsylogo.png")
    if os.path.exists(logo_path):
        st.image(logo_path, width=180)
    st.subheader("Athlete Information")

    def sticky_warning(text):
        st.markdown(f"<div style='color:red; font-size:0.9em; position:sticky;'>{text}</div>", unsafe_allow_html=True)

    # === Row 1: Player Name + Player ID ===
    col1, col2 = st.columns(2)
    with col1:
        st.session_state.player_name = st.text_input("Player Name", st.session_state.get("player_name", ""))
        if not st.session_state.player_name:
            sticky_warning("⚠️ Please fill this field, put N/A if unsure.")

    with col2:
        def generate_player_id():
            rand = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
            now = datetime.datetime.now()
            return f"FPY-{now.month:02d}-{now.year}-{rand}"

        st.session_state.player_id = st.text_input("Player ID", st.session_state.get("player_id", ""), placeholder="Auto-generated if left blank")
        st.markdown("<span style='color:gray; font-size:0.8em;'>Leave blank if unsure — ID will be generated automatically.</span>", unsafe_allow_html=True)
        if not st.session_state.player_id:
            st.session_state.player_id = generate_player_id()

    # === Row 2: Team Name + Position ===
    col3, col4 = st.columns(2)
    with col3:
        st.session_state.team_name = st.text_input("Team Name", st.session_state.get("team_name", ""))
        if not st.session_state.team_name:
            sticky_warning("⚠️ Please fill this field, put N/A if unsure.")

    with col4:
        st.session_state.player_position = st.text_input("Position", st.session_state.get("player_position", ""))
        if not st.session_state.player_position:
            sticky_warning("⚠️ Please fill this field, put N/A if unsure.")

    # === Row 3: DOB + Auto Age ===
    col5, col6 = st.columns(2)
    with col5:
        today = datetime.date.today()
        st.session_state.dob = st.date_input("Date of Birth (DD/MM/YYYY)", value=st.session_state.get("dob", today),
                                             format="DD/MM/YYYY", min_value=datetime.date(1970, 1, 1), max_value=today)
    with col6:
        dob = st.session_state.dob
        player_age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
        st.session_state.player_age = player_age
        st.text_input("Age", value=str(player_age), disabled=True)

    # === Navigation ===
    all_filled = all([
        st.session_state.player_name.strip(),
        st.session_state.team_name.strip(),
        st.session_state.player_position.strip(),
        st.session_state.dob is not None
    ])

    start_disabled = not all_filled
    if st.button("Start the assessment", disabled=start_disabled):
        st.session_state.page = 2
        st.session_state.qpage = 1
        st.rerun()

    if start_disabled:
        st.caption("Please fill all required fields before starting the assessment")


# ======= PAGES 2–7: QUESTIONS =======
if st.session_state.page >= 2 and st.session_state.page <= 7:
    st.title("⚽ FOOTPSY — Assessment")
    st.markdown(
        "**Purpose:** Measures key psychological skills such as drive, resilience, focus, and adaptability.\n\n"
        "**Instructions:** Read each statement and select how true it is for you (1–5)."
    )

    q_per_page = 10
    total_q = len(questions)
    total_qpages = (total_q + q_per_page - 1) // q_per_page
    qpage = st.session_state.qpage
    start_q, end_q = (qpage - 1) * q_per_page + 1, min(qpage * q_per_page, total_q)

    st.subheader(f"Questions {start_q}–{end_q}  (Page {qpage}/{total_qpages})")

    for i in range(start_q, end_q + 1):
        if f"q{i}" not in st.session_state: st.session_state[f"q{i}"] = 0

    with st.form(key=f"form_page_{qpage}"):
        st.markdown("### Answer the following questions:")

        response_labels = [
            "Strongly Disagree",
            "Disagree",
            "Neutral",
            "Agree",
            "Strongly Agree"
        ]

        for i in range(start_q, end_q + 1):
            existing = st.session_state.get(f"q{i}", 0)
            default_idx = (existing - 1) if existing in [1, 2, 3, 4, 5] else 2

            st.markdown(f"**{i}. {questions[i]}**")
            st.radio(
                "Your answer:",
                options=response_labels,
                key=f"form_q{i}",
                index=default_idx,
                horizontal=True,
                label_visibility="collapsed"
            )
            st.markdown("---")  # visual divider between questions

        submitted = st.form_submit_button("💾 Save & Next")

    back_col, spacer, next_col = st.columns([1,6,1])
    with back_col:
        if st.button("⬅ Back"):
            if st.session_state.qpage > 1:
                st.session_state.qpage -= 1
            else:
                st.session_state.page = 1
            st.rerun()

    if submitted:
        incomplete = False
        label_to_num = {
            "Strongly Disagree": 1,
            "Disagree": 2,
            "Neutral": 3,
            "Agree": 4,
            "Strongly Agree": 5
        }

        for i in range(start_q, end_q + 1):
            val = st.session_state.get(f"form_q{i}", None)
            if val is None:
                incomplete = True
                break

        if incomplete:
            st.warning("⚠️ Please answer all questions on this page before continuing.")
        else:
            for i in range(start_q, end_q + 1):
                label = st.session_state.get(f"form_q{i}")
                st.session_state[f"q{i}"] = label_to_num.get(label, 0)
            if qpage < total_qpages:
                st.session_state.qpage += 1
            else:
                st.session_state.page = 8
            st.rerun()

# ======= PAGE 8: RESULTS =======
if st.session_state.page == 8:
    st.title("📊 Results & Report")
    responses = {i: st.session_state.get(f"q{i}", 0) for i in range(1,61)}
    domain_means = compute_domain_means(responses, map_dict, reverse_items)
    im_avg = compute_im_score(responses, im_items, reverse_items) / len(im_items)
    inconsistency = inconsistency_index(responses, inconsistency_pairs)
    long_run = max_longstring(responses)
    att_pass = (responses.get(8)==4) and (responses.get(57)==4)
    adjusted = adjust_for_im(domain_means, im_avg, len(im_items))

    st.subheader("Results Summary")
    perf_scales = [s for s in adjusted.keys() if s not in ['Impression Management','Attention Checks']]
    cols = st.columns(2)
    for i,k in enumerate(perf_scales):
        cols[i%2].metric(k, f"{adjusted[k]:.2f}")

    st.markdown("**Validity & Quality**")
    st.write(f"IM: {im_avg:.2f} ; Inconsistency index: {inconsistency} ; Longstring: {long_run} ; Attention pass: {att_pass}")

    # Prepare info for logging
    player_info = {
        "name": st.session_state.get("player_name", "N/A"),
        "id": st.session_state.get("player_id", "N/A"),
        "team": st.session_state.get("team_name", "N/A"),
        "position": st.session_state.get("player_position", "N/A"),
        "dob": st.session_state.get("dob", "").strftime("%d/%m/%Y"),
        "age": st.session_state.get("player_age", "N/A"),
    }

    validity_scores = {
        "IM": im_avg,
        "Inconsistency": inconsistency,
        "Longstring": long_run,
        "AttentionPass": att_pass
    }

    # === Log results to Google Sheets ===
    log_to_gsheet(player_info, adjusted, validity_scores)

    # === Generate and Download PDF Report ===
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    logo_path = os.path.join(BASE, "assets", "footpsylogo.png")
    if os.path.exists(logo_path):
        c.drawImage(logo_path, 40, height - 110, width=120, preserveAspectRatio=True)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(180, height - 60, f"FOOTPSY — Individual Report")
    c.setFont("Helvetica", 10)
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    c.drawString(40, height - 120, f"Date: {now}")

    player_name = st.session_state.get("player_name", "N/A")
    player_id = st.session_state.get("player_id", "N/A")
    team_name = st.session_state.get("team_name", "N/A")
    player_position = st.session_state.get("player_position", "N/A")
    dob = st.session_state.get("dob", None)
    player_age = (datetime.date.today().year - dob.year) if dob else "N/A"

    c.drawString(40, height - 135, f"Player: {player_name}  |  ID: {player_id}")
    c.drawString(40, height - 150, f"Team: {team_name}  |  Position: {player_position}")
    c.drawString(40, height - 165, f"Date of Birth: {dob.strftime('%d/%m/%Y') if dob else 'N/A'}  |  Age: {player_age}")
    y = height - 195
    for k in perf_scales:
        c.drawString(40, y, f"{k}: {adjusted[k]:.2f}")
        y -= 14
    y -= 8
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, y, "Validity & Quality Checks")
    y -= 14
    c.setFont("Helvetica", 10)
    c.drawString(40, y,
                 f"IM: {im_avg:.2f} ; Inconsistency index: {inconsistency} ; Longstring: {long_run} ; Attention pass: {att_pass}")
    y -= 24
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, y, "Actionable Recommendations")
    y -= 14
    recos = [
        "Introduce breathing and visualization routines to improve focus.",
        "Use pressure-simulation drills to improve resilience.",
        "Set progressive measurable goals to leverage drive and commitment.",
        "Include short reset routines after mistakes."
    ]
    c.setFont("Helvetica", 10)
    for r in recos:
        c.drawString(40, y, f"• {r}")
        y -= 12
    c.save()
    buffer.seek(0)


    # === Do another test button (appears only on final page, before download button) ===
    restart = st.button("🏠 Do another test")

    if restart:
        # Clear everything and immediately rerun BEFORE re-rendering download button
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.session_state.page = 1
        st.session_state.qpage = 1
        st.rerun()

    # === Single visible download button ===
    st.download_button(
        label="📄 Download PDF Report",
        data=buffer,
        file_name=f"FOOTPSY_Report_{player_name}.pdf",
        mime="application/pdf"
    )


