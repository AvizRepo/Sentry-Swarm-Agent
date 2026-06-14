import collections
import collections.abc
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN

def create_presentation():
    prs = Presentation()
    # 16:9 widescreen dimensions
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    
    # Color palette
    BG_COLOR = RGBColor(245, 248, 253)       # Soft blue-white
    CARD_BG = RGBColor(255, 255, 255)       # White cards
    TEXT_INK = RGBColor(13, 24, 40)         # Dark navy
    MUTED_INK = RGBColor(102, 118, 143)     # Slate gray
    BLUE_BRAND = RGBColor(47, 127, 230)     # SentrySwarm Blue
    GREEN_BRAND = RGBColor(21, 163, 90)     # Evidence Green
    AMBER_BRAND = RGBColor(224, 138, 0)     # Judge Amber
    
    # Helper to set background color of a slide
    def set_slide_background(slide):
        background = slide.background
        fill = background.fill
        fill.solid()
        fill.fore_color.rgb = BG_COLOR

    # Helper to add a slide with standard header
    def add_standard_slide(title_text):
        slide = prs.slides.add_slide(prs.slide_layouts[6]) # Blank layout
        set_slide_background(slide)
        
        # Header block
        txBox = slide.shapes.add_textbox(Inches(0.8), Inches(0.5), Inches(11.7), Inches(0.8))
        tf = txBox.text_frame
        tf.word_wrap = True
        p = tf.paragraphs[0]
        p.text = title_text
        p.font.name = 'Arial'
        p.font.size = Pt(28)
        p.font.bold = True
        p.font.color.rgb = BLUE_BRAND
        return slide

    # ----------------------------------------------------
    # SLIDE 1: Title Slide
    # ----------------------------------------------------
    slide1 = prs.slides.add_slide(prs.slide_layouts[6])
    set_slide_background(slide1)
    
    # Big title box
    txBox = slide1.shapes.add_textbox(Inches(1.0), Inches(2.0), Inches(11.3), Inches(3.5))
    tf = txBox.text_frame
    tf.word_wrap = True
    
    p = tf.paragraphs[0]
    p.text = "SentrySwarm AI"
    p.font.name = 'Arial'
    p.font.size = Pt(54)
    p.font.bold = True
    p.font.color.rgb = BLUE_BRAND
    
    p2 = tf.add_paragraph()
    p2.text = "Autonomous Incident Diagnosis Swarm"
    p2.font.name = 'Arial'
    p2.font.size = Pt(24)
    p2.font.color.rgb = TEXT_INK
    p2.space_before = Pt(10)
    
    p3 = tf.add_paragraph()
    p3.text = "Microsoft Build AI Hackathon  ·  Theme: Agent Swarms"
    p3.font.name = 'Arial'
    p3.font.size = Pt(14)
    p3.font.color.rgb = MUTED_INK
    p3.space_before = Pt(40)

    p4 = tf.add_paragraph()
    p4.text = "Developed by: Avinash Yadav & Darshan Ghorpade"
    p4.font.name = 'Arial'
    p4.font.size = Pt(16)
    p4.font.bold = True
    p4.font.color.rgb = TEXT_INK
    p4.space_before = Pt(20)

    # ----------------------------------------------------
    # SLIDE 2: The Problem
    # ----------------------------------------------------
    slide2 = add_standard_slide("Outage Diagnosis is Broken")
    
    # Content left box (The Pain points)
    txBox_l = slide2.shapes.add_textbox(Inches(0.8), Inches(1.5), Inches(5.5), Inches(5.0))
    tf_l = txBox_l.text_frame
    tf_l.word_wrap = True
    
    p_l1 = tf_l.paragraphs[0]
    p_l1.text = "The Modern War-Room Challenge"
    p_l1.font.name = 'Arial'
    p_l1.font.size = Pt(20)
    p_l1.font.bold = True
    p_l1.font.color.rgb = TEXT_INK
    p_l1.space_after = Pt(12)
    
    bullets = [
        "Production outages cost businesses thousands of dollars per minute.",
        "Manual triage is slow, fragmented, and prone to developer bias or guessing.",
        "Traditional alert noise buries the real root cause in metrics and logs.",
        "Single-agent AI systems fail on complex tasks—getting stuck in reasoning loops or accepting unverified assumptions."
    ]
    for b in bullets:
        p_b = tf_l.add_paragraph()
        p_b.text = "• " + b
        p_b.font.name = 'Arial'
        p_b.font.size = Pt(14)
        p_b.font.color.rgb = MUTED_INK
        p_b.space_before = Pt(8)
        
    # Right visual box (High MTTR callout)
    txBox_r = slide2.shapes.add_textbox(Inches(7.2), Inches(2.0), Inches(5.3), Inches(4.0))
    tf_r = txBox_r.text_frame
    tf_r.word_wrap = True
    
    p_r1 = tf_r.paragraphs[0]
    p_r1.text = "THE COST OF DELAY"
    p_r1.font.name = 'Arial'
    p_r1.font.size = Pt(12)
    p_r1.font.bold = True
    p_r1.font.color.rgb = AMBER_BRAND
    p_r1.alignment = PP_ALIGN.CENTER
    
    p_r2 = tf_r.add_paragraph()
    p_r2.text = "High MTTR"
    p_r2.font.name = 'Arial'
    p_r2.font.size = Pt(56)
    p_r2.font.bold = True
    p_r2.font.color.rgb = RGBColor(224, 68, 95) # Red
    p_r2.alignment = PP_ALIGN.CENTER
    
    p_r3 = tf_r.add_paragraph()
    p_r3.text = "(Mean Time To Resolution)\nleads to SLA breaches and damaged customer trust."
    p_r3.font.name = 'Arial'
    p_r3.font.size = Pt(14)
    p_r3.font.color.rgb = MUTED_INK
    p_r3.alignment = PP_ALIGN.CENTER

    # ----------------------------------------------------
    # SLIDE 3: The Solution
    # ----------------------------------------------------
    slide3 = add_standard_slide("The Solution: SentrySwarm AI")
    
    # 5 cards in a horizontal layout representing the swarm
    roles = [
        {"icon": "🧭", "name": "1. Triage", "color": BLUE_BRAND, "desc": "Classifies the outage severity, defines the focus parameters, and spawns the investigator agents."},
        {"icon": "💡", "name": "2. Hypotheses", "color": RGBColor(15, 169, 189), "desc": "Multiple agents run in parallel, each independently chasing a distinct potential root cause angle."},
        {"icon": "🔍", "name": "3. Evidence", "color": GREEN_BRAND, "desc": "Scours logs and metrics in parallel to compile factual supporting & contradicting data for each theory."},
        {"icon": "⚔️", "name": "4. Critic", "color": RGBColor(122, 92, 255), "desc": "Acts as a red-team validator, challenging the weak logic and testing assumptions of every hypothesis."},
        {"icon": "⚖️", "name": "5. Judge", "color": AMBER_BRAND, "desc": "Weighs the evidence and critic attacks to deliver the final root cause verdict and remediation steps."}
    ]
    
    card_width = Inches(2.2)
    card_height = Inches(4.5)
    gap = Inches(0.2)
    start_left = Inches(0.8)
    top_pos = Inches(1.8)
    
    for i, r in enumerate(roles):
        left_pos = start_left + i * (card_width + gap)
        # Create a textbox for each card
        card_box = slide3.shapes.add_textbox(left_pos, top_pos, card_width, card_height)
        tf_c = card_box.text_frame
        tf_c.word_wrap = True
        
        p_icon = tf_c.paragraphs[0]
        p_icon.text = r["icon"]
        p_icon.font.name = 'Arial'
        p_icon.font.size = Pt(36)
        p_icon.alignment = PP_ALIGN.CENTER
        
        p_name = tf_c.add_paragraph()
        p_name.text = r["name"]
        p_name.font.name = 'Arial'
        p_name.font.size = Pt(16)
        p_name.font.bold = True
        p_name.font.color.rgb = r["color"]
        p_name.alignment = PP_ALIGN.CENTER
        p_name.space_before = Pt(8)
        p_name.space_after = Pt(8)
        
        p_desc = tf_c.add_paragraph()
        p_desc.text = r["desc"]
        p_desc.font.name = 'Arial'
        p_desc.font.size = Pt(11.5)
        p_desc.font.color.rgb = TEXT_INK
        p_desc.alignment = PP_ALIGN.LEFT
        p_desc.space_before = Pt(6)

    # ----------------------------------------------------
    # SLIDE 4: Key Architecture Features
    # ----------------------------------------------------
    slide4 = add_standard_slide("Key Technical Innovations")
    
    features = [
        {"title": "WebSocket Real-Time Visualization", "desc": "A responsive, client-side SVG node graph renders live token streaming in real-time, allowing on-call teams to monitor the swarm's exact line of reasoning as it happens."},
        {"title": "Multi-Model Dynamic Routing", "desc": "Context-propagating routing dynamically leverages the strengths of multiple state-of-the-art models (Google Gemma 4, Gemini 3.5 Flash, Gemini 3.1 Pro, and Anthropic Claude 4.6 Sonnet)."},
        {"title": "Interactive Out-of-Band Retries", "desc": "Allows human operators to click a retry button on any card to rerun specific steps (e.g. gathering evidence under a new model) without resetting the entire workflow."},
        {"title": "Zero-Config local privacy", "desc": "API keys are managed securely on the client-side via browser localStorage and passed directly to WebSocket execution, eliminating server-side credential leaks."}
    ]
    
    for idx, f in enumerate(features):
        row = idx // 2
        col = idx % 2
        
        left = Inches(0.8 + col * 6.0)
        top = Inches(1.8 + row * 2.5)
        
        box = slide4.shapes.add_textbox(left, top, Inches(5.5), Inches(2.2))
        tf_f = box.text_frame
        tf_f.word_wrap = True
        
        p_title = tf_f.paragraphs[0]
        p_title.text = "🚀  " + f["title"]
        p_title.font.name = 'Arial'
        p_title.font.size = Pt(18)
        p_title.font.bold = True
        p_title.font.color.rgb = BLUE_BRAND
        p_title.space_after = Pt(6)
        
        p_desc = tf_f.add_paragraph()
        p_desc.text = f["desc"]
        p_desc.font.name = 'Arial'
        p_desc.font.size = Pt(13)
        p_desc.font.color.rgb = TEXT_INK
        p_desc.space_before = Pt(4)

    # ----------------------------------------------------
    # SLIDE 5: How it Works & Running Instructions
    # ----------------------------------------------------
    slide5 = add_standard_slide("Quick Start & Execution")
    
    # Left Box - Code / Setup
    txBox_l = slide5.shapes.add_textbox(Inches(0.8), Inches(1.5), Inches(5.8), Inches(5.0))
    tf_l = txBox_l.text_frame
    tf_l.word_wrap = True
    
    p_l1 = tf_l.paragraphs[0]
    p_l1.text = "Setup & Running Instructions"
    p_l1.font.name = 'Arial'
    p_l1.font.size = Pt(20)
    p_l1.font.bold = True
    p_l1.font.color.rgb = TEXT_INK
    p_l1.space_after = Pt(12)
    
    setup_steps = [
        "1. Clone the project code:\n   git clone https://github.com/AvizRepo/Sentry-Swarm-Agent.git",
        "2. Install python dependencies:\n   pip install -r requirements.txt",
        "3. Start FastAPI server:\n   cd backend && uvicorn main:app --reload",
        "4. Dockerized Run:\n   docker compose up --build",
        "5. Access UI at http://localhost:8000, add API keys in Key settings, pick a preset incident and run!"
    ]
    for step in setup_steps:
        p_step = tf_l.add_paragraph()
        p_step.text = step
        p_step.font.name = 'Consolas'
        p_step.font.size = Pt(11.5)
        p_step.font.color.rgb = MUTED_INK
        p_step.space_before = Pt(8)
        
    # Right Box - Architecture summary
    txBox_r = slide5.shapes.add_textbox(Inches(7.2), Inches(1.5), Inches(5.3), Inches(5.0))
    tf_r = txBox_r.text_frame
    tf_r.word_wrap = True
    
    p_r1 = tf_r.paragraphs[0]
    p_r1.text = "Swarm Topology"
    p_r1.font.name = 'Arial'
    p_r1.font.size = Pt(20)
    p_r1.font.bold = True
    p_r1.font.color.rgb = TEXT_INK
    p_r1.space_after = Pt(12)
    
    p_diag = tf_r.add_paragraph()
    p_diag.text = (
        "  [Triage Agent]\n"
        "        │\n"
        "  ┌─────┼─────┐   (Parallel Execution)\n"
        "  ▼     ▼     ▼\n"
        "[Hyp1] [Hyp2] [Hyp3]\n"
        "  │     │     │\n"
        "  ▼     ▼     ▼\n"
        "[Ev1]  [Ev2]  [Ev3]\n"
        "  └─────┼─────┘\n"
        "        ▼\n"
        "  [Critic Agent]  (Adversarial Attacks)\n"
        "        │\n"
        "        ▼\n"
        "  [Judge Agent]   (Root Cause + Remediation)"
    )
    p_diag.font.name = 'Consolas'
    p_diag.font.size = Pt(13)
    p_diag.font.bold = True
    p_diag.font.color.rgb = BLUE_BRAND
    p_diag.space_before = Pt(10)
    
    # Save the presentation
    prs.save("presentation.pptx")
    print("presentation.pptx created successfully!")

if __name__ == '__main__':
    create_presentation()
