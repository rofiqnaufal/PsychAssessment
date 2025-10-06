import streamlit as st
import pandas as pd, numpy as np, os, datetime
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.utils import ImageReader
from scoring import compute_domain_means, compute_im_score, inconsistency_index, max_longstring, adjust_for_im

st.set_page_config(page_title="FOOTPSY Assessment", layout="wide")

primary_green = "#4CAF50"
st.markdown(f"""
    <style>
    .reportview-container {{background-color: #111111;}}
    .main {{color: #FFFFFF;}}
    .stButton>button {{background-color: {primary_green}; color: white;}}
    .stSlider>div>div>div>input {{accent-color: {primary_green};}}
    .stMarkdown {{color: #FFFFFF}}
    </style>
    """, unsafe_allow_html=True)

BASE = os.path.dirname(__file__)
mapping_path = os.path.join(BASE, "assets", "scales_mapping.csv")
mapping_df = pd.read_csv(mapping_path)
mapping = {}
for _, r in mapping_df.iterrows():
    mapping.setdefault(r['Scale'], []).append(int(r['Item']))

reverse_items = [2,6,7,10,14,16,20,21,22,26,31,36,38,42,45,50,54,59,13,43]
im_items = mapping.get("Impression Management", [])
attention_items = mapping.get("Attention Checks", [])
inconsistency_pairs = [(1,42),(2,47),(15,22),(16,18)]

st.title("🏆 FOOTPSY — Football Psychological Assessment")
logo_path = os.path.join(BASE, "assets", "footpsylogo.png")
if os.path.exists(logo_path):
    st.image(logo_path, width=180)

st.subheader("Athlete Information")
player_name = st.text_input("Player Name")
player_id = st.text_input("Player ID")
team_name = st.text_input("Team/Club")
player_position = st.text_input("Position")
player_age = st.number_input("Age", min_value=10, max_value=45, value=20)


st.markdown("""
**Purpose:**  
This assessment measures key psychological skills that influence football performance — such as drive, resilience, focus, and adaptability.  
Please answer each statement honestly based on how you typically think, feel, and behave.  
There are no right or wrong answers.
""")


if st.checkbox("Load demo athlete responses (for testing)"):
    demo = pd.read_csv(os.path.join(BASE, "demo_data.csv"))
    sel = st.selectbox("Choose a demo athlete", demo['Athlete'].tolist())
    row = demo[demo['Athlete']==sel].iloc[0]
    st.subheader("Demo athlete domain scores")
    for col in ['Drive_Commitment','Competitive_Edge','Resilience_Under_Pressure','Learning_Adaptability','Focus_Game_Intelligence','Team_Orientation','Emotional_Regulation']:
        st.metric(col.replace('_',' '), f"{row[col]:.2f}")
    if st.button("Generate demo PDF report"):
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4
        c.drawImage(logo_path, 40, height-100, width=120, preserveAspectRatio=True)
        c.setFont("Helvetica-Bold", 14)
        c.drawString(180, height-60, f"FOOTPSY — Individual Report")
        c.setFont("Helvetica", 10)
        c.drawString(40, height-120, f"Athlete: {row['Athlete']}    Role: {row['Role']}    Date: {row['Date']}")
        y = height-150
        for col in ['Drive_Commitment','Competitive_Edge','Resilience_Under_Pressure','Learning_Adaptability','Focus_Game_Intelligence','Team_Orientation','Emotional_Regulation']:
            c.drawString(40, y, f"{col.replace('_',' ')}: {row[col]:.2f}")
            y -= 14
        c.save()
        buffer.seek(0)
        st.download_button("Download demo PDF", buffer, file_name=f"report_{row['Athlete']}.pdf", mime="application/pdf")
    st.stop()

st.subheader("Instructions")
st.markdown("Rate how true each statement is for you on a 1-5 scale: 1=Strongly Disagree ... 5=Strongly Agree.")

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

st.subheader("Questionnaire")
responses = {}
with st.form(key='qform'):
    cols = st.columns(2)
    for i in range(1,61):
        col = cols[i%2]
        responses[i] = col.selectbox(f"{i}. {questions[i]}", options=[1,2,3,4,5], index=2, key=f"q{i}")
    submit = st.form_submit_button("Submit and Generate Report")

if submit:
    domain_means = compute_domain_means(responses, mapping, reverse_items)
    im_sum = compute_im_score(responses, im_items, reverse_items)
    inconsistency = inconsistency_index(responses, inconsistency_pairs)
    long_run = max_longstring(responses)
    att_pass = (responses.get(8)==4) and (responses.get(57)==4)
    adjusted = adjust_for_im(domain_means, im_sum, len(im_items))
    st.subheader("Results Summary")
    cols = st.columns(2)
    perf_scales = [s for s in adjusted.keys() if s not in ['Impression Management','Attention Checks']]
    for i,k in enumerate(perf_scales):
        cols[i%2].metric(k, f"{adjusted[k]:.2f}")
    st.markdown("**Validity & Quality**")
    st.write(f"IM sum: {im_sum} ; Inconsistency index: {inconsistency} ; Longstring: {long_run} ; Attention pass: {att_pass}")
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4
    c.drawImage(logo_path, 40, height-110, width=120, preserveAspectRatio=True)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(180, height-60, f"FOOTPSY — Individual Report")
    c.setFont("Helvetica", 10)
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    c.drawString(40, height - 120, f"Date: {now}")
    c.drawString(40, height - 135, f"Player: {player_name or 'N/A'}  |  ID: {player_id or 'N/A'}  |  Age: {player_age}")
    c.drawString(40, height - 150, f"Team: {team_name or 'N/A'}  |  Position: {player_position or 'N/A'}")
    y = height - 180
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
    st.download_button("📄 Download PDF Report", buffer, file_name="FOOTPSY_report.pdf", mime="application/pdf")
