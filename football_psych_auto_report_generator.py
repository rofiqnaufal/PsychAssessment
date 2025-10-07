import streamlit as st
import pandas as pd, numpy as np, os, datetime, random, string
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from scoring import compute_domain_means, compute_im_score, inconsistency_index, max_longstring, adjust_for_im

st.set_page_config(page_title="FOOTPSY Assessment", layout="wide")

primary_green = "#4CAF50"
st.markdown(f"""
<style>
.reportview-container {{background-color: #111111;}}
.main {{color: #FFFFFF;}}
.stButton>button {{background-color: {primary_green}; color: white;}}
.stMarkdown {{color: #FFFFFF}}
</style>
""", unsafe_allow_html=True)

BASE = os.path.dirname(__file__)
mapping = pd.read_csv(os.path.join(BASE, "assets", "scales_mapping.csv"))
map_dict = {}
for _, r in mapping.iterrows():
    map_dict.setdefault(r['Scale'], []).append(int(r['Item']))

reverse_items = [2,6,7,10,14,16,20,21,22,26,31,36,38,42,45,50,54,59,13,43]
im_items = map_dict.get("Impression Management", [])
attention_items = map_dict.get("Attention Checks", [])
inconsistency_pairs = [(1,42),(2,47),(15,22),(16,18)]

questions = {}
# create a sample questions dict
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
57:'Please select \"Agree\" for this item.',
58:"I like to give orders and take charge when needed.",
59:"I feel anxious before important matches.",
60:"I show total commitment to developing as a footballer."
}

# === Session State Management ===
if 'page' not in st.session_state:
    st.session_state.page = 1
if 'qpage' not in st.session_state:
    st.session_state.qpage = 1

def next_page():
    st.session_state.qpage += 1

def prev_page():
    if st.session_state.qpage > 1:
        st.session_state.qpage -= 1


# PAGE 1
if st.session_state.page == 1:
    st.title("🏆 FOOTPSY — Football Psychological Assessment")
    logo_path = os.path.join(BASE, "assets", "footpsylogo.png")
    if os.path.exists(logo_path):
        st.image(logo_path, width=180)
    st.subheader("Athlete Information")


    def sticky_warning(text):
        st.markdown(f"<div style='color:red; font-size:0.9em; position:sticky;'>{text}</div>", unsafe_allow_html=True)


    # === Player Name ===
    player_name = st.text_input("Player Name", key="player_name")
    if not player_name:
        sticky_warning("⚠️ Please fill this field, put N/A if unsure.")


    # === Player ID (auto-generate if blank) ===
    def generate_player_id():
        rand = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        now = datetime.datetime.now()
        return f"FPY-{now.month:02d}-{now.year}-{rand}"


    player_id = st.text_input("Player ID", key="player_id", placeholder="Auto-generated if left blank")
    st.markdown(
        "<span style='color:gray; font-size:0.8em;'>Leave blank if unsure — ID will be generated automatically.</span>",
        unsafe_allow_html=True)
    if not player_id:
        player_id = generate_player_id()

    # === Team ===
    team_name = st.text_input("Team Name", key="team_name")
    if not team_name:
        sticky_warning("⚠️ Please fill this field, put N/A if unsure.")

    # === Position ===
    player_position = st.text_input("Position", key="player_position")
    if not player_position:
        sticky_warning("⚠️ Please fill this field, put N/A if unsure.")

    # === DOB ===
    today = datetime.date.today()
    dob = st.date_input("Date of Birth (DD/MM/YYYY)", key="dob", format="DD/MM/YYYY",
                        min_value=datetime.date(1970, 1, 1), max_value=today)

    if not dob:
        sticky_warning("⚠️ Please select your date of birth.")
        player_age = ""
    else:
        player_age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))

    # === Age auto-calculated ===
    player_age_display = st.text_input("Age", value=str(player_age), disabled=True)

    all_filled = all([
        player_name.strip(),
        team_name.strip(),
        player_position.strip(),
        dob is not None
    ])

    start_disabled = not all_filled
    if st.button("Start the assessment", disabled=start_disabled, on_click=next_page):
        pass
    if start_disabled:
        st.caption("Please fill all required fields before starting the assessment")

# PAGES 2..7: questionnaire
if st.session_state.page >=2 and st.session_state.page <=7:
    st.title("⚽ FOOTPSY — Assessment")
    st.markdown("**Purpose:** This assessment measures key mental attributes such as drive, focus, resilience, and adaptability.\n\n**Instructions:** Read each statement and click the box that best describes how true it is for you.\n\nScale: 1=Strongly Disagree, 2=Disagree, 3=Neutral, 4=Agree, 5=Strongly Agree")

    questions_per_page = 10
    total_questions = len(questions)
    total_qpages = (total_questions + questions_per_page - 1) // questions_per_page
    qpage = st.session_state.qpage
    start_q = (qpage - 1) * questions_per_page + 1
    end_q = min(start_q + questions_per_page - 1, total_questions)

    st.subheader(f"Questions {start_q} – {end_q}  (Page {qpage} of {total_qpages})")

    # header row
    cols = st.columns([3,1,1,1,1,1,1])
    cols[0].markdown("**Item**")
    cols[1].markdown("**1**")
    cols[2].markdown("**2**")
    cols[3].markdown("**3**")
    cols[4].markdown("**4**")
    cols[5].markdown("**5**")

    # ensure responses exist
    for i in range(1, total_questions+1):
        if f"q{i}" not in st.session_state:
            st.session_state[f"q{i}"] = 0

    # display questions
    for i in range(start_q, end_q+1):
        row_cols = st.columns([3,1,1,1,1,1,1])
        row_cols[0].write(f"{i}. {questions[i]}")
        for opt in range(1,6):
            label = "●" if st.session_state.get(f"q{i}") == opt else "○"
            key = f"btn_{i}_{opt}"
            if row_cols[opt].button(label, key=key):
                st.session_state[f"q{i}"] = opt

        # === Navigation Buttons with Validation ===
        # Determine which questions are on this page
        current_items = range(start_q, end_q + 1)
        answered = all(st.session_state.get(f"q{i}") != 0 for i in current_items)

        nav_cols = st.columns([1, 5, 1])

        with nav_cols[0]:
            if st.button("⬅ Back", disabled=(st.session_state.qpage == 1)):
                st.session_state.qpage -= 1

        with nav_cols[2]:
            if st.session_state.qpage < total_qpages:
                if st.button("Next ➡", disabled=not answered):
                    st.session_state.qpage += 1
            else:
                if st.button("Submit and Generate Report", disabled=not answered):
                    st.session_state.page = 8

        if not answered:
            st.markdown(
                "<div style='color:red; font-size:0.9em;'>⚠️ Please answer all questions on this page before proceeding.</div>",
                unsafe_allow_html=True
            )

# PAGE 8 results
if st.session_state.page == 8:
    st.title("📊 Results & Report")
    responses = {i: st.session_state.get(f"q{i}", 0) for i in range(1,61)}
    domain_means = compute_domain_means(responses, map_dict, reverse_items)
    im_sum = compute_im_score(responses, im_items, reverse_items)
    inconsistency = inconsistency_index(responses, inconsistency_pairs)
    long_run = max_longstring(responses)
    att_pass = (responses.get(8)==4) and (responses.get(57)==4)
    adjusted = adjust_for_im(domain_means, im_sum, len(im_items))

    st.subheader("Results Summary")
    perf_scales = [s for s in adjusted.keys() if s not in ['Impression Management','Attention Checks']]
    cols = st.columns(2)
    for i,k in enumerate(perf_scales):
        cols[i%2].metric(k, f"{adjusted[k]:.2f}")

    st.markdown("**Validity & Quality**")
    st.write(f"IM sum: {im_sum} ; Inconsistency index: {inconsistency} ; Longstring: {long_run} ; Attention pass: {att_pass}")

    if st.button("Download PDF Report"):
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4
        logo_path = os.path.join(BASE, "assets", "footpsylogo.png")
        if os.path.exists(logo_path):
            c.drawImage(logo_path, 40, height-110, width=120, preserveAspectRatio=True)
        c.setFont("Helvetica-Bold", 14)
        c.drawString(180, height-60, f"FOOTPSY — Individual Report")
        c.setFont("Helvetica", 10)
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        c.drawString(40, height - 120, f"Date: {now}")
        player_name = st.session_state.get("player_name","N/A")
        player_id = st.session_state.get("player_id", "N/A")
        team_name = st.session_state.get("team_name", "N/A")
        player_position = st.session_state.get("player_position","N/A")
        dob = st.session_state.get("dob", None)
        player_age = st.session_state.get("player_age_display","N/A")
        c.drawString(40, height - 135, f"Player: {player_name}  |  ID: {player_id}")
        c.drawString(40, height - 150, f"Team: {team_name}  |  Position: {player_position}")
        c.drawString(40, height - 165, f"Date of Birth: {dob.strftime('%d/%m/%Y') if dob else 'N/A'}  |  Age: {player_age if player_age else 'N/A'} years")
        y = height - 195
        for k in ['Drive & Commitment','Competitive Edge','Resilience Under Pressure','Learning & Adaptability','Focus & Game Intelligence','Team Orientation & Coachability','Emotional Regulation']:
            val = adjusted.get(k, None)
            c.drawString(40, y, f"{k}: {val if val is not None else 'N/A'}")
            y -= 14
        y -= 8
        c.setFont("Helvetica-Bold", 11)
        c.drawString(40, y, "Validity & Quality Checks")
        y -= 14
        c.setFont("Helvetica", 10)
        c.drawString(40, y, f"IM sum: {im_sum} ; Inconsistency index: {inconsistency} ; Longstring: {long_run} ; Attention pass: {att_pass}")
        y -= 24
        c.setFont("Helvetica-Bold", 11)
        c.drawString(40, y, "Actionable Recommendations")
        y -= 14
        recos = ["Introduce breathing and visualization routines to improve focus.","Use pressure-simulation drills to improve resilience.","Set progressive measurable goals to leverage drive and commitment.","Include short reset routines after mistakes."]
        c.setFont("Helvetica", 10)
        for r in recos:
            c.drawString(40, y, f"• {r}")
            y -= 12
        c.save()
        buffer.seek(0)
        st.download_button("Download PDF", buffer, file_name="FOOTPSY_report.pdf", mime="application/pdf")
