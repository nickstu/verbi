import base64
import hashlib
import hmac
import json
import os
import random
import secrets
import sqlite3
import math
from http.cookies import SimpleCookie
from html import escape
from urllib.parse import parse_qs


DATA_DIR = os.path.join(os.path.dirname(__file__), "data", "verbs")
USERS_PATH = os.path.join(os.path.dirname(__file__), "data", "users.json")
DB_PATH = os.path.join(os.path.dirname(__file__), "data", "verbi.db")
TOTAL_QUESTIONS = 10
DEFAULT_ELO = 1200
ELO_K = 32
NEW_CONTENT_CHANCE = 0.08
TENSE_JA = {
    "presente": "現在",
    "passato prossimo": "近過去",
}
GENDER_LABELS = {
    "masculine": "maschile 男性",
    "feminine": "femminile 女性",
    "masculine plural": "maschile 男性",
    "feminine plural": "femminile 女性",
}
ALL_GENDERS = list(GENDER_LABELS.keys())
DB_INITIALIZED = False
CLOZE_EXAMPLES = [
    ("Io ____ italiano ogni giorno.", "studio", "私は毎日イタリア語を勉強します。"),
    ("Tu ____ un caffè al mattino.", "bevi", "君は朝にコーヒーを飲みます。"),
    ("Lei ____ a Tokyo.", "vive", "彼女は東京に住んでいます。"),
    ("Noi ____ la cena insieme.", "prepariamo", "私たちは一緒に夕食を準備します。"),
    ("Voi ____ molto bene.", "cantate", "あなたたちはとても上手に歌います。"),
    ("Loro ____ al parco.", "camminano", "彼らは公園で歩きます。"),
    ("Il gatto ____ sul divano.", "dorme", "猫はソファで寝ています。"),
    ("Maria ____ una lettera.", "scrive", "マリアは手紙を書きます。"),
    ("Noi ____ il treno alle otto.", "prendiamo", "私たちは8時に電車に乗ります。"),
    ("Tu ____ la porta.", "apri", "君はドアを開けます。"),
    ("Io ____ fame.", "ho", "私はお腹が空いています。"),
    ("Lei ____ felice oggi.", "è", "彼女は今日幸せです。"),
    ("Noi ____ italiani.", "siamo", "私たちはイタリア人です。"),
    ("Voi ____ una macchina rossa.", "avete", "あなたたちは赤い車を持っています。"),
    ("Loro ____ stanchi.", "sono", "彼らは疲れています。"),
    ("Io ____ al mercato.", "vado", "私は市場へ行きます。"),
    ("Tu ____ a casa tardi.", "torni", "君は遅く家に帰ります。"),
    ("Lei ____ un libro interessante.", "legge", "彼女は面白い本を読みます。"),
    ("Noi ____ la musica classica.", "ascoltiamo", "私たちはクラシック音楽を聞きます。"),
    ("Voi ____ una pizza.", "mangiate", "あなたたちはピザを食べます。"),
    ("Loro ____ una domanda.", "fanno", "彼らは質問をします。"),
    ("Io ____ il mio amico.", "vedo", "私は友達に会います。"),
    ("Tu ____ una risposta.", "dai", "君は答えを出します。"),
    ("Lei ____ in ufficio.", "lavora", "彼女はオフィスで働きます。"),
    ("Noi ____ una nuova lingua.", "impariamo", "私たちは新しい言語を学びます。"),
    ("Voi ____ il film stasera.", "guardate", "あなたたちは今夜映画を見ます。"),
    ("Loro ____ in Italia.", "abitano", "彼らはイタリアに住んでいます。"),
    ("Io ____ una foto.", "scatto", "私は写真を撮ります。"),
    ("Tu ____ troppo veloce.", "parli", "君は速すぎる話し方をします。"),
    ("Lei ____ il cane.", "ama", "彼女は犬が好きです。"),
    ("Noi ____ una pausa.", "facciamo", "私たちは休憩します。"),
    ("Voi ____ il conto.", "pagate", "あなたたちは会計を払います。"),
    ("Loro ____ la finestra.", "chiudono", "彼らは窓を閉めます。"),
    ("Io ____ presto.", "arrivo", "私は早く到着します。"),
    ("Tu ____ la chiave.", "cerchi", "君は鍵を探しています。"),
    ("Lei ____ una torta.", "cucina", "彼女はケーキを作ります。"),
    ("Noi ____ il problema.", "capiamo", "私たちは問題を理解します。"),
    ("Voi ____ il biglietto.", "comprate", "あなたたちはチケットを買います。"),
    ("Loro ____ una canzone.", "cantano", "彼らは歌を歌います。"),
    ("Io ____ l'acqua.", "bevo", "私は水を飲みます。"),
    ("Tu ____ il giornale.", "leggi", "君は新聞を読みます。"),
    ("Lei ____ al telefono.", "parla", "彼女は電話で話しています。"),
    ("Noi ____ la strada.", "attraversiamo", "私たちは道を渡ります。"),
    ("Voi ____ in montagna.", "andate", "あなたたちは山へ行きます。"),
    ("Loro ____ il museo.", "visitano", "彼らは博物館を訪れます。"),
    ("Io ____ una domanda.", "faccio", "私は質問をします。"),
    ("Tu ____ un regalo.", "ricevi", "君はプレゼントを受け取ります。"),
    ("Lei ____ il vestito blu.", "indossa", "彼女は青い服を着ています。"),
    ("Noi ____ dopo pranzo.", "partiamo", "私たちは昼食後に出発します。"),
    ("Voi ____ la verità.", "sapete", "あなたたちは真実を知っています。"),
]


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def load_seed_verbs():
    verbs = []
    if not os.path.exists(DATA_DIR):
        return verbs
    for name in sorted(os.listdir(DATA_DIR)):
        if not name.endswith(".json"):
            continue
        path = os.path.join(DATA_DIR, name)
        with open(path, "r", encoding="utf-8") as f:
            verbs.append(json.load(f))
    return verbs


def init_db():
    global DB_INITIALIZED
    if DB_INITIALIZED:
        return

    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with get_db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                name TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL DEFAULT '',
                practiced_count INTEGER NOT NULL DEFAULT 0,
                elo INTEGER NOT NULL DEFAULT 1200,
                session_token TEXT NOT NULL DEFAULT '',
                password_reset_required INTEGER NOT NULL DEFAULT 0,
                is_admin INTEGER NOT NULL DEFAULT 0,
                state_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_users_session_token
                ON users(session_token);

            CREATE TABLE IF NOT EXISTS verbs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                infinitive TEXT NOT NULL UNIQUE,
                ja TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS verb_forms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                verb_id INTEGER NOT NULL REFERENCES verbs(id) ON DELETE CASCADE,
                tense TEXT NOT NULL,
                pronoun TEXT NOT NULL,
                value TEXT NOT NULL,
                gender TEXT NOT NULL DEFAULT ''
            );

            CREATE INDEX IF NOT EXISTS idx_verb_forms_verb_id
                ON verb_forms(verb_id);

            CREATE TABLE IF NOT EXISTS user_flashcards (
                user_name TEXT NOT NULL REFERENCES users(name) ON DELETE CASCADE,
                verb_id INTEGER NOT NULL REFERENCES verbs(id) ON DELETE CASCADE,
                PRIMARY KEY (user_name, verb_id)
            );

            CREATE TABLE IF NOT EXISTS questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,
                verb_id INTEGER NOT NULL REFERENCES verbs(id) ON DELETE CASCADE,
                verb_form_id INTEGER REFERENCES verb_forms(id) ON DELETE CASCADE,
                prompt TEXT NOT NULL,
                answer TEXT NOT NULL,
                elo INTEGER NOT NULL DEFAULT 1200,
                active INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'approved',
                is_new INTEGER NOT NULL DEFAULT 0,
                UNIQUE(kind, verb_id, verb_form_id)
            );

            CREATE INDEX IF NOT EXISTS idx_questions_kind_elo
                ON questions(kind, elo);

            CREATE TABLE IF NOT EXISTS practice_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_name TEXT NOT NULL REFERENCES users(name) ON DELETE CASCADE,
                question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
                game TEXT NOT NULL,
                correct INTEGER NOT NULL,
                user_elo_before INTEGER NOT NULL,
                user_elo_after INTEGER NOT NULL,
                question_elo_before INTEGER NOT NULL,
                question_elo_after INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS cloze_questions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sentence TEXT NOT NULL UNIQUE,
                answer TEXT NOT NULL,
                translation TEXT NOT NULL,
                elo INTEGER NOT NULL DEFAULT 1200,
                active INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'approved',
                is_new INTEGER NOT NULL DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_cloze_questions_elo
                ON cloze_questions(elo);

            CREATE TABLE IF NOT EXISTS cloze_practice_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_name TEXT NOT NULL REFERENCES users(name) ON DELETE CASCADE,
                cloze_question_id INTEGER NOT NULL REFERENCES cloze_questions(id) ON DELETE CASCADE,
                correct INTEGER NOT NULL,
                user_elo_before INTEGER NOT NULL,
                user_elo_after INTEGER NOT NULL,
                question_elo_before INTEGER NOT NULL,
                question_elo_after INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS pending_content (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                content_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                created_by TEXT REFERENCES users(name) ON DELETE SET NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                reviewed_by TEXT REFERENCES users(name) ON DELETE SET NULL,
                reviewed_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_pending_content_status
                ON pending_content(status);
            """
        )

        user_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(users)").fetchall()
        }
        if "elo" not in user_columns:
            conn.execute(
                f"ALTER TABLE users ADD COLUMN elo INTEGER NOT NULL DEFAULT {DEFAULT_ELO}"
            )

        for table in ("questions", "cloze_questions"):
            columns = {
                row["name"]
                for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
            }
            if "status" not in columns:
                conn.execute(
                    f"ALTER TABLE {table} ADD COLUMN status TEXT NOT NULL DEFAULT 'approved'"
                )
            if "is_new" not in columns:
                conn.execute(
                    f"ALTER TABLE {table} ADD COLUMN is_new INTEGER NOT NULL DEFAULT 0"
                )

        verb_count = conn.execute("SELECT COUNT(*) FROM verbs").fetchone()[0]
        if verb_count == 0:
            for verb in load_seed_verbs():
                cursor = conn.execute(
                    "INSERT INTO verbs (infinitive, ja) VALUES (?, ?)",
                    (verb["infinitive"], verb["ja"]),
                )
                verb_id = cursor.lastrowid
                conn.executemany(
                    """
                    INSERT INTO verb_forms
                        (verb_id, tense, pronoun, value, gender)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            verb_id,
                            form["tense"],
                            form["pronoun"],
                            form["value"],
                            form.get("gender", ""),
                        )
                        for form in verb["forms"]
                    ],
                )

        question_count = conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0]
        if question_count == 0:
            conn.execute(
                """
                INSERT OR IGNORE INTO questions
                    (kind, verb_id, verb_form_id, prompt, answer, elo)
                SELECT 'flashcard', id, NULL, infinitive, ja, ?
                FROM verbs
                """,
                (DEFAULT_ELO,),
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO questions
                    (kind, verb_id, verb_form_id, prompt, answer, elo)
                SELECT
                    'verb_form',
                    v.id,
                    vf.id,
                    v.infinitive || '|' || v.ja || '|' || vf.tense || '|'
                        || vf.pronoun || '|' || vf.gender,
                    vf.value,
                    ?
                FROM verb_forms vf
                JOIN verbs v ON v.id = vf.verb_id
                """,
                (DEFAULT_ELO,),
            )

        cloze_count = conn.execute(
            "SELECT COUNT(*) FROM cloze_questions"
        ).fetchone()[0]
        if cloze_count == 0:
            conn.executemany(
                """
                INSERT OR IGNORE INTO cloze_questions
                    (sentence, answer, translation, elo)
                VALUES (?, ?, ?, ?)
                """,
                [
                    (sentence, answer, translation, DEFAULT_ELO)
                    for sentence, answer, translation in CLOZE_EXAMPLES
                ],
            )

        user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if user_count == 0 and os.path.exists(USERS_PATH):
            try:
                with open(USERS_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, json.JSONDecodeError):
                data = {"users": {}}

            for name, user in data.get("users", {}).items():
                if not isinstance(user, dict):
                    continue
                state = user.get("state") or {}
                conn.execute(
                    """
                    INSERT OR IGNORE INTO users
                        (
                            name,
                            password_hash,
                            practiced_count,
                            elo,
                            session_token,
                            password_reset_required,
                            is_admin,
                            state_json
                        )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        name,
                        user.get("password", ""),
                        int(state.get("practiced_count", 0)),
                        int(user.get("elo", DEFAULT_ELO)),
                        user.get("session_token", ""),
                        1 if user.get("password_reset_required") else 0,
                        1 if user.get("is_admin") or name == "admin" else 0,
                        json.dumps(
                            {
                                key: value
                                for key, value in state.items()
                                if key != "practiced_count"
                            },
                            ensure_ascii=False,
                        ),
                    ),
                )

    DB_INITIALIZED = True


def load_users():
    init_db()
    users = {}
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM users ORDER BY name").fetchall()
    for row in rows:
        try:
            extra_state = json.loads(row["state_json"] or "{}")
        except json.JSONDecodeError:
            extra_state = {}
        state = dict(extra_state)
        state["practiced_count"] = int(row["practiced_count"])
        users[row["name"]] = {
            "name": row["name"],
            "password": row["password_hash"],
            "elo": int(row["elo"]),
            "state": state,
            "session_token": row["session_token"],
            "password_reset_required": bool(row["password_reset_required"]),
            "is_admin": bool(row["is_admin"]) or row["name"] == "admin",
        }
    return {"users": users}


def save_users(data):
    init_db()
    with get_db() as conn:
        for name, user in data.get("users", {}).items():
            state = dict(user.get("state") or {})
            practiced = int(state.pop("practiced_count", 0))
            conn.execute(
                """
                INSERT INTO users
                    (
                        name,
                        password_hash,
                        practiced_count,
                        elo,
                        session_token,
                        password_reset_required,
                        is_admin,
                        state_json
                    )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    password_hash = excluded.password_hash,
                    practiced_count = excluded.practiced_count,
                    elo = excluded.elo,
                    session_token = excluded.session_token,
                    password_reset_required = excluded.password_reset_required,
                    is_admin = excluded.is_admin,
                    state_json = excluded.state_json
                """,
                (
                    name,
                    user.get("password", ""),
                    practiced,
                    int(user.get("elo", DEFAULT_ELO)),
                    user.get("session_token", ""),
                    1 if user.get("password_reset_required") else 0,
                    1 if user.get("is_admin") or name == "admin" else 0,
                    json.dumps(state, ensure_ascii=False),
                ),
            )


def load_verbs():
    init_db()
    verbs = []
    with get_db() as conn:
        verb_rows = conn.execute(
            "SELECT id, infinitive, ja FROM verbs ORDER BY infinitive"
        ).fetchall()
        for verb in verb_rows:
            form_rows = conn.execute(
                """
                SELECT tense, pronoun, value, gender
                FROM verb_forms
                WHERE verb_id = ?
                ORDER BY id
                """,
                (verb["id"],),
            ).fetchall()
            verbs.append(
                {
                    "infinitive": verb["infinitive"],
                    "ja": verb["ja"],
                    "forms": [
                        {
                            "tense": form["tense"],
                            "pronoun": form["pronoun"],
                            "value": form["value"],
                            **({"gender": form["gender"]} if form["gender"] else {}),
                        }
                        for form in form_rows
                    ],
                }
            )
    return verbs


VERBS = load_verbs()


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("ascii"), 100_000
    ).hex()
    return f"{salt}${digest}"


def verify_password(password, stored):
    try:
        salt, expected = stored.split("$", 1)
    except ValueError:
        return False
    actual = password_hash(password, salt).split("$", 1)[1]
    return hmac.compare_digest(actual, expected)


def get_cookie(environ, name):
    raw = environ.get("HTTP_COOKIE", "")
    cookie = SimpleCookie()
    cookie.load(raw)
    if name not in cookie:
        return ""
    return cookie[name].value


def set_session_cookie(headers, token):
    headers.append(
        (
            "Set-Cookie",
            f"verbi_session={token}; Path=/; HttpOnly; SameSite=Lax",
        )
    )


def clear_session_cookie(headers):
    headers.append(
        (
            "Set-Cookie",
            "verbi_session=; Path=/; Max-Age=0; HttpOnly; SameSite=Lax",
        )
    )


def current_user(environ):
    token = get_cookie(environ, "verbi_session")
    if not token:
        return None, None
    users = load_users()
    for name, user in users["users"].items():
        if hmac.compare_digest(user.get("session_token", ""), token):
            return name, user
    return None, None


def redirect(start_response, location, headers=None):
    response_headers = [("Location", location)]
    if headers:
        response_headers.extend(headers)
    start_response("302 Found", response_headers)
    return [b""]


def render_login(error=""):
    error_html = f'<div class="login-error">{escape(error)}</div>' if error else ""
    return f"""<!doctype html>
<html lang="it">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>ログイン</title>
    <style>
      body {{
        min-height: 100vh;
        margin: 0;
        display: grid;
        place-items: center;
        font-family: Georgia, "Times New Roman", serif;
        background: #f5f0e6;
        color: #3d3630;
      }}
      .login-window {{
        width: min(340px, calc(100vw - 40px));
        background: #fffef9;
        border: 1px solid #e8e0d4;
        border-radius: 12px;
        box-shadow: 0 12px 32px rgba(139, 125, 107, 0.14);
        padding: 24px;
      }}
      h1 {{
        margin: 0 0 16px;
        font-size: 22px;
        color: #4a4239;
      }}
      label {{
        display: block;
        margin: 12px 0 6px;
        font-size: 13px;
        color: #6b635c;
      }}
      input {{
        width: 100%;
        box-sizing: border-box;
        padding: 10px 12px;
        font-size: 15px;
        border: 2px solid #d8d0c4;
        border-radius: 8px;
        background: #fffef9;
      }}
      input:focus {{
        outline: none;
        border-color: #8fa68e;
      }}
      .actions {{
        margin-top: 18px;
      }}
      button {{
        width: 100%;
        background: #8fa68e;
        color: #fff;
        border: 0;
        padding: 11px 12px;
        border-radius: 8px;
        font-size: 15px;
        cursor: pointer;
      }}
      .login-error {{
        margin-bottom: 12px;
        padding: 10px 12px;
        border-radius: 8px;
        background: #f7e7e4;
        color: #9b4d48;
        font-size: 13px;
      }}
    </style>
  </head>
  <body>
    <form method="post" action="/login" class="login-window">
      <h1>イタリア語練習</h1>
      {error_html}
      <label for="name">名前</label>
      <input id="name" name="name" type="text" autocomplete="username" required />
      <label for="password">パスワード</label>
      <input id="password" name="password" type="password" autocomplete="current-password" />
      <div class="actions">
        <button type="submit" name="mode" value="login">ログイン</button>
      </div>
    </form>
  </body>
</html>"""


def render_password_setup(name, error=""):
    error_html = f'<div class="login-error">{escape(error)}</div>' if error else ""
    return f"""<!doctype html>
<html lang="it">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>パスワード設定</title>
    <style>
      body {{
        min-height: 100vh;
        margin: 0;
        display: grid;
        place-items: center;
        font-family: Georgia, "Times New Roman", serif;
        background: #f5f0e6;
        color: #3d3630;
      }}
      .login-window {{
        width: min(340px, calc(100vw - 40px));
        background: #fffef9;
        border: 1px solid #e8e0d4;
        border-radius: 12px;
        box-shadow: 0 12px 32px rgba(139, 125, 107, 0.14);
        padding: 24px;
      }}
      h1 {{
        margin: 0 0 8px;
        font-size: 22px;
        color: #4a4239;
      }}
      p {{
        margin: 0 0 16px;
        color: #6b635c;
        font-size: 14px;
      }}
      label {{
        display: block;
        margin: 12px 0 6px;
        font-size: 13px;
        color: #6b635c;
      }}
      input {{
        width: 100%;
        box-sizing: border-box;
        padding: 10px 12px;
        font-size: 15px;
        border: 2px solid #d8d0c4;
        border-radius: 8px;
        background: #fffef9;
      }}
      input:focus {{
        outline: none;
        border-color: #8fa68e;
      }}
      button {{
        width: 100%;
        margin-top: 18px;
        background: #8fa68e;
        color: #fff;
        border: 0;
        padding: 11px 12px;
        border-radius: 8px;
        font-size: 15px;
        cursor: pointer;
      }}
      .login-error {{
        margin-bottom: 12px;
        padding: 10px 12px;
        border-radius: 8px;
        background: #f7e7e4;
        color: #9b4d48;
        font-size: 13px;
      }}
    </style>
  </head>
  <body>
    <form method="post" action="/set-password" class="login-window">
      <h1>パスワード設定</h1>
      <p>{escape(name)}さん、続けるためにパスワードを設定してください。</p>
      {error_html}
      <label for="password">パスワード</label>
      <input id="password" name="password" type="password" autocomplete="new-password" required />
      <label for="confirm_password">パスワード確認</label>
      <input id="confirm_password" name="confirm_password" type="password" autocomplete="new-password" required />
      <button type="submit">保存</button>
    </form>
  </body>
</html>"""


def render_admin(users, message="", error=""):
    message_html = f'<div class="notice ok">{escape(message)}</div>' if message else ""
    error_html = f'<div class="notice bad">{escape(error)}</div>' if error else ""
    rows = []
    for name, user in sorted(users["users"].items()):
        role = "管理者" if user.get("is_admin") else "ユーザー"
        reset = "未設定" if user.get("password_reset_required") else "設定済み"
        disabled = " disabled" if user.get("is_admin") else ""
        rows.append(
            "<tr>"
            f"<td>{escape(name)}</td>"
            f"<td>{role}</td>"
            f"<td>{reset}</td>"
            f'<td><form method="post" action="/admin/reset-password">'
            f'<input type="hidden" name="name" value="{escape(name)}" />'
            f"<button type=\"submit\"{disabled}>リセット</button>"
            "</form></td>"
            "</tr>"
        )
    return f"""<!doctype html>
<html lang="it">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>管理</title>
    <style>
      body {{
        font-family: Georgia, "Times New Roman", serif;
        background: #f5f0e6;
        color: #3d3630;
        margin: 0;
        padding: 32px;
      }}
      .panel {{
        max-width: 760px;
        margin: 0 auto;
        background: #fffef9;
        border: 1px solid #e8e0d4;
        border-radius: 12px;
        box-shadow: 0 12px 32px rgba(139, 125, 107, 0.12);
        padding: 24px;
      }}
      .top {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
        margin-bottom: 20px;
      }}
      h1 {{
        margin: 0;
        font-size: 24px;
      }}
      a {{
        color: #8fa68e;
        font-weight: 600;
        text-decoration: none;
      }}
      form.create {{
        display: flex;
        gap: 10px;
        margin: 0 0 20px;
      }}
      input {{
        flex: 1;
        min-width: 0;
        padding: 10px 12px;
        font-size: 15px;
        border: 2px solid #d8d0c4;
        border-radius: 8px;
        background: #fffef9;
      }}
      button {{
        background: #8fa68e;
        color: #fff;
        border: 0;
        padding: 10px 14px;
        border-radius: 8px;
        font-size: 14px;
        cursor: pointer;
      }}
      button:disabled {{
        background: #c9c1b7;
        cursor: default;
      }}
      table {{
        width: 100%;
        border-collapse: collapse;
      }}
      th, td {{
        padding: 10px 8px;
        border-bottom: 1px dashed #dcd4c8;
        text-align: left;
        font-size: 14px;
      }}
      th {{
        color: #6b635c;
      }}
      td form {{
        margin: 0;
      }}
      .notice {{
        margin-bottom: 14px;
        padding: 10px 12px;
        border-radius: 8px;
        font-size: 13px;
      }}
      .ok {{
        background: #e9f1e8;
        color: #557a53;
      }}
      .bad {{
        background: #f7e7e4;
        color: #9b4d48;
      }}
      @media (max-width: 640px) {{
        body {{
          padding: 20px;
        }}
        .top, form.create {{
          align-items: stretch;
          flex-direction: column;
        }}
      }}
    </style>
  </head>
  <body>
    <main class="panel">
      <div class="top">
        <h1>管理</h1>
        <a href="/">メニューへ戻る</a>
      </div>
      {message_html}
      {error_html}
      <form method="post" action="/admin/create-user" class="create">
        <input name="name" type="text" placeholder="新しいユーザー名" autocomplete="off" required />
        <button type="submit">ユーザー作成</button>
      </form>
      <table>
        <thead>
          <tr><th>名前</th><th>権限</th><th>パスワード</th><th>操作</th></tr>
        </thead>
        <tbody>
          {"".join(rows)}
        </tbody>
      </table>
    </main>
  </body>
</html>"""


def load_pending_content():
    init_db()
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT id, content_type, payload_json, status, created_at
            FROM pending_content
            WHERE status = 'pending'
            ORDER BY created_at DESC
            """
        ).fetchall()
    items = []
    for row in rows:
        try:
            payload = json.loads(row["payload_json"])
        except json.JSONDecodeError:
            payload = {}
        items.append(
            {
                "id": row["id"],
                "content_type": row["content_type"],
                "payload": payload,
                "created_at": row["created_at"],
            }
        )
    return items


def render_content_admin(items, message="", error=""):
    message_html = f'<div class="notice ok">{escape(message)}</div>' if message else ""
    error_html = f'<div class="notice bad">{escape(error)}</div>' if error else ""
    if items:
        item_html = []
        for item in items:
            payload = item["payload"]
            item_html.append(
                '<div class="pending-item">'
                f'<div class="meta">#{item["id"]} · {escape(item["content_type"])}</div>'
                f'<div class="sentence">{escape(payload.get("sentence", ""))}</div>'
                f'<div>答え: {escape(payload.get("answer", ""))}</div>'
                f'<div>訳: {escape(payload.get("translation", ""))}</div>'
                '<div class="actions-row">'
                '<form method="post" action="/admin/content/approve">'
                f'<input type="hidden" name="id" value="{item["id"]}" />'
                '<button type="submit">承認</button>'
                '</form>'
                '<form method="post" action="/admin/content/reject">'
                f'<input type="hidden" name="id" value="{item["id"]}" />'
                '<button class="secondary" type="submit">却下</button>'
                '</form>'
                '</div>'
                '</div>'
            )
        pending_html = f'<div class="review-list">{"".join(item_html)}</div>'
    else:
        pending_html = '<div class="empty">保留中のコンテンツはありません。</div>'
    return f"""<!doctype html>
<html lang="ja">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>コンテンツ管理</title>
    <style>
      body {{
        font-family: Georgia, "Times New Roman", serif;
        background: #f5f0e6;
        color: #3d3630;
        margin: 0;
        padding: 32px;
      }}
      .panel {{
        max-width: 980px;
        margin: 0 auto;
        background: #fffef9;
        border: 1px solid #e8e0d4;
        border-radius: 12px;
        box-shadow: 0 12px 32px rgba(139, 125, 107, 0.12);
        padding: 24px;
      }}
      .top {{
        display: flex;
        justify-content: space-between;
        gap: 12px;
        align-items: center;
        margin-bottom: 20px;
      }}
      h1, h2 {{
        margin: 0 0 14px;
      }}
      h1 {{
        font-size: 24px;
      }}
      h2 {{
        font-size: 18px;
        margin-top: 24px;
      }}
      .review-list {{
        display: grid;
        gap: 12px;
        max-height: 68vh;
        overflow-y: auto;
        padding-right: 4px;
      }}
      a {{
        color: #8fa68e;
        font-weight: 600;
        text-decoration: none;
      }}
      label {{
        display: block;
        color: #6b635c;
        font-size: 13px;
        margin: 10px 0 6px;
      }}
      input, textarea {{
        box-sizing: border-box;
        width: 100%;
        padding: 10px 12px;
        font-size: 15px;
        border: 2px solid #d8d0c4;
        border-radius: 8px;
        background: #fffef9;
      }}
      textarea {{
        min-height: 78px;
        resize: vertical;
      }}
      button {{
        background: #8fa68e;
        color: #fff;
        border: 0;
        border-radius: 8px;
        cursor: pointer;
        font-size: 14px;
        margin-top: 12px;
        padding: 10px 14px;
      }}
      button.secondary {{
        background: #b8aa97;
      }}
      .pending-item {{
        background: #faf7f0;
        border: 1px solid #e8e0d4;
        border-radius: 10px;
        padding: 16px;
      }}
      .meta, .empty {{
        color: #7a7065;
        font-size: 13px;
      }}
      .sentence {{
        font-size: 18px;
        font-weight: 600;
        margin: 6px 0;
      }}
      .actions-row {{
        display: flex;
        gap: 10px;
        justify-content: flex-end;
        margin-top: 12px;
      }}
      .actions-row form {{
        margin: 0;
      }}
      .actions-row button {{
        margin-top: 0;
      }}
      .notice {{
        margin-bottom: 14px;
        padding: 10px 12px;
        border-radius: 8px;
        font-size: 13px;
      }}
      .ok {{
        background: #e9f1e8;
        color: #557a53;
      }}
      .bad {{
        background: #f7e7e4;
        color: #9b4d48;
      }}
    </style>
  </head>
  <body>
    <main class="panel">
      <div class="top">
        <h1>コンテンツ管理</h1>
        <a href="/admin">管理へ戻る</a>
      </div>
      {message_html}
      {error_html}
      <h2>レビュー待ち</h2>
      {pending_html}
    </main>
  </body>
</html>"""


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


def expected_score(player_elo, question_elo):
    return 1 / (1 + 10 ** ((question_elo - player_elo) / 400))


def update_elo(username, question_id, correct, game):
    init_db()
    with get_db() as conn:
        user_row = conn.execute(
            "SELECT elo FROM users WHERE name = ?", (username,)
        ).fetchone()
        question_row = conn.execute(
            "SELECT elo FROM questions WHERE id = ?", (question_id,)
        ).fetchone()
        if not user_row or not question_row:
            return None

        user_before = int(user_row["elo"])
        question_before = int(question_row["elo"])
        actual = 1 if correct else 0
        expected = expected_score(user_before, question_before)
        user_after = round(user_before + ELO_K * (actual - expected))
        question_actual = 1 - actual
        question_expected = 1 - expected
        question_after = round(
            question_before + ELO_K * (question_actual - question_expected)
        )

        conn.execute(
            "UPDATE users SET elo = ? WHERE name = ?", (user_after, username)
        )
        conn.execute(
            "UPDATE questions SET elo = ? WHERE id = ?",
            (question_after, question_id),
        )
        conn.execute(
            """
            INSERT INTO practice_events
                (
                    user_name,
                    question_id,
                    game,
                    correct,
                    user_elo_before,
                    user_elo_after,
                    question_elo_before,
                    question_elo_after
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                username,
                question_id,
                game,
                actual,
                user_before,
                user_after,
                question_before,
                question_after,
            ),
        )
    return {
        "user_before": user_before,
        "user_after": user_after,
        "question_before": question_before,
        "question_after": question_after,
    }


def update_cloze_elo(username, question_id, correct):
    init_db()
    with get_db() as conn:
        user_row = conn.execute(
            "SELECT elo FROM users WHERE name = ?", (username,)
        ).fetchone()
        question_row = conn.execute(
            "SELECT elo FROM cloze_questions WHERE id = ?", (question_id,)
        ).fetchone()
        if not user_row or not question_row:
            return None

        user_before = int(user_row["elo"])
        question_before = int(question_row["elo"])
        actual = 1 if correct else 0
        expected = expected_score(user_before, question_before)
        user_after = round(user_before + ELO_K * (actual - expected))
        question_after = round(
            question_before + ELO_K * ((1 - actual) - (1 - expected))
        )

        conn.execute(
            "UPDATE users SET elo = ? WHERE name = ?", (user_after, username)
        )
        conn.execute(
            "UPDATE cloze_questions SET elo = ? WHERE id = ?",
            (question_after, question_id),
        )
        conn.execute(
            """
            INSERT INTO cloze_practice_events
                (
                    user_name,
                    cloze_question_id,
                    correct,
                    user_elo_before,
                    user_elo_after,
                    question_elo_before,
                    question_elo_after
                )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                username,
                question_id,
                actual,
                user_before,
                user_after,
                question_before,
                question_after,
            ),
        )
    return {
        "user_before": user_before,
        "user_after": user_after,
        "question_before": question_before,
        "question_after": question_after,
    }


def weighted_row_by_elo(rows, user_elo):
    if not rows:
        return None
    weights = []
    for row in rows:
        diff = int(row["elo"]) - user_elo
        if diff > 150:
            weight = 0.15 * math.exp(-diff / 250)
        else:
            weight = math.exp(-abs(diff) / 250)
        if diff < -800:
            weight *= 0.25
        weights.append(max(weight, 0.001))
    return random.choices(rows, weights=weights, k=1)[0]


def weighted_question_row(user, kind):
    init_db()
    user_elo = int(user.get("elo", DEFAULT_ELO))
    with get_db() as conn:
        if kind == "flashcard":
            pool_count = conn.execute(
                "SELECT COUNT(*) FROM user_flashcards WHERE user_name = ?",
                (user["name"],),
            ).fetchone()[0]
            force_new = random.random() < NEW_CONTENT_CHANCE
            if pool_count:
                rows = conn.execute(
                    """
                    SELECT q.*, v.infinitive, v.ja
                    FROM questions q
                    JOIN verbs v ON v.id = q.verb_id
                    JOIN user_flashcards uf ON uf.verb_id = v.id
                    WHERE uf.user_name = ?
                        AND q.kind = 'flashcard'
                        AND q.active = 1
                        AND q.status = 'approved'
                        AND (? = 0 OR q.is_new = 1)
                    """,
                    (user["name"], 1 if force_new else 0),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT q.*, v.infinitive, v.ja
                    FROM questions q
                    JOIN verbs v ON v.id = q.verb_id
                    WHERE q.kind = 'flashcard'
                        AND q.active = 1
                        AND q.status = 'approved'
                        AND (? = 0 OR q.is_new = 1)
                    """
                    ,
                    (1 if force_new else 0,),
                ).fetchall()
            if force_new and not rows:
                return weighted_question_row(user, kind)
        else:
            force_new = random.random() < NEW_CONTENT_CHANCE
            rows = conn.execute(
                """
                SELECT
                    q.*,
                    v.infinitive,
                    v.ja,
                    vf.tense,
                    vf.pronoun,
                    vf.gender
                FROM questions q
                JOIN verbs v ON v.id = q.verb_id
                JOIN verb_forms vf ON vf.id = q.verb_form_id
                WHERE q.kind = 'verb_form'
                    AND q.active = 1
                    AND q.status = 'approved'
                    AND (? = 0 OR q.is_new = 1)
                """
                ,
                (1 if force_new else 0,),
            ).fetchall()
            if force_new and not rows:
                return weighted_question_row(user, kind)

    return weighted_row_by_elo(rows, user_elo)


def pick_cloze_question(user):
    init_db()
    force_new = (
        random.random() < NEW_CONTENT_CHANCE
        and not user.get("_skip_new")
    )
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT id, sentence, answer, translation, elo, is_new
            FROM cloze_questions
            WHERE active = 1
                AND status = 'approved'
                AND (? = 0 OR is_new = 1)
            """,
            (1 if force_new else 0,),
        ).fetchall()
    if force_new and not rows:
        return pick_cloze_question({**user, "_skip_new": True})
    row = weighted_row_by_elo(rows, int(user.get("elo", DEFAULT_ELO)))
    if not row:
        return None
    return {
        "question_id": row["id"],
        "sentence": row["sentence"],
        "answer": row["answer"],
        "translation": row["translation"],
        "question_elo": row["elo"],
        "is_new": bool(row["is_new"]),
    }


def pick_question(user=None):
    row = weighted_question_row(user or {"name": "", "elo": DEFAULT_ELO}, "verb_form")
    if row:
        return {
            "question_id": row["id"],
            "question_elo": row["elo"],
            "is_new": bool(row["is_new"]),
            "infinitive": row["infinitive"],
            "ja": row["ja"],
            "tense": row["tense"],
            "pronoun": row["pronoun"],
            "answer": row["answer"],
            "gender": row["gender"],
        }
    verb = random.choice(VERBS)
    form = random.choice(verb["forms"])
    return {
        "question_id": "",
        "question_elo": DEFAULT_ELO,
        "is_new": False,
        "infinitive": verb["infinitive"],
        "ja": verb["ja"],
        "tense": form["tense"],
        "pronoun": form["pronoun"],
        "answer": form["value"],
        "gender": form.get("gender", ""),
    }


def user_flashcard_pool(user):
    init_db()
    with get_db() as conn:
        pool_count = conn.execute(
            "SELECT COUNT(*) FROM user_flashcards WHERE user_name = ?",
            (user["name"],),
        ).fetchone()[0]
        if pool_count:
            rows = conn.execute(
                """
                SELECT v.infinitive, v.ja
                FROM user_flashcards uf
                JOIN verbs v ON v.id = uf.verb_id
                WHERE uf.user_name = ?
                ORDER BY v.infinitive
                """,
                (user["name"],),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT infinitive, ja FROM verbs ORDER BY infinitive"
            ).fetchall()
    return [
        {"word": row["infinitive"], "translation": row["ja"]}
        for row in rows
    ]


def pick_flashcard(user):
    row = weighted_question_row(user, "flashcard")
    if row:
        card = {
            "question_id": row["id"],
            "question_elo": row["elo"],
            "is_new": bool(row["is_new"]),
            "word": row["infinitive"],
            "translation": row["answer"],
        }
    else:
        cards = user_flashcard_pool(user)
        card = random.choice(cards)
        card["question_id"] = ""
        card["question_elo"] = DEFAULT_ELO
        card["is_new"] = False
    cards = user_flashcard_pool(user)
    translations = [
        item["translation"]
        for item in cards
        if item["translation"] != card["translation"]
    ]
    random.shuffle(translations)
    options = translations[:3] + [card["translation"]]
    random.shuffle(options)
    return card, options


def increment_practiced_count(username):
    init_db()
    with get_db() as conn:
        conn.execute(
            """
            UPDATE users
            SET practiced_count = practiced_count + 1
            WHERE name = ?
            """,
            (username,),
        )
    return load_users()["users"].get(username)


def practiced_count(user):
    return int(user.get("state", {}).get("practiced_count", 0))


def render_nav(username, user, active=""):
    admin_link = (
        '<a href="/admin">管理</a>' if user.get("is_admin") else ""
    )
    links = [
        ('href="/"', "メニュー"),
        ('href="/verbs"', "動詞練習"),
        ('href="/flashcards"', "単語カード"),
        ('href="/cloze"', "穴埋め"),
    ]
    link_html = "".join(
        f'<a {attrs} class="{"active" if label == active else ""}">{label}</a>'
        for attrs, label in links
    )
    return (
        f'<div class="topline"><nav class="nav">{link_html}{admin_link}</nav>'
        f'<div class="user-status">{escape(username)} · '
        f'{practiced_count(user)}枚練習済み '
        '<a class="logout" href="/logout">ログアウト</a></div></div>'
    )


def render_nav(username, user, active=""):
    admin_link = '<a href="/admin">管理</a>' if user.get("is_admin") else ""
    links = [
        ('href="/"', "メニュー"),
        ('href="/verbs"', "動詞練習"),
        ('href="/flashcards"', "単語カード"),
        ('href="/cloze"', "穴埋め"),
    ]
    link_html = "".join(
        f'<a {attrs} class="{"active" if label == active else ""}">{label}</a>'
        for attrs, label in links
    )
    return (
        f'<div class="topline"><nav class="nav">{link_html}{admin_link}</nav>'
        f'<div class="user-status">{escape(username)} · '
        f'ELO {int(user.get("elo", DEFAULT_ELO))} · '
        f'{practiced_count(user)}枚練習済み '
        '<a class="logout" href="/logout">ログアウト</a></div></div>'
    )


def render_page(
    question,
    state,
    username,
    practiced_count,
    user_elo=DEFAULT_ELO,
    is_admin=False,
    finished=False,
):
    progress = f"{state['count']}/{TOTAL_QUESTIONS}"
    nav_html = render_nav(
        username,
        {
            "state": {"practiced_count": practiced_count},
            "elo": user_elo,
            "is_admin": is_admin,
        },
        "動詞練習",
    )

    finish_note = ""
    if finished:
        finish_note = '<div class="finish">10問完了です。ページを更新するとリセットされます。</div>'

    question_html = ""
    form_html = ""
    if not finished and question:
        tense_label = build_tense_label(question["tense"])
        new_badge = '<span class="new-badge">NEW</span>' if question.get("is_new") else ""
        # Always show gender - randomize if not present so it doesn't give away the answer
        if question["gender"]:
            display_gender = question["gender"]
        else:
            display_gender = random.choice(ALL_GENDERS)
        gender_display = escape(build_gender_label(display_gender))
        question_html = (
            f'<div class="verb-info">'
            f'<div class="verb-name">{escape(question["infinitive"])} {escape(question["ja"])} {new_badge}</div>'
            f'<div class="tense">{escape(tense_label)}</div>'
            f'<div class="gender">{gender_display}</div>'
            f'<div class="elo-line">あなたのELO: {int(user_elo)} / '
            f'問題ELO: {int(question.get("question_elo", DEFAULT_ELO))}</div>'
            f"</div>"
        )
        form_html = f"""<form method="post" action="/verbs" class="answer-form">
          <span class="pronoun-inline">{escape(question["pronoun"])}</span>
          <input name="user_answer" type="text" autocomplete="off" class="answer-input" />
          <button type="submit">確認</button>
          <input type="hidden" name="q_infinitive" value="{escape(question["infinitive"])}" />
          <input type="hidden" name="q_ja" value="{escape(question["ja"])}" />
          <input type="hidden" name="q_tense" value="{escape(question["tense"])}" />
          <input type="hidden" name="q_pronoun" value="{escape(question["pronoun"])}" />
          <input type="hidden" name="q_gender" value="{escape(question["gender"])}" />
          <input type="hidden" name="q_answer" value="{escape(question["answer"])}" />
          <input type="hidden" name="q_question_id" value="{escape(str(question.get("question_id", "")))}" />
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
      .topline {{
        display: flex;
        justify-content: space-between;
        gap: 16px;
        align-items: center;
        margin-bottom: 16px;
      }}
      .progress {{
        margin-bottom: 0;
      }}
      .user-status {{
        color: #7a7065;
        font-size: 13px;
        text-align: right;
      }}
      .logout {{
        color: #8fa68e;
        margin-left: 8px;
        text-decoration: none;
        font-weight: 600;
      }}
      .verb-info {{
        margin-bottom: 20px;
      }}
      .card-content > .topline:nth-of-type(2) {{
        display: none;
      }}
      .nav {{
        display: flex;
        flex-wrap: wrap;
        gap: 12px;
        align-items: center;
      }}
      .nav a {{
        color: #8fa68e;
        font-size: 13px;
        font-weight: 600;
        text-decoration: none;
      }}
      .nav a.active {{
        color: #4a4239;
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
      .elo-line {{
        color: #7a7065;
        font-size: 13px;
        margin-top: 8px;
      }}
      .new-badge {{
        background: #c4706a;
        border-radius: 999px;
        color: #fff;
        display: inline-block;
        font-size: 11px;
        padding: 3px 7px;
        vertical-align: middle;
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
          flex-direction: row;
          align-items: flex-start;
          gap: 16px;
        }}
        .card-content {{
          flex: 1;
        }}
        .card-image {{
          width: 104px;
          flex-shrink: 0;
          margin: 0;
        }}
        .answer-form {{
          flex-direction: column;
          align-items: stretch;
          margin-top: 16px;
        }}
        .pronoun-inline {{
          text-align: center;
        }}
        .verb-name {{
          font-size: 20px;
        }}
        .tense {{
          font-size: 14px;
        }}
        .gender {{
          font-size: 12px;
        }}
        .topline {{
          align-items: flex-start;
        }}
      }}
    </style>
  </head>
  <body>
    <div class="layout">
      <div class="card">
        <div class="card-main">
          <div class="card-content">
            {nav_html}
            <div class="topline">
              <div class="progress">{progress}</div>
              <div class="user-status">
                {escape(username)} · {practiced_count} practiced
                {"<a class=\"logout\" href=\"/admin\">Admin</a>" if is_admin else ""}
                <a class="logout" href="/logout">Logout</a>
              </div>
            </div>
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


def render_menu(username, user):
    nav_html = render_nav(username, user, "メニュー")
    return f"""<!doctype html>
<html lang="ja">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>練習メニュー</title>
    <style>
      body {{
        font-family: Georgia, "Times New Roman", serif;
        background: #f5f0e6;
        color: #3d3630;
        margin: 0;
        padding: 32px;
      }}
      .wrap {{
        max-width: 880px;
        margin: 0 auto;
      }}
      .topline {{
        display: flex;
        justify-content: space-between;
        gap: 16px;
        align-items: center;
        margin-bottom: 20px;
      }}
      .nav {{
        display: flex;
        flex-wrap: wrap;
        gap: 12px;
      }}
      .nav a, .logout {{
        color: #8fa68e;
        font-size: 13px;
        font-weight: 600;
        text-decoration: none;
      }}
      .nav a.active {{
        color: #4a4239;
      }}
      .user-status {{
        color: #7a7065;
        font-size: 13px;
        text-align: right;
      }}
      h1 {{
        margin: 0 0 18px;
        font-size: 28px;
      }}
      .games {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
        gap: 16px;
      }}
      .game {{
        display: block;
        background: #fffef9;
        border: 1px solid #e8e0d4;
        border-radius: 12px;
        box-shadow: 0 12px 32px rgba(139, 125, 107, 0.12);
        color: inherit;
        padding: 22px;
        text-decoration: none;
      }}
      .game h2 {{
        margin: 0 0 8px;
        font-size: 20px;
      }}
      .game p {{
        margin: 0;
        color: #6b635c;
        font-size: 14px;
        line-height: 1.5;
      }}
      @media (max-width: 640px) {{
        body {{
          padding: 20px;
        }}
        .topline {{
          align-items: flex-start;
          flex-direction: column;
        }}
        .user-status {{
          text-align: left;
        }}
      }}
    </style>
  </head>
  <body>
    <main class="wrap">
      {nav_html}
      <h1>練習メニュー</h1>
      <section class="games">
        <a class="game" href="/verbs">
          <h2>動詞練習</h2>
          <p>イタリア語の動詞活用を入力して練習します。</p>
        </a>
        <a class="game" href="/flashcards">
          <h2>単語カード</h2>
          <p>イタリア語の単語を見て、日本語の意味を選びます。</p>
        </a>
        <a class="game" href="/cloze">
          <h2>穴埋め</h2>
          <p>イタリア語の文の空欄に入る単語を入力します。下に日本語訳が表示されます。</p>
        </a>
      </section>
    </main>
  </body>
</html>"""


def render_flashcards(username, user, card, options, result=None):
    nav_html = render_nav(username, user, "単語カード")
    new_badge = '<span class="new-badge">NEW</span>' if card.get("is_new") else ""
    result_html = ""
    if result:
        css_class = "ok" if result["ok"] else "bad"
        text = "正解です。" if result["ok"] else "不正解です。"
        result_html = (
            f'<div class="result {css_class}">{text} '
            f'答え: {escape(result["answer"])}</div>'
        )
    option_buttons = []
    for option in options:
        option_buttons.append(
            f'<button type="submit" name="choice" value="{escape(option)}">'
            f"{escape(option)}</button>"
        )
    return f"""<!doctype html>
<html lang="ja">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>単語カード</title>
    <style>
      body {{
        font-family: Georgia, "Times New Roman", serif;
        background: #f5f0e6;
        color: #3d3630;
        margin: 0;
        padding: 32px;
      }}
      .wrap {{
        max-width: 760px;
        margin: 0 auto;
      }}
      .topline {{
        display: flex;
        justify-content: space-between;
        gap: 16px;
        align-items: center;
        margin-bottom: 20px;
      }}
      .nav {{
        display: flex;
        flex-wrap: wrap;
        gap: 12px;
      }}
      .nav a, .logout {{
        color: #8fa68e;
        font-size: 13px;
        font-weight: 600;
        text-decoration: none;
      }}
      .nav a.active {{
        color: #4a4239;
      }}
      .user-status {{
        color: #7a7065;
        font-size: 13px;
        text-align: right;
      }}
      .card {{
        background: #fffef9;
        border: 1px solid #e8e0d4;
        border-radius: 12px;
        box-shadow: 0 12px 32px rgba(139, 125, 107, 0.12);
        padding: 28px;
      }}
      .prompt {{
        color: #6b635c;
        font-size: 14px;
        margin-bottom: 8px;
      }}
      .word {{
        font-size: 36px;
        font-weight: 600;
        margin-bottom: 22px;
      }}
      .new-badge {{
        background: #c4706a;
        border-radius: 999px;
        color: #fff;
        display: inline-block;
        font-size: 11px;
        margin-left: 8px;
        padding: 3px 7px;
        vertical-align: middle;
      }}
      .options {{
        display: grid;
        gap: 10px;
      }}
      button, .next {{
        background: #8fa68e;
        color: #fff;
        border: 0;
        border-radius: 10px;
        cursor: pointer;
        display: block;
        font-size: 16px;
        padding: 13px 16px;
        text-align: center;
        text-decoration: none;
      }}
      .result {{
        border-radius: 10px;
        font-size: 14px;
        margin-bottom: 18px;
        padding: 12px 14px;
      }}
      .ok {{
        background: #e9f1e8;
        color: #557a53;
      }}
      .bad {{
        background: #f7e7e4;
        color: #9b4d48;
      }}
      @media (max-width: 640px) {{
        body {{
          padding: 20px;
        }}
        .topline {{
          align-items: flex-start;
          flex-direction: column;
        }}
        .user-status {{
          text-align: left;
        }}
        .word {{
          font-size: 30px;
        }}
      }}
    </style>
  </head>
  <body>
    <main class="wrap">
      {nav_html}
      <section class="card">
        {result_html}
        <div class="prompt">この単語の意味は？</div>
        <div class="word">{escape(card["word"])} {new_badge}</div>
        <div class="prompt">あなたのELO: {int(user.get("elo", DEFAULT_ELO))} / 問題ELO: {int(card.get("question_elo", DEFAULT_ELO))}</div>
        <form method="post" action="/flashcards" class="options">
          <input type="hidden" name="word" value="{escape(card["word"])}" />
          <input type="hidden" name="answer" value="{escape(card["translation"])}" />
          <input type="hidden" name="question_id" value="{escape(str(card.get("question_id", "")))}" />
          {"".join(option_buttons)}
        </form>
      </section>
    </main>
  </body>
</html>"""


def render_cloze(username, user, question, result=None):
    nav_html = render_nav(username, user, "穴埋め")
    new_badge = '<span class="new-badge">NEW</span>' if question.get("is_new") else ""
    result_html = ""
    if result:
        css_class = "ok" if result["ok"] else "bad"
        text = "正解です。" if result["ok"] else "不正解です。"
        result_html = (
            f'<div class="result {css_class}">{text} '
            f'答え: {escape(result["answer"])}</div>'
        )
    return f"""<!doctype html>
<html lang="ja">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>穴埋め</title>
    <style>
      body {{
        font-family: Georgia, "Times New Roman", serif;
        background: #f5f0e6;
        color: #3d3630;
        margin: 0;
        padding: 32px;
      }}
      .wrap {{
        max-width: 760px;
        margin: 0 auto;
      }}
      .topline {{
        display: flex;
        justify-content: space-between;
        gap: 16px;
        align-items: center;
        margin-bottom: 20px;
      }}
      .nav {{
        display: flex;
        flex-wrap: wrap;
        gap: 12px;
      }}
      .nav a, .logout {{
        color: #8fa68e;
        font-size: 13px;
        font-weight: 600;
        text-decoration: none;
      }}
      .nav a.active {{
        color: #4a4239;
      }}
      .user-status {{
        color: #7a7065;
        font-size: 13px;
        text-align: right;
      }}
      .card {{
        background: #fffef9;
        border: 1px solid #e8e0d4;
        border-radius: 12px;
        box-shadow: 0 12px 32px rgba(139, 125, 107, 0.12);
        padding: 28px;
      }}
      .sentence {{
        font-size: 30px;
        font-weight: 600;
        line-height: 1.35;
        margin-bottom: 14px;
      }}
      .new-badge {{
        background: #c4706a;
        border-radius: 999px;
        color: #fff;
        display: inline-block;
        font-size: 11px;
        margin-left: 8px;
        padding: 3px 7px;
        vertical-align: middle;
      }}
      .translation, .elo-line {{
        color: #6b635c;
        font-size: 14px;
        margin-bottom: 16px;
      }}
      .answer-form {{
        display: flex;
        gap: 10px;
      }}
      input {{
        flex: 1;
        min-width: 0;
        padding: 12px 14px;
        font-size: 16px;
        border: 2px solid #d8d0c4;
        border-radius: 8px;
        background: #fffef9;
      }}
      input:focus {{
        border-color: #8fa68e;
        outline: none;
      }}
      button {{
        background: #8fa68e;
        color: #fff;
        border: 0;
        border-radius: 10px;
        cursor: pointer;
        font-size: 16px;
        padding: 12px 18px;
      }}
      .result {{
        border-radius: 10px;
        font-size: 14px;
        margin-bottom: 18px;
        padding: 12px 14px;
      }}
      .ok {{
        background: #e9f1e8;
        color: #557a53;
      }}
      .bad {{
        background: #f7e7e4;
        color: #9b4d48;
      }}
      @media (max-width: 640px) {{
        body {{
          padding: 20px;
        }}
        .topline, .answer-form {{
          align-items: stretch;
          flex-direction: column;
        }}
        .user-status {{
          text-align: left;
        }}
        .sentence {{
          font-size: 24px;
        }}
      }}
    </style>
  </head>
  <body>
    <main class="wrap">
      {nav_html}
      <section class="card">
        {result_html}
        <div class="sentence">{escape(question["sentence"])} {new_badge}</div>
        <div class="translation">{escape(question["translation"])}</div>
        <div class="elo-line">あなたのELO: {int(user.get("elo", DEFAULT_ELO))} / 問題ELO: {int(question.get("question_elo", DEFAULT_ELO))}</div>
        <form method="post" action="/cloze" class="answer-form">
          <input name="answer" type="text" autocomplete="off" autofocus />
          <button type="submit">確認</button>
          <input type="hidden" name="question_id" value="{escape(str(question["question_id"]))}" />
          <input type="hidden" name="correct_answer" value="{escape(question["answer"])}" />
        </form>
      </section>
    </main>
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


def normalize_answer(value):
    cleaned = value.strip()
    while cleaned.endswith("."):
        cleaned = cleaned[:-1].rstrip()
    return cleaned


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

    if path == "/logout":
        headers = [("Content-Type", "text/html; charset=utf-8")]
        clear_session_cookie(headers)
        return redirect(start_response, "/", headers)

    if path == "/login" and environ.get("REQUEST_METHOD") == "POST":
        form = parse_post(environ)
        name = form.get("name", "").strip()
        password = form.get("password", "")
        users = load_users()

        if not name:
            body = render_login("名前を入力してください。")
            start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
            return [body.encode("utf-8")]

        user = users["users"].get(name)
        if not user:
            body = render_login("名前またはパスワードが違います。")
            start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
            return [body.encode("utf-8")]

        if not user.get("password_reset_required") and (
            not password or not verify_password(password, user.get("password", ""))
        ):
            body = render_login("名前またはパスワードが違います。")
            start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
            return [body.encode("utf-8")]

        user["session_token"] = secrets.token_urlsafe(32)
        save_users(users)

        headers = []
        set_session_cookie(headers, user["session_token"])
        return redirect(start_response, "/", headers)

    username, user = current_user(environ)
    if not user:
        body = render_login()
        start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
        return [body.encode("utf-8")]

    if user.get("password_reset_required"):
        if path == "/set-password" and environ.get("REQUEST_METHOD") == "POST":
            form = parse_post(environ)
            password = form.get("password", "")
            confirm_password = form.get("confirm_password", "")
            if len(password) < 4:
                body = render_password_setup(username, "4文字以上で入力してください。")
                start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
                return [body.encode("utf-8")]
            if password != confirm_password:
                body = render_password_setup(username, "パスワードが一致しません。")
                start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
                return [body.encode("utf-8")]
            users = load_users()
            saved_user = users["users"].get(username)
            if saved_user:
                saved_user["password"] = password_hash(password)
                saved_user["password_reset_required"] = False
                save_users(users)
            return redirect(start_response, "/")

        body = render_password_setup(username)
        start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
        return [body.encode("utf-8")]

    if path == "/admin":
        if not user.get("is_admin"):
            return redirect(start_response, "/")
        users = load_users()
        body = render_admin(users)
        start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
        return [body.encode("utf-8")]

    if path == "/admin/content":
        if not user.get("is_admin"):
            return redirect(start_response, "/")
        body = render_content_admin(load_pending_content())
        start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
        return [body.encode("utf-8")]

    if path == "/admin/content/approve" and environ.get("REQUEST_METHOD") == "POST":
        if not user.get("is_admin"):
            return redirect(start_response, "/")
        form = parse_post(environ)
        content_id = form.get("id", "")
        message = "承認しました。"
        error = ""
        with get_db() as conn:
            row = conn.execute(
                """
                SELECT id, content_type, payload_json
                FROM pending_content
                WHERE id = ? AND status = 'pending'
                """,
                (content_id,),
            ).fetchone()
            if not row:
                error = "候補が見つかりません。"
                message = ""
            else:
                payload = json.loads(row["payload_json"])
                if row["content_type"] == "cloze":
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO cloze_questions
                            (sentence, answer, translation, elo, active, status, is_new)
                        VALUES (?, ?, ?, ?, 1, 'approved', 1)
                        """,
                        (
                            payload.get("sentence", ""),
                            payload.get("answer", ""),
                            payload.get("translation", ""),
                            DEFAULT_ELO,
                        ),
                    )
                    conn.execute(
                        """
                        UPDATE pending_content
                        SET status = 'approved',
                            reviewed_by = ?,
                            reviewed_at = CURRENT_TIMESTAMP
                        WHERE id = ?
                        """,
                        (username, content_id),
                    )
                else:
                    error = "未対応の種類です。"
                    message = ""
        body = render_content_admin(load_pending_content(), message=message, error=error)
        start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
        return [body.encode("utf-8")]

    if path == "/admin/content/reject" and environ.get("REQUEST_METHOD") == "POST":
        if not user.get("is_admin"):
            return redirect(start_response, "/")
        form = parse_post(environ)
        content_id = form.get("id", "")
        with get_db() as conn:
            conn.execute(
                """
                UPDATE pending_content
                SET status = 'rejected',
                    reviewed_by = ?,
                    reviewed_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status = 'pending'
                """,
                (username, content_id),
            )
        body = render_content_admin(
            load_pending_content(), message="候補を却下しました。"
        )
        start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
        return [body.encode("utf-8")]

    if path == "/admin/create-user" and environ.get("REQUEST_METHOD") == "POST":
        if not user.get("is_admin"):
            return redirect(start_response, "/")
        form = parse_post(environ)
        name = form.get("name", "").strip()
        users = load_users()
        if not name:
            body = render_admin(users, error="ユーザー名を入力してください。")
        elif name in users["users"]:
            body = render_admin(users, error="そのユーザーはすでに存在します。")
        else:
            users["users"][name] = {
                "name": name,
                "password": "",
                "elo": DEFAULT_ELO,
                "password_reset_required": True,
                "state": {"practiced_count": 0},
                "session_token": "",
                "is_admin": False,
            }
            save_users(users)
            body = render_admin(users, message=f"{name}を作成しました。")
        start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
        return [body.encode("utf-8")]

    if path == "/admin/reset-password" and environ.get("REQUEST_METHOD") == "POST":
        if not user.get("is_admin"):
            return redirect(start_response, "/")
        form = parse_post(environ)
        name = form.get("name", "").strip()
        users = load_users()
        target = users["users"].get(name)
        if not target:
            body = render_admin(users, error="ユーザーが見つかりません。")
        elif target.get("is_admin"):
            body = render_admin(users, error="管理者のパスワードはここではリセットできません。")
        else:
            target["password"] = ""
            target["password_reset_required"] = True
            target["session_token"] = ""
            save_users(users)
            body = render_admin(users, message=f"{name}のパスワードをリセットしました。")
        start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
        return [body.encode("utf-8")]

    if path in ("", "/"):
        body = render_menu(username, user)
        start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
        return [body.encode("utf-8")]

    if path == "/flashcards":
        if environ.get("REQUEST_METHOD") == "POST":
            form = parse_post(environ)
            choice = form.get("choice", "")
            answer = form.get("answer", "")
            question_id = form.get("question_id", "")
            ok = choice == answer
            elo_result = None
            if question_id:
                elo_result = update_elo(username, int(question_id), ok, "flashcard")
            user = increment_practiced_count(username) or user
            card, options = pick_flashcard(user)
            body = render_flashcards(
                username,
                user,
                card,
                options,
                result={"ok": ok, "answer": answer, "elo": elo_result},
            )
        else:
            card, options = pick_flashcard(user)
            body = render_flashcards(username, user, card, options)
        start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
        return [body.encode("utf-8")]

    if path == "/cloze":
        if environ.get("REQUEST_METHOD") == "POST":
            form = parse_post(environ)
            user_answer = normalize_answer(form.get("answer", ""))
            correct_answer = normalize_answer(form.get("correct_answer", ""))
            question_id = form.get("question_id", "")
            ok = user_answer.lower() == correct_answer.lower()
            if question_id:
                update_cloze_elo(username, int(question_id), ok)
            user = increment_practiced_count(username) or user
            question = pick_cloze_question(user)
            body = render_cloze(
                username,
                user,
                question,
                result={"ok": ok, "answer": correct_answer},
            )
        else:
            question = pick_cloze_question(user)
            body = render_cloze(username, user, question)
        start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
        return [body.encode("utf-8")]

    if path == "/verbs" and environ.get("REQUEST_METHOD") == "POST":
        form = parse_post(environ)
        state = decode_state(form.get("state", ""))
        user_answer = normalize_answer(form.get("user_answer", ""))
        correct = normalize_answer(form.get("q_answer", ""))
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
        question_id = form.get("q_question_id", "")
        if question_id:
            update_elo(username, int(question_id), ok, "verb_form")
        user = increment_practiced_count(username) or user

        finished = state["count"] >= TOTAL_QUESTIONS
        question = None if finished else pick_question(user)
        count = practiced_count(user)
        body = render_page(
            question,
            state,
            username,
            count,
            user_elo=int(user.get("elo", DEFAULT_ELO)),
            is_admin=user.get("is_admin", False),
            finished=finished,
        )
    elif path == "/verbs":
        state = {"count": 0, "history": []}
        question = pick_question(user)
        count = practiced_count(user)
        body = render_page(
            question,
            state,
            username,
            count,
            user_elo=int(user.get("elo", DEFAULT_ELO)),
            is_admin=user.get("is_admin", False),
            finished=False,
        )
    else:
        return redirect(start_response, "/")

    start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
    return [body.encode("utf-8")]


if __name__ == "__main__":
    from wsgiref.simple_server import make_server

    with make_server("0.0.0.0", 8000, application) as httpd:
        print("Serving on http://127.0.0.1:8000")
        httpd.serve_forever()
