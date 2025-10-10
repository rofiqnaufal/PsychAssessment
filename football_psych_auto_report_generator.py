import streamlit as st
import pandas as pd, os, datetime, random, string
from io import BytesIO
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from scoring import compute_domain_means, compute_im_score, inconsistency_index, max_longstring
import gspread
from google.oauth2.service_account import Credentials
try:
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaIoBaseUpload
except ImportError:
    st.error("googleapiclient not installed. Please add 'google-api-python-client==2.108.0' to requirements.txt")

# ======= PAGE CONFIG & STYLING =======
BASE = os.path.dirname(__file__)

st.set_page_config(
    page_title="FOOTPSY Assessment",
    page_icon=os.path.join(BASE, "assets", "footpsylogo.png"),  # ✅ custom favicon
    layout="wide",
    initial_sidebar_state="collapsed"
)

primary_green = "#4CAF50"
# Force dark theme in Streamlit config
st.set_page_config(
    page_title="FOOTPSY Assessment",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Additional theme forcing
try:
    st._config.set_option('theme.base', 'dark')
    st._config.set_option('theme.primaryColor', primary_green)
    st._config.set_option('theme.backgroundColor', '#111111')
    st._config.set_option('theme.secondaryBackgroundColor', '#1E1E1E')
    st._config.set_option('theme.textColor', '#FFFFFF')
except:
    pass

# ======= GOOGLE SHEETS HELPER =======
def log_to_gsheet(player_info, domain_scores, validity_scores, responses, pdf_link=""):
    """Append one assessment result to Google Sheets with PDF link"""
    try:
        SCOPES = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = Credentials.from_service_account_info(
            st.secrets["google_service_account"],
            scopes=SCOPES
        )
        client = gspread.authorize(creds)

        sheet = client.open("Footpsy - Football Psychological Assessment Database").sheet1

        # --- Build the row ---
        row = [
            datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            player_info.get("name", "N/A"),
            player_info.get("id", "N/A"),
            player_info.get("team", "N/A"),
            player_info.get("position", "N/A"),
            player_info.get("dob", "N/A"),
            player_info.get("age", "N/A"),
        ]

        # Add domain scores
        ordered_domains = [
            "Resilience", "Self-Discipline", "Competitiveness",
            "Achievement Motivation", "Focus & Concentration",
            "Confidence", "Emotional Control", "Coachability & Adaptability",
            "Risk-Taking", "Team Orientation", "Leadership & Influence",
            "Aggressiveness & Bravery"
        ]

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

        # Add all individual question responses
        for i in range(1, 67):
            row.append(responses.get(i, ""))

        # Add PDF link
        row.append(pdf_link if pdf_link else "Not saved")

        # Append the row
        sheet.append_row(row)
        return True

    except Exception as e:
        st.error(f"Failed to log data: {e}")
        return False


def save_pdf_to_shared_drive(pdf_data, player_name, player_id):
    """Save PDF report to a Shared Drive"""
    try:
        SCOPES = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = Credentials.from_service_account_info(
            st.secrets["google_service_account"],
            scopes=SCOPES
        )

        # Build Drive API client
        drive_service = build('drive', 'v3', credentials=creds)

        # === REPLACE THIS WITH YOUR ACTUAL SHARED DRIVE ID ===
        SHARED_DRIVE_ID = "0AOT9SySfSgB9Uk9PVA"  # ← Replace with your actual Shared Drive ID

        # Create file metadata
        file_metadata = {
            'name': f"FOOTPSY_Report_{player_name}_{player_id}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf",
            'parents': [SHARED_DRIVE_ID]
        }

        # Create media upload
        media = MediaIoBaseUpload(
            pdf_data,
            mimetype='application/pdf',
            resumable=True
        )

        # Upload file to shared drive
        file = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            supportsAllDrives=True,  # Required for shared drives
            fields='id, webViewLink, webContentLink'
        ).execute()

        # Make the file publicly viewable
        drive_service.permissions().create(
            fileId=file['id'],
            body={'type': 'anyone', 'role': 'reader'},
            supportsAllDrives=True  # Required for shared drives
        ).execute()

        st.success("✅ Report saved!")
        return file['webViewLink']

    except Exception as e:
        st.error(f"Failed to save PDF: {e}")
        return None

# ======= SETUP =======
mapping = pd.read_csv(os.path.join(BASE, "assets", "scales_mapping.csv"))
map_dict = {}
for _, r in mapping.iterrows():
    map_dict.setdefault(r['Scale'], []).append(int(r['Item']))

reverse_items = [7, 14, 23, 25, 26, 30, 31, 34, 36, 37, 38, 39, 41, 44, 45, 47, 48, 49, 50, 55, 57, 61, 62, 63, 64]
im_items = map_dict.get("Impression Management", [])
inconsistency_pairs = [(17,64),(6,25),(22,39),(4,49)]

# --- Sample Questions ---
questions = {
    1: "I can maintain my focus on the game for the full 90 minutes, even when we are winning comfortably.",
    2: "I will often attempt a difficult through-pass or progressive pass, even if it might be intercepted. ",
    3: "I am confident that I can perform well even in a high-pressure match, like a cup final or a derby.",
    4: "I follow a strict routine for sleep, nutrition, and recovery, even on my days off.",
    5: "I feel just as much satisfaction from providing a crucial assist as I do from scoring a goal myself.",
    6: "I can stay calm and make rational decisions even when opponents are trying to provoke me.",
    7: "If I get beaten in a 1v1, my confidence drops and I become hesitant and worried next time I encounter a 1v1 again.",
    8: "I am comfortable being the one who gives instructions and organizes the team during a game.",
    9: "I get extra motivation from playing against opponents who are considered better than me.",
    10: "I am always willing to admit when I make a mistake.",
    11: "I enjoy trying creative flicks and tricks during a game if I see an opportunity.",
    12: "I am always willing to sacrifice my own positioning to cover for a teammate who has pushed forward.",
    13: "I have a specific technique that I use to calm myself down quickly when I feel frustration building.",
    14: "I sometimes skip the recommended cool-down or stretching after training if I'm feeling tired.",
    15: "I rarely let the referee's decisions affect my mood or my focus on the game.",
    16: "I set specific personal goals for myself for each season and review my progress regularly.",
    17: "I can shake off a bad pass or a missed tackle and focus on the next play immediately.",
    18: "This is an attention check. Please select 'Strongly Disagree'.",
    19: "I actively seek out feedback from my coaches on how I can improve, even after a good game.",
    20: "I will happily do the 'unseen' defensive work that might not get noticed by fans but helps the team win.",
    21: "I have never felt jealous of a teammate's success or recognition.",
    22: "I enjoy the challenge of learning a new playing position or tactical role.",
    23: "I believe it's always better to keep possession with a simple pass than to risk losing the ball with an ambitious one.",
    24: "I am always fully focused and give 100% effort in every training session, not just the ones before a big game.",
    25: "I often react impulsively in the heat of the moment and later regret my actions.",
    26: "I am just as satisfied with a good personal performance in a loss as I am with a win.",
    27: "If the game is on the line, I want to be the one taking the penalty/free-kick or having the decisive moment.",
    28: "I make a conscious effort to encourage teammates, especially when they are struggling or have made a mistake.",
    29: "When the opponent scores, it makes me more determined to make an immediate impact to turn things around.",
    30: "I sometimes lose track of my tactical position when I get tired in the last 15 minutes of a game.",
    31: "I avoid high-risk actions unless the odds of success are strongly in my favor.",
    32: "I am not intimidated by playing against opponents who are known for being physically stronger or more aggressive.",
    33: "I constantly compare my performance and statistics to my teammates and rivals.",
    34: "If I make an error in the first half, it's hard for me to perform well for the rest of the game.",
    35: "The feeling of mastering a new skill is one of the most rewarding parts of football for me.",
    36: "I get frustrated when a coach asks me to change a technique that I'm already comfortable with.",
    37: "I sometimes doubt my abilities when my team is about to face a much stronger opponent.",
    38: "After an opponent scores a goal, I find it difficult to regain my composure and focus.",
    39: "I prefer to stick to a familiar game plan rather than adapt to the specific strengths of our opponent.",
    40: "I always give 100% in every drill, regardless of how tired or unmotivated I feel.",
    41: "If a teammate makes a mistake that costs us a goal, I struggle to hide my frustration with them.",
    42: "I will voluntarily do extra training sessions to work on my weaknesses.",
    43: "I have a specific routine or technique to quickly refocus my mind if it starts to wander during a match.",
    44: "I am happy with my current ability level and don't feel a strong need to improve.",
    45: "I believe that technical skill and intelligence are far more important in football than physical aggression.",
    46: "Winning my individual battles on the pitch is just as important to me as the final score.",
    47: "I tend to avoid 50/50 challenges where I might get hurt.",
    48: "Once I've achieved a goal, I tend to relax my efforts rather than immediately set a new one.",
    49: "During the off-season, I find it difficult to maintain the same level of fitness and discipline.",
    50: "I am not particularly bothered by losing in training games or small-sided matches.",
    51: "I’ve never felt frustrated with a teammate, even after a costly mistake.",
    52: "I am always willing to put my body on the line, for example, by throwing myself to win a duel or block a shot.",
    53: "I enjoy the physical side of football and look for opportunities to win my individual duels.",
    54: "If the coach changes the game plan at halftime, I can quickly understand and execute the new instructions.",
    55: "I sometimes get frustrated when a teammate doesn’t pass the ball to me when I’m in a better position.",
    56: "I believe I have what it takes to succeed at the highest level of football.",
    57: "If I have a run of poor form, I start to question whether I'm good enough.",
    58: "I am driven by a need to see how good I can ultimately become.",
    59: "When I'm on the pitch, I can easily tune out distractions like the crowd or opponents' comments.",
    60: "To show you are paying attention, please select 'Agree' for this statement.",
    61: "I feel uncomfortable having to give critical feedback to a teammate, even if it would help the team.",
    62: "My primary personal goal is to be the star player of the team, even if the team doesn't win.",
    63: "I prefer to focus solely on my own performance and let others worry about organizing the team.",
    64: "If I make a mistake, I find it very difficult to stop thinking about it and focus on the next play.",
    65: "I will speak up in the dressing room to address issues or to motivate the group before an important match.",
    66: "When under pressure, I prefer to attempt a high-risk/ambitious play rather than play it safe."
}

# ======= SESSION STATE =======
if 'page' not in st.session_state: st.session_state.page = 1
if 'qpage' not in st.session_state: st.session_state.qpage = 1
if 'admin_authenticated' not in st.session_state: st.session_state.admin_authenticated = False

# ======= PAGE 1: ATHLETE INFO =======
if st.session_state.page == 1:
    st.title("🏆 FOOTPSY — Football Psychological Assessment")

    # Add SECURE admin access button
    with st.sidebar:
        st.markdown("---")
        st.subheader("Admin Access")

        # Password protection
        admin_password_input = st.text_input("Admin Password", type="password", placeholder="Enter admin password")

        if st.button("🔧 Admin Login"):
            # Use password from secrets.toml
            if admin_password_input == st.secrets.get("admin_password", "default_fallback_password"):
                st.session_state.admin_authenticated = True
                st.session_state.page = 9
                st.rerun()
            elif admin_password_input:  # Only show error if they actually entered something
                st.error("❌ Incorrect admin password")

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

    q_per_page = 11
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
    responses = {i: st.session_state.get(f"q{i}", 0) for i in range(1, 67)}
    domain_means = compute_domain_means(responses, map_dict, reverse_items)
    im_avg = compute_im_score(responses, im_items, reverse_items) / len(im_items)
    inconsistency = inconsistency_index(responses, inconsistency_pairs)
    long_run = max_longstring(responses)
    att_pass = (responses.get(18) == 1) and (responses.get(60) == 4)
    adjusted = domain_means

    # Define core scales (12 domains)
    core_scales = [
        "Resilience", "Self-Discipline", "Competitiveness",
        "Achievement Motivation", "Focus & Concentration",
        "Confidence", "Emotional Control", "Coachability & Adaptability",
        "Risk-Taking", "Team Orientation", "Leadership & Influence",
        "Aggressiveness & Bravery"
    ]

    st.subheader("Psychological Domain Scores")


    # Function to determine color based on score
    def get_score_color(score):
        if score >= 4.2:
            return "#4CAF50"  # Green for High
        elif score >= 3.0:
            return "#FFA500"  # Orange/Yellow for Moderate
        else:
            return "#FF4B4B"  # Red for Low


    # Function to create progress bar HTML
    def create_progress_bar(score, width=200, height=20):
        percentage = (score / 5.0) * 100
        color = get_score_color(score)
        return f"""
        <div style="width: {width}px; height: {height}px; background-color: #f0f0f0; border-radius: 10px; overflow: hidden; position: relative;">
            <div style="width: {percentage}%; height: 100%; background-color: {color}; border-radius: 10px; transition: width 0.3s ease;"></div>
            <div style="position: absolute; top: 0; left: 0; width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: bold; color: #333;">
                {score:.2f}/5.00
            </div>
        </div>
        """


    # Display core scales with progress bars in 2 columns
    cols = st.columns(2)
    for i, scale in enumerate(core_scales):
        score = domain_means.get(scale, 0)
        with cols[i % 2]:
            # Create a container for each scale
            with st.container():
                st.markdown(f"**{scale}**")

                # Create two columns: one for progress bar, one for interpretation
                bar_col, text_col = st.columns([2, 1])

                with bar_col:
                    st.markdown(create_progress_bar(score), unsafe_allow_html=True)

                with text_col:
                    if score >= 4.2:
                        st.markdown("<span style='color: #4CAF50; font-weight: bold;'>High</span>",
                                    unsafe_allow_html=True)
                    elif score >= 3.0:
                        st.markdown("<span style='color: #FFA500; font-weight: bold;'>Moderate</span>",
                                    unsafe_allow_html=True)
                    else:
                        st.markdown("<span style='color: #FF4B4B; font-weight: bold;'>Low</span>",
                                    unsafe_allow_html=True)

                st.markdown("---")

    # Validity scores (no progress bars)
    st.markdown("**Validity & Quality Checks**")
    st.write(
        f"Impression Management: {im_avg:.2f} | Inconsistency: {inconsistency} | Longstring: {long_run} | Attention: {'PASS' if att_pass else 'FAIL'}")

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

    # === Generate PDF Report ===
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    width, height = A4

    # === PDF STYLING CONSTANTS ===
    LEFT_MARGIN = 40
    RIGHT_MARGIN = width - 40
    LINE_HEIGHT = 14
    SECTION_SPACING = 20

    # Progress bar dimensions for PDF
    PROGRESS_BAR_WIDTH = 200
    PROGRESS_BAR_HEIGHT = 12


    def draw_header():
        """Draw the header with logo and title"""
        logo_path = os.path.join(BASE, "assets", "footpsylogo.png")
        if os.path.exists(logo_path):
            c.drawImage(logo_path, LEFT_MARGIN, height - 110, width=120, preserveAspectRatio=True)
        c.setFont("Helvetica-Bold", 16)
        c.drawString(180, height - 60, "FOOTPSY — Individual Psychological Report")
        c.setFont("Helvetica", 10)
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        c.drawString(LEFT_MARGIN, height - 85, f"Report Generated: {now}")


    player_name = st.session_state.get("player_name", "N/A")
    player_id = st.session_state.get("player_id", "N/A")
    team_name = st.session_state.get("team_name", "N/A")
    player_position = st.session_state.get("player_position", "N/A")
    dob = st.session_state.get("dob", None)
    player_age = (datetime.date.today().year - dob.year) if dob else "N/A"


    def draw_player_info(y_position):
        """Draw player information section"""
        c.setFont("Helvetica-Bold", 12)
        c.drawString(LEFT_MARGIN, y_position, "Player Information")
        y_position -= LINE_HEIGHT

        c.setFont("Helvetica", 10)
        info_lines = [
            f"Name: {player_name}",
            f"ID: {player_id}",
            f"Team: {team_name}",
            f"Position: {player_position}",
            f"Date of Birth: {dob.strftime('%d/%m/%Y') if dob else 'N/A'}",
            f"Age: {player_age}"
        ]

        for line in info_lines:
            c.drawString(LEFT_MARGIN, y_position, line)
            y_position -= LINE_HEIGHT

        return y_position - 10


    def draw_progress_bar(c, x, y, score, width=PROGRESS_BAR_WIDTH, height=PROGRESS_BAR_HEIGHT):
        """Draw a progress bar for PDF"""
        # Background
        c.setFillColorRGB(0.94, 0.94, 0.94)  # Light gray
        c.rect(x, y, width, height, fill=1, stroke=0)

        # Determine color
        if score >= 4.2:
            color = (0.3, 0.69, 0.3)  # Green
        elif score >= 3.0:
            color = (1.0, 0.65, 0.0)  # Orange
        else:
            color = (1.0, 0.29, 0.29)  # Red

        # Progress fill
        progress_width = (score / 5.0) * width
        c.setFillColorRGB(*color)
        c.rect(x, y, progress_width, height, fill=1, stroke=0)

        # Border
        c.setStrokeColorRGB(0.7, 0.7, 0.7)
        c.rect(x, y, width, height, fill=0, stroke=1)

        # Score text
        c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica-Bold", 8)
        text = f"{score:.2f}/5.00"
        text_width = c.stringWidth(text, "Helvetica-Bold", 8)
        c.drawString(x + (width - text_width) / 2, y + 2, text)


    def draw_domain_scores(y_position):
        """Draw domain scores section with progress bars"""
        c.setFont("Helvetica-Bold", 12)
        c.drawString(LEFT_MARGIN, y_position, "Psychological Domain Scores")
        y_position -= LINE_HEIGHT + 5

        c.setFont("Helvetica", 10)

        # Draw in two columns
        col_width = (RIGHT_MARGIN - LEFT_MARGIN) / 2
        column_gap = 20

        for i, scale in enumerate(core_scales):
            score = domain_means.get(scale, 0)

            # Determine column position
            if i % 2 == 0:
                col_x = LEFT_MARGIN
                item_y = y_position - (i // 2) * 35
            else:
                col_x = LEFT_MARGIN + col_width + column_gap
                item_y = y_position - ((i - 1) // 2) * 35

            # Scale name
            c.setFont("Helvetica-Bold", 9)
            c.drawString(col_x, item_y, scale)

            # Progress bar
            draw_progress_bar(c, col_x, item_y - 15, score)

            # Interpretation text
            c.setFont("Helvetica", 8)
            if score >= 4.2:
                interpretation = "High"
                c.setFillColorRGB(0.3, 0.69, 0.3)  # Green
            elif score >= 3.0:
                interpretation = "Moderate"
                c.setFillColorRGB(1.0, 0.65, 0.0)  # Orange
            else:
                interpretation = "Development Area"
                c.setFillColorRGB(1.0, 0.29, 0.29)  # Red

            c.drawString(col_x + PROGRESS_BAR_WIDTH + 5, item_y - 10, interpretation)
            c.setFillColorRGB(0, 0, 0)  # Reset to black

        # Calculate new y position (6 rows of content)
        return y_position - (len(core_scales) // 2 * 35) - 20


    def draw_validity_scores(y_position):
        """Draw validity and quality checks"""
        c.setFont("Helvetica-Bold", 12)
        c.drawString(LEFT_MARGIN, y_position, "Validity & Quality Checks")
        y_position -= LINE_HEIGHT

        c.setFont("Helvetica", 10)
        validity_lines = [
            f"Impression Management: {im_avg:.2f}",
            f"Inconsistency Index: {inconsistency}",
            f"Longest Straight Run: {long_run}",
            f"Attention Check: {'PASS' if att_pass else 'FAIL'}"
        ]

        for line in validity_lines:
            c.drawString(LEFT_MARGIN, y_position, line)
            y_position -= LINE_HEIGHT

        return y_position - 10


    def draw_question_responses(y_position):
        """Draw all question responses with abbreviated question text in 2 columns"""
        c.setFont("Helvetica-Bold", 12)
        c.drawString(LEFT_MARGIN, y_position, "Complete Question Responses")
        y_position -= LINE_HEIGHT

        # Define response labels for display
        response_labels = {
            1: "SD",  # Strongly Disagree
            2: "D",  # Disagree
            3: "N",  # Neutral
            4: "A",  # Agree
            5: "SA"  # Strongly Agree
        }

        # Setup two columns
        col_width = (RIGHT_MARGIN - LEFT_MARGIN) / 2
        column_gap = 20
        current_col = 0
        start_x = LEFT_MARGIN
        current_y = y_position

        # Column headers
        c.setFont("Helvetica-Bold", 9)
        c.drawString(start_x, current_y, "Question & Response")
        c.drawString(start_x + col_width + column_gap, current_y, "Question & Response")
        current_y -= LINE_HEIGHT

        c.setFont("Helvetica", 8)

        # Create abbreviated question texts
        abbreviated_questions = {
            1: "Maintain focus for full 90 minutes",
            2: "Attempt difficult progressive/through-passes",
            3: "Confident in high-pressure matches",
            4: "Strict sleep/nutrition/recovery routine",
            5: "Satisfaction from assists equals goals",
            6: "Stay calm when provoked",
            7: "Confidence drops after beaten in 1v1",
            8: "Comfortable giving instructions",
            9: "Motivated vs better opponents",
            10: "Willing to admit mistakes",
            11: "Enjoy creative flicks/tricks",
            12: "Sacrifice positioning to cover teammates",
            13: "Technique to calm frustration",
            14: "Skip cool-down if tired",
            15: "Referee decisions don't affect focus",
            16: "Set and review seasonal goals",
            17: "Shake off bad passes immediately",
            18: "Attention check: select Strongly Disagree",
            19: "Seek feedback after good games",
            20: "Do unseen defensive work",
            21: "Never jealous of teammates",
            22: "Enjoy learning new positions",
            23: "Prefer safe passes over risky ones",
            24: "100% effort in all training",
            25: "React impulsively and regret",
            26: "Satisfied with good performance in loss",
            27: "Want decisive moments",
            28: "Encourage struggling teammates",
            29: "Determined after opponent scores",
            30: "Lose tactical position when tired",
            31: "Avoid high-risk actions",
            32: "Not intimidated by physical opponents",
            33: "Compare stats with teammates",
            34: "Errors affect rest of game",
            35: "Reward from mastering new skills",
            36: "Frustrated by technique changes",
            37: "Doubt abilities vs stronger teams",
            38: "Difficulty refocusing after conceding",
            39: "Prefer familiar game plans",
            40: "100% in all drills",
            41: "Struggle to hide frustration with teammates",
            42: "Extra training for weaknesses",
            43: "Routine to refocus during matches",
            44: "Happy with current ability",
            45: "Skill over physical aggression",
            46: "Individual battles important",
            47: "Avoid 50/50 challenges",
            48: "Relax after achieving goals",
            49: "Off-season fitness difficult",
            50: "Not bothered by training losses",
            51: "Never frustrated with teammates",
            52: "Willing to put body on line",
            53: "Enjoy physical duels",
            54: "Quickly adapt to halftime changes",
            55: "Frustrated when not passed to",
            56: "Believe in highest level success",
            57: "Question ability after poor form",
            58: "Driven to maximize potential",
            59: "Tune out crowd/distractions",
            60: "Attention check: select Agree",
            61: "Uncomfortable giving critical feedback",
            62: "Want to be star player",
            63: "Focus on own performance only",
            64: "Difficulty moving past mistakes",
            65: "Speak up in dressing room",
            66: "Prefer high-risk plays under pressure"
        }

        # Draw all questions in 2 columns
        for q_num in range(1, 67):
            response_num = responses.get(q_num, 0)
            response_text = response_labels.get(response_num, "NR")
            question_abbr = abbreviated_questions.get(q_num, f"Q{q_num}")

            # Calculate position
            if current_col == 0:
                col_x = start_x
            else:
                col_x = start_x + col_width + column_gap

            # Draw the line
            line_text = f"Q{q_num:02d}: {question_abbr} [{response_text}]"
            c.drawString(col_x, current_y, line_text)

            # Move to next row/column
            current_col += 1
            if current_col >= 2:
                current_col = 0
                current_y -= LINE_HEIGHT

                # Check if we need a new page
                if current_y < 100:
                    c.showPage()
                    current_y = height - 50
                    c.setFont("Helvetica-Bold", 9)
                    c.drawString(start_x, current_y, "Question & Response")
                    c.drawString(start_x + col_width + column_gap, current_y, "Question & Response")
                    current_y -= LINE_HEIGHT
                    c.setFont("Helvetica", 8)

        # Add response key
        current_y -= 10
        c.setFont("Helvetica-Bold", 8)
        c.drawString(LEFT_MARGIN, current_y,
                     "Response Key: SD=Strongly Disagree, D=Disagree, N=Neutral, A=Agree, SA=Strongly Agree")
        current_y -= LINE_HEIGHT

        return current_y


    def draw_recommendations(y_position):
        """Draw actionable recommendations"""
        c.setFont("Helvetica-Bold", 12)
        c.drawString(LEFT_MARGIN, y_position, "Actionable Recommendations")
        y_position -= LINE_HEIGHT

        c.setFont("Helvetica", 10)

        # Generate personalized recommendations based on scores
        personalized_recos = []

        # Generate recommendations for each core scale
        for scale in core_scales:
            score = domain_means.get(scale, 0)
            if score < 3.0:
                personalized_recos.append(f"• Develop strategies to improve {scale.lower()}")
            elif score > 4.0:
                personalized_recos.append(f"• Leverage strong {scale.lower()} in team leadership")

        if not personalized_recos:
            personalized_recos = [
                "• Continue current development path with focus on maintaining strengths",
                "• Set specific performance targets for each psychological domain",
                "• Regular self-reflection on mental performance after each game",
                "• Seek regular feedback from coaches on psychological development"
            ]

        # Draw recommendations
        for reco in personalized_recos:
            if y_position < 100:  # Start new page if needed
                c.showPage()
                y_position = height - 100
                c.setFont("Helvetica", 10)
            c.drawString(LEFT_MARGIN, y_position, reco)
            y_position -= LINE_HEIGHT

        return y_position


    # === BUILD THE PDF ===
    current_y = height - 50

    # Header
    draw_header()
    current_y = height - 120

    # Player Information
    current_y = draw_player_info(current_y)

    # Domain Scores with Progress Bars
    current_y = draw_domain_scores(current_y)

    # Validity Scores
    current_y = draw_validity_scores(current_y)

    # Question Responses (start new page if needed)
    if current_y < 200:
        c.showPage()
        current_y = height - 50

    current_y = draw_question_responses(current_y)

    # Recommendations (start new page if needed)
    if current_y < 150:
        c.showPage()
        current_y = height - 50

    current_y = draw_recommendations(current_y)

    # Footer
    c.setFont("Helvetica-Oblique", 8)
    c.drawString(LEFT_MARGIN, 30, "Confidential Psychological Assessment - For Professional Use Only")
    c.drawString(LEFT_MARGIN, 20, "FOOTPSY Football Psychological Assessment System")

    c.save()
    buffer.seek(0)

    # Make a copy of the PDF data for saving
    pdf_data = BytesIO(buffer.getvalue())
    pdf_data.seek(0)

    # === Log results to Google Sheets ===
    if "logged" not in st.session_state:
        # First, save PDF to shared drive
        pdf_link = save_pdf_to_shared_drive(pdf_data, player_name, player_id)

        # Then log all data including PDF link
        success = log_to_gsheet(player_info, adjusted, validity_scores, responses, pdf_link)

        if success:
            st.success("✅ Assessment completed!")

        st.session_state.logged = True

    # Show PDF link if available
    if hasattr(st.session_state, 'pdf_link'):
        st.markdown(f"**🌐 Online Report Link:** [View Permanent Online Copy]({st.session_state.pdf_link})")
        st.markdown("*This link will always be accessible*")

    # === Do another test button ===
    restart = st.button("🏠 Do another test")

    if restart:
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.session_state.page = 1
        st.session_state.qpage = 1
        st.rerun()

    # === Download button ===
    st.download_button(
        label="📄 Download PDF Report",
        data=buffer,
        file_name=f"FOOTPSY_Report_{player_name}.pdf",
        mime="application/pdf"
    )

# ======= PAGE 9: ADMIN PANEL =======
if st.session_state.page == 9:
    # Check if user is authenticated
    if not st.session_state.get('admin_authenticated', False):
        st.error("🔒 Unauthorized access. Please login through the admin panel.")
        if st.button("← Back to Main"):
            st.session_state.page = 1
            st.rerun()
        st.stop()  # Stop execution here

    st.title("🔧 Admin Panel - View All Reports")

    # Add logout button
    if st.sidebar.button("🚪 Logout"):
        st.session_state.admin_authenticated = False
        st.session_state.page = 1
        st.rerun()

    # Rest of your admin panel code remains the same...
    try:
        SCOPES = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = Credentials.from_service_account_info(
            st.secrets["google_service_account"],
            scopes=SCOPES
        )
        client = gspread.authorize(creds)

        # Access the spreadsheet
        sheet = client.open("Footpsy - Football Psychological Assessment Database").sheet1

        # Get all records
        records = sheet.get_all_records()

        if records:
            st.subheader(f"Total Assessments: {len(records)}")

            # Create a DataFrame for display
            df = pd.DataFrame(records)

            # Search and filter
            col1, col2 = st.columns(2)
            with col1:
                search_name = st.text_input("Search by Player Name")
            with col2:
                search_team = st.text_input("Search by Team")

            # Filter data
            if search_name:
                df = df[df['Player Name'].str.contains(search_name, case=False, na=False)]
            if search_team:
                df = df[df['Team Name'].str.contains(search_team, case=False, na=False)]

            # Display results
            st.dataframe(df)

            # Option to download all data
            csv = df.to_csv(index=False)
            st.download_button(
                label="📥 Download All Data as CSV",
                data=csv,
                file_name="footpsy_all_assessments.csv",
                mime="text/csv"
            )
        else:
            st.info("No assessment data found.")

    except Exception as e:
        st.error(f"Error accessing data: {e}")

    if st.button("← Back to Main"):
        st.session_state.page = 1
        st.rerun()
