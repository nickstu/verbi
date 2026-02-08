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
    "masculine": "maschile (男性)",
    "feminine": "femminile (女性)",
    "masculine plural": "maschile plurale (男性複数)",
    "feminine plural": "femminile plurale (女性複数)",
}


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
        return f"{tense} ({tense_ja})"
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
        finish_note = "<div class=\"finish\">10問完了です。ページを更新するとリセットされます。</div>"

    question_html = ""
    form_html = ""
    if not finished and question:
        tense_label = build_tense_label(question["tense"])
        gender_label = build_gender_label(question["gender"])
        gender_text = f" {escape(gender_label)}" if gender_label else ""
        question_html = (
            f'<div class="question">{escape(question["infinitive"])} '
            f'{escape(question["ja"])} '
            f'{escape(tense_label)}{gender_text}</div>'
            f'<div class="pronoun">{escape(question["pronoun"])}</div>'
        )
        form_html = f"""<form method="post">
          <input name="user_answer" type="text" autocomplete="off" />
          <input type="hidden" name="q_infinitive" value="{escape(question['infinitive'])}" />
          <input type="hidden" name="q_ja" value="{escape(question['ja'])}" />
          <input type="hidden" name="q_tense" value="{escape(question['tense'])}" />
          <input type="hidden" name="q_pronoun" value="{escape(question['pronoun'])}" />
          <input type="hidden" name="q_gender" value="{escape(question['gender'])}" />
          <input type="hidden" name="q_answer" value="{escape(question['answer'])}" />
          <input type="hidden" name="state" value="{escape(encode_state(state))}" />
          <div class="actions">
            <button type="submit">確認</button>
          </div>
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
                f"<div class=\"history-answer\">{pronoun_text} "
                f"<span class=\"history-correct\">{user_answer}</span></div>"
            )
        else:
            answer_line = (
                f"<div class=\"history-answer\">{pronoun_text} "
                f"<span class=\"{user_class}\"><s>{user_answer}</s></span> "
                f"<span class=\"history-correct\">{correct}</span></div>"
            )
        history_items.append(
            "<div class=\"history-item\">"
            f"<div class=\"history-question\">{question_text}</div>"
            f"{answer_line}"
            "</div>"
        )

    history_html = "".join(history_items) if history_items else "<div class=\"empty\">まだありません。</div>"

    return f"""<!doctype html>
<html lang="it">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Italian Verb Quiz</title>
    <style>
      body {{
        font-family: Georgia, "Times New Roman", serif;
        background: #f2efe8;
        color: #1f1c1a;
        margin: 0;
        padding: 32px;
      }}
      .layout {{
        display: flex;
        gap: 20px;
        max-width: 1100px;
        margin: 0 auto;
      }}
      .card {{
        flex: 1;
        background: #fffdf7;
        border: 1px solid #e3ddd1;
        border-radius: 10px;
        padding: 24px;
        box-shadow: 0 10px 24px rgba(0, 0, 0, 0.08);
      }}
      .sidebar {{
        width: 360px;
        background: #faf6ed;
        border: 1px solid #e3ddd1;
        border-radius: 10px;
        padding: 16px;
        box-shadow: 0 10px 24px rgba(0, 0, 0, 0.06);
        overflow-y: auto;
        max-height: 80vh;
      }}
      h1 {{
        margin: 0 0 16px;
        font-size: 24px;
        letter-spacing: 0.5px;
      }}
      .progress {{
        font-size: 14px;
        color: #5a524b;
        margin-bottom: 8px;
      }}
      .question {{
        font-size: 20px;
        margin-bottom: 8px;
      }}
      .pronoun {{
        font-size: 18px;
        font-weight: 600;
        margin-bottom: 8px;
      }}
      .finish {{
        margin-top: 12px;
        font-size: 15px;
        color: #3a342e;
        background: #f0e6d6;
        border: 1px solid #e1d2bd;
        padding: 10px 12px;
        border-radius: 6px;
      }}
      input[type=text] {{
        width: 100%;
        padding: 10px 12px;
        font-size: 18px;
        border: 1px solid #cfc7bb;
        border-radius: 6px;
        box-sizing: border-box;
      }}
      .actions {{
        margin-top: 12px;
        display: flex;
        gap: 8px;
      }}
      button {{
        background: #2d5a4c;
        color: #fff;
        border: 0;
        padding: 10px 14px;
        border-radius: 6px;
        font-size: 16px;
        cursor: pointer;
      }}
      .sidebar h2 {{
        margin: 0 0 12px;
        font-size: 16px;
        text-transform: uppercase;
        letter-spacing: 0.8px;
      }}
      .history-item {{
        border-bottom: 1px dashed #d8cbb7;
        padding: 10px 0;
      }}
      .history-item:last-child {{
        border-bottom: 0;
      }}
      .history-question {{
        font-size: 14px;
        margin-bottom: 2px;
      }}
      .history-answer {{
        font-size: 13px;
        font-weight: 600;
      }}
      .history-correct {{
        font-size: 13px;
        color: #1f6b3b;
      }}
      .user-ok {{
        color: #1f6b3b;
      }}
      .user-bad {{
        color: #b01d1d;
      }}
      .empty {{
        font-size: 13px;
        color: #6b635c;
      }}
      @media (max-width: 900px) {{
        .layout {{
          flex-direction: column;
        }}
        .sidebar {{
          width: auto;
          max-height: none;
        }}
      }}
    </style>
  </head>
  <body>
    <div class="layout">
      <div class="card">
        <h1>Italian Verb Quiz</h1>
        <div class="progress">{progress}</div>
        {finish_note}
        {question_html}
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


def application(environ, start_response):
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
