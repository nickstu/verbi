import base64
import base64
import json
import os
import random
from html import escape
from urllib.parse import parse_qs


DATA_DIR = os.path.join(os.path.dirname(__file__), "data", "verbs")
TOTAL_QUESTIONS = 10
TENSE_JA = {
    "presente": "現在",
    "passato prossimo": "近過去",
}
GENDER_LABELS = {
    "masculine": "maschile 男性",
    "feminine": "femminile 女性",
    "masculine plural": "maschile plurale 男性複数",
    "feminine plural": "femminile plurale 女性複数",
}
ALL_GENDERS = list(GENDER_LABELS.keys())


def load_verbs():
    verbs = []
    for name in sorted(os.listdir(DATA_DIR)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(DATA_DIR, name)
        with open(path, "r", encoding="utf-8") as f:
            verb = json.load(f)
            verbs.append(verb)
    return verbs


VERBS = load_verbs()


def encode_state(state):
    raw = json.dumps(state, ensure_ascii=False).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def decode_state(value):
    if not value:
        return {"count": 0, "history": []}
    try:
        raw = base64.urlsafe_b64decode(value.encode("ascii"))
        state = json.loads(raw.decode("utf-8"))
        if "count" not in state or "history" not in state:
            return {"count": 0, "history": []}
        return state
    except (ValueError, json.JSONDecodeError):
        return {"count": 0, "history": []}


def build_tense_label(tense):
    tense_ja = TENSE_JA.get(tense, "")
    if tense_ja:
        return f"{tense} {tense_ja}"
    return tense


def build_gender_label(gender):
    return GENDER_LABELS.get(gender, "")


def pick_question():
    verb = random.choice(VERBS)
    form = random.choice(verb["forms"])
    return {
        "infinitive": verb["infinitive"],
        "ja": verb["ja"],
        "tense": form["tense"],
        "pronoun": form["pronoun"],
        "answer": form["value"],
        "gender": form.get("gender", ""),
    }


def render_page(question, state, finished=False):
    progress = f"{state['count']}/{TOTAL_QUESTIONS}"

    finish_note = ""
    if finished:
        finish_note = '<div class="finish">10問完了です。ページを更新するとリセットされます。</div>'

    question_html = ""
    form_html = ""
    if not finished and question:
        tense_label = build_tense_label(question["tense"])
        # Always show gender - randomize if not present so it doesn't give away the answer
        if question["gender"]:
            display_gender = question["gender"]
        else:
            display_gender = random.choice(ALL_GENDERS)
        gender_display = escape(build_gender_label(display_gender))
        question_html = (
            f'<div class="verb-info">'
            f'<div class="verb-name">{escape(question["infinitive"])} {escape(question["ja"])}</div>'
            f'<div class="tense">{escape(tense_label)}</div>'
            f'<div class="gender">{gender_display}</div>'
            f"</div>"
        )
        form_html = f"""<form method="post" class="answer-form">
          <span class="pronoun-inline">{escape(question["pronoun"])}</span>
          <input name="user_answer" type="text" autocomplete="off" class="answer-input" />
          <button type="submit">確認</button>
          <input type="hidden" name="q_infinitive" value="{escape(question["infinitive"])}" />
          <input type="hidden" name="q_ja" value="{escape(question["ja"])}" />
          <input type="hidden" name="q_tense" value="{escape(question["tense"])}" />
          <input type="hidden" name="q_pronoun" value="{escape(question["pronoun"])}" />
          <input type="hidden" name="q_gender" value="{escape(question["gender"])}" />
          <input type="hidden" name="q_answer" value="{escape(question["answer"])}" />
          <input type="hidden" name="state" value="{escape(encode_state(state))}" />
        </form>"""

    history_items = []
    for entry in state["history"]:
        tense_label = build_tense_label(entry["tense"])
        gender_label = build_gender_label(entry.get("gender", ""))
        gender_text = f" {escape(gender_label)}" if gender_label else ""
        question_text = (
            f"{escape(entry['infinitive'])} "
            f"{escape(entry['ja'])} "
            f"{escape(tense_label)}{gender_text}"
        )
        pronoun_text = escape(entry["pronoun"])
        user_answer = escape(entry.get("user_answer", ""))
        correct = escape(entry["correct"])
        user_class = "user-ok" if entry["ok"] else "user-bad"
        if entry["ok"]:
            answer_line = (
                f'<div class="history-answer">{pronoun_text} '
                f'<span class="history-correct">{user_answer}</span></div>'
            )
        else:
            answer_line = (
                f'<div class="history-answer">{pronoun_text} '
                f'<span class="{user_class}"><s>{user_answer}</s></span> '
                f'<span class="history-correct">{correct}</span></div>'
            )
        history_items.append(
            '<div class="history-item">'
            f'<div class="history-question">{question_text}</div>'
            f"{answer_line}"
            "</div>"
        )

    history_html = (
        "".join(history_items)
        if history_items
        else '<div class="empty">まだありません。</div>'
    )

    cat_image_html = (
        '<img src="/static/gatto-cropped.png" alt="Study cat" class="cat-image" />'
    )

    return f"""<!doctype html>
<html lang="it">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Italian Verb Quiz</title>
    <style>
      body {{
        font-family: Georgia, "Times New Roman", serif;
        background: #f5f0e6;
        color: #3d3630;
        margin: 0;
        padding: 32px;
      }}
      .layout {{
        display: flex;
        gap: 20px;
        max-width: 1100px;
        margin: 0 auto;
      }}
      .sidebar {{
        width: 360px;
        background: #faf7f0;
        border: 1px solid #e8e0d4;
        border-radius: 16px;
        padding: 20px;
        box-shadow: 0 12px 32px rgba(139, 125, 107, 0.1);
        overflow-y: auto;
        max-height: 85vh;
      }}
      .card {{
        flex: 1;
        background: #fffef9;
        border: 1px solid #e8e0d4;
        border-radius: 16px;
        padding: 28px;
        box-shadow: 0 12px 32px rgba(139, 125, 107, 0.12);
        display: flex;
        flex-direction: column;
        gap: 20px;
      }}
      .card-main {{
        display: flex;
        gap: 24px;
      }}
      .card-content {{
        flex: 1;
      }}
      .card-image {{
        width: 140px;
        flex-shrink: 0;
      }}
      .cat-image {{
        width: 100%;
        height: auto;
        display: block;
        object-fit: cover;
      }}
      .progress {{
        font-size: 14px;
        color: #7a7065;
        margin-bottom: 16px;
        font-weight: 500;
      }}
      .verb-info {{
        margin-bottom: 20px;
      }}
      .verb-name {{
        font-size: 24px;
        font-weight: 600;
        margin-bottom: 8px;
        color: #4a4239;
      }}
      .tense {{
        font-size: 16px;
        color: #6b635c;
        margin-bottom: 4px;
      }}
      .gender {{
        font-size: 14px;
        color: #8fa68e;
        font-style: italic;
      }}
      .answer-form {{
        display: flex;
        align-items: center;
        gap: 12px;
        margin-top: 20px;
      }}
      .pronoun-inline {{
        font-size: 18px;
        font-weight: 600;
        color: #5c5348;
        white-space: nowrap;
      }}
      .answer-input {{
        flex: 1;
        padding: 10px 14px;
        font-size: 16px;
        border: 2px solid #d8d0c4;
        border-radius: 8px;
        background: #fffef9;
      }}
      .answer-input:focus {{
        outline: none;
        border-color: #8fa68e;
      }}
      .finish {{
        margin-top: 12px;
        font-size: 15px;
        color: #5c5348;
        background: #f0ebe3;
        border: 1px solid #dcd4c8;
        padding: 12px 16px;
        border-radius: 10px;
      }}
      button {{
        background: #8fa68e;
        color: #fff;
        border: 0;
        padding: 12px 20px;
        border-radius: 10px;
        font-size: 16px;
        font-weight: 500;
        cursor: pointer;
        transition: background 0.2s, transform 0.1s;
      }}
      button:hover {{
        background: #7a9179;
      }}
      button:active {{
        transform: translateY(1px);
      }}
      .sidebar h2 {{
        margin: 0 0 14px;
        font-size: 14px;
        text-transform: uppercase;
        letter-spacing: 1px;
        color: #8fa68e;
        font-weight: 600;
      }}
      .history-item {{
        border-bottom: 1px dashed #dcd4c8;
        padding: 12px 0;
      }}
      .history-item:last-child {{
        border-bottom: 0;
      }}
      .history-question {{
        font-size: 14px;
        margin-bottom: 4px;
        color: #6b635c;
      }}
      .history-answer {{
        font-size: 13px;
        font-weight: 600;
      }}
      .history-correct {{
        font-size: 13px;
        color: #6b9b6a;
      }}
      .user-ok {{
        color: #6b9b6a;
      }}
      .user-bad {{
        color: #c4706a;
      }}
      .empty {{
        font-size: 13px;
        color: #9a9287;
        font-style: italic;
      }}
      @media (max-width: 900px) {{
        .layout {{
          flex-direction: column;
        }}
        .sidebar {{
          width: auto;
          max-height: none;
        }}
        .card-main {{
          flex-direction: column;
        }}
        .card-image {{
          width: 100%;
          max-width: 300px;
          margin: 0 auto;
        }}
        .answer-form {{
          flex-direction: column;
          align-items: stretch;
        }}
        .pronoun-inline {{
          text-align: center;
        }}
      }}
    </style>
  </head>
  <body>
    <div class="layout">
      <div class="card">
        <div class="card-main">
          <div class="card-content">
            <div class="progress">{progress}</div>
            {finish_note}
            {question_html}
          </div>
          <div class="card-image">
            {cat_image_html}
          </div>
        </div>
        {form_html}
      </div>
      <aside class="sidebar">
        <h2>History</h2>
        {history_html}
      </aside>
    </div>
  </body>
</html>"""


def parse_post(environ):
    try:
        length = int(environ.get("CONTENT_LENGTH", "0"))
    except ValueError:
        length = 0
    data = environ["wsgi.input"].read(length).decode("utf-8")
    parsed = parse_qs(data, keep_blank_values=True)
    return {key: values[0] if values else "" for key, values in parsed.items()}


def serve_static_file(path):
    static_dir = os.path.join(os.path.dirname(__file__), "static")
    file_path = os.path.join(static_dir, path.lstrip("/"))

    # Security check to prevent directory traversal
    real_static_dir = os.path.realpath(static_dir)
    real_file_path = os.path.realpath(file_path)
    if not real_file_path.startswith(real_static_dir):
        return None, None

    if not os.path.exists(file_path) or not os.path.isfile(file_path):
        return None, None

    content_type = "application/octet-stream"
    if file_path.endswith(".jpg") or file_path.endswith(".jpeg"):
        content_type = "image/jpeg"
    elif file_path.endswith(".png"):
        content_type = "image/png"
    elif file_path.endswith(".gif"):
        content_type = "image/gif"
    elif file_path.endswith(".svg"):
        content_type = "image/svg+xml"
    elif file_path.endswith(".css"):
        content_type = "text/css"
    elif file_path.endswith(".js"):
        content_type = "application/javascript"

    with open(file_path, "rb") as f:
        content = f.read()

    return content, content_type


def application(environ, start_response):
    path = environ.get("PATH_INFO", "")

    # Serve static files
    if path.startswith("/static/"):
        content, content_type = serve_static_file(path[8:])  # Remove "/static/" prefix
        if content is not None:
            start_response("200 OK", [("Content-Type", content_type)])
            return [content]
        else:
            start_response("404 Not Found", [("Content-Type", "text/plain")])
            return [b"Not Found"]

    if environ.get("REQUEST_METHOD") == "POST":
        form = parse_post(environ)
        state = decode_state(form.get("state", ""))
        user_answer = form.get("user_answer", "").strip()
        correct = form.get("q_answer", "").strip()
        ok = user_answer.lower() == correct.lower()
        entry = {
            "infinitive": form.get("q_infinitive", ""),
            "ja": form.get("q_ja", ""),
            "tense": form.get("q_tense", ""),
            "pronoun": form.get("q_pronoun", ""),
            "gender": form.get("q_gender", ""),
            "user_answer": user_answer,
            "correct": correct,
            "ok": ok,
        }
        state["history"].append(entry)
        state["count"] = len(state["history"])

        finished = state["count"] >= TOTAL_QUESTIONS
        question = None if finished else pick_question()
        body = render_page(question, state, finished=finished)
    else:
        state = {"count": 0, "history": []}
        question = pick_question()
        body = render_page(question, state, finished=False)

    start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
    return [body.encode("utf-8")]


if __name__ == "__main__":
    from wsgiref.simple_server import make_server

    with make_server("0.0.0.0", 8000, application) as httpd:
        print("Serving on http://127.0.0.1:8000")
        httpd.serve_forever()
