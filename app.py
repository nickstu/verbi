import base64
import hashlib
import hmac
import json
import os
import random
import secrets
import sqlite3
import math
import re
import unicodedata
import contextvars
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from http.cookiejar import CookieJar
from html import escape, unescape
from urllib.parse import parse_qs, quote_plus, urljoin
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen


DATA_DIR = os.path.join(os.path.dirname(__file__), "data", "verbs")
USERS_PATH = os.path.join(os.path.dirname(__file__), "data", "users.json")
DB_PATH = os.environ.get(
    "VERBI_DB_PATH",
    os.path.join(os.path.dirname(__file__), "data", "runtime.db"),
)
MATERIAL_DB_PATHS = {
    "it_ja": os.path.join(os.path.dirname(__file__), "data", "verbi.db"),
    "ja_en": os.path.join(os.path.dirname(__file__), "data", "japanese_english.db"),
}
STUDY_LANGUAGES = {
    "it_ja": {
        "label": "Italiano -> 日本語",
        "short": "イタリア語",
        "flashcard_description": "イタリア語の単語を見て、日本語の意味を選びます。",
        "cloze_description": "イタリア語の文の空欄に入る単語を入力します。下に日本語訳が表示されます。",
        "verb_enabled": True,
    },
    "ja_en": {
        "label": "English -> 日本語",
        "short": "英語",
        "flashcard_description": "英語の単語を見て、日本語の意味を選びます。",
        "cloze_description": "英語の文の空欄に入る語を入力します。下に日本語訳が表示されます。",
        "verb_enabled": False,
    },
}
DEFAULT_STUDY_LANGUAGE = "it_ja"
ACTIVE_MATERIAL_DB = contextvars.ContextVar("ACTIVE_MATERIAL_DB", default=MATERIAL_DB_PATHS[DEFAULT_STUDY_LANGUAGE])
DB_DIR = os.path.dirname(DB_PATH) or os.path.join(os.path.dirname(__file__), "data")
TOTAL_QUESTIONS = 10
DEFAULT_DAILY_TARGET = 20
DEFAULT_ELO = 1200
ELO_K = 32
NEW_CONTENT_CHANCE = 0.10
SCRAPER_DEFAULT_SOURCES = [
    "https://api.tatoeba.org/v1/sentences?lang=ita&q={query}&trans:lang=jpn&trans:is_direct=yes&showtrans=matching&sort=relevance&limit=500",
    "https://it.wikisource.org/wiki/Novelle_per_un_anno",
    "https://it.wikisource.org/wiki/Il_fu_Mattia_Pascal",
    "https://www.galileonet.it/feed/",
    "https://www.doppiozero.com/rss.xml",
    "https://www.iltascabile.com/feed/",
]
SCRAPER_DEFAULT_SOURCES_BY_LANGUAGE = {
    "it_ja": SCRAPER_DEFAULT_SOURCES,
    "ja_en": [
        "https://api.tatoeba.org/v1/sentences?lang=eng&q={query}&trans:lang=jpn&trans:is_direct=yes&showtrans=matching&sort=relevance&limit=500",
    ],
}
SCRAPER_SOURCE_LIBRARY = [
    ("Tatoeba + Japanese", "didattico/traduzioni", "https://api.tatoeba.org/v1/sentences?lang=ita&q={query}&trans:lang=jpn&trans:is_direct=yes&showtrans=matching&sort=relevance&limit=500"),
    ("Wikisource - Novelle per un anno", "storie/libri", "https://it.wikisource.org/wiki/Novelle_per_un_anno"),
    ("Wikisource - Il fu Mattia Pascal", "storie/libri", "https://it.wikisource.org/wiki/Il_fu_Mattia_Pascal"),
    ("Project Gutenberg - Italiano", "libri", "https://www.gutenberg.org/browse/languages/it"),
    ("Il Tascabile", "cultura/saggi", "https://www.iltascabile.com/feed/"),
    ("Doppiozero", "cultura/saggi", "https://www.doppiozero.com/rss.xml"),
    ("Rivista Studio", "blog/cultura", "https://www.rivistastudio.com/feed/"),
    ("Giap", "blog/storie", "https://www.wumingfoundation.com/giap/feed/"),
    ("Valigia Blu", "blog/analisi", "https://www.valigiablu.it/feed/"),
    ("Galileo", "scienza", "https://www.galileonet.it/feed/"),
    ("Open", "attualita", "https://www.open.online/feed/"),
    ("Il Libraio", "libri", "https://www.illibraio.it/feed/"),
    ("Gambero Rosso", "cucina", "https://www.gamberorosso.it/feed/"),
    ("Pagella Politica", "fact checking", "https://pagellapolitica.it/feed"),
    ("ANSA", "notizie brevi", "https://www.ansa.it/sito/ansait_rss.xml"),
]
SCRAPER_SOURCE_LIBRARY_BY_LANGUAGE = {
    "it_ja": SCRAPER_SOURCE_LIBRARY,
    "ja_en": [
        ("Tatoeba English + Japanese", "didattico/traduzioni", "https://api.tatoeba.org/v1/sentences?lang=eng&q={query}&trans:lang=jpn&trans:is_direct=yes&showtrans=matching&sort=relevance&limit=500"),
        ("Tatoeba English", "didattico", "https://api.tatoeba.org/v1/sentences?lang=eng&q={query}&sort=relevance&limit=500"),
    ],
}
SCRAPER_MAX_SOURCE_LINKS = 4
SCRAPER_MAX_SENTENCES = 80
SCRAPER_TIMEOUT_SECONDS = 4
APP_TIMEZONE = timezone(timedelta(hours=9))
PERSON_SLOTS = [
    ("1", "SG", "io"),
    ("2", "SG", "tu"),
    ("3", "SG", "lui/lei"),
    ("1", "PL", "noi"),
    ("2", "PL", "voi"),
    ("3", "PL", "loro"),
]
SUPPORTED_TENSES = {
    "presente": {"label": "presente", "verbecc_tense": "presente"},
    "passato prossimo": {"label": "passato prossimo", "verbecc_tense": "passato-prossimo"},
}
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
DB_INITIALIZED = set()
VERBECC_CONJUGATOR = None


def stable_digest(*parts):
    raw = "\x1f".join(str(part or "") for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def make_question_uid(kind, prompt):
    return f"q_{stable_digest('question', kind, prompt)[:24]}"


def make_cloze_uid(sentence, answer):
    return f"cloze_{stable_digest('cloze', sentence, answer)[:24]}"


def question_content_hash(kind, prompt, answer):
    return stable_digest("question-content", kind, prompt, answer)


def cloze_content_hash(sentence, answer, translation):
    return stable_digest("cloze-content", sentence, answer, translation)


def migrate_content_identity(conn):
    for table in ("questions", "cloze_questions"):
        columns = {
            row["name"]
            for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if "uid" not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN uid TEXT NOT NULL DEFAULT ''")
        if "content_hash" not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN content_hash TEXT NOT NULL DEFAULT ''")
        if "revision" not in columns:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN revision INTEGER NOT NULL DEFAULT 1")

    for row in conn.execute(
        "SELECT id, kind, prompt, answer FROM questions WHERE uid = '' OR content_hash = ''"
    ).fetchall():
        conn.execute(
            """
            UPDATE questions
            SET uid = CASE WHEN uid = '' THEN ? ELSE uid END,
                content_hash = CASE WHEN content_hash = '' THEN ? ELSE content_hash END
            WHERE id = ?
            """,
            (
                make_question_uid(row["kind"], row["prompt"]),
                question_content_hash(row["kind"], row["prompt"], row["answer"]),
                row["id"],
            ),
        )

    for row in conn.execute(
        "SELECT id, sentence, answer, translation FROM cloze_questions WHERE uid = '' OR content_hash = ''"
    ).fetchall():
        conn.execute(
            """
            UPDATE cloze_questions
            SET uid = CASE WHEN uid = '' THEN ? ELSE uid END,
                content_hash = CASE WHEN content_hash = '' THEN ? ELSE content_hash END
            WHERE id = ?
            """,
            (
                make_cloze_uid(row["sentence"], row["answer"]),
                cloze_content_hash(row["sentence"], row["answer"], row["translation"]),
                row["id"],
            ),
        )

    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_questions_uid ON questions(uid) WHERE uid <> ''")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_cloze_questions_uid ON cloze_questions(uid) WHERE uid <> ''")
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


def material_db_path_for_language(language):
    return MATERIAL_DB_PATHS.get(language, MATERIAL_DB_PATHS[DEFAULT_STUDY_LANGUAGE])


def get_db(path=None, foreign_keys=True):
    conn = sqlite3.connect(path or ACTIVE_MATERIAL_DB.get())
    conn.row_factory = sqlite3.Row
    conn.execute(f"PRAGMA foreign_keys = {'ON' if foreign_keys else 'OFF'}")
    return conn


def get_runtime_db():
    return get_db(DB_PATH, foreign_keys=False)


def study_language(user):
    language = user.get("study_language") or DEFAULT_STUDY_LANGUAGE
    if language not in STUDY_LANGUAGES:
        return DEFAULT_STUDY_LANGUAGE
    return language


def scraper_language(value):
    return value if value in STUDY_LANGUAGES else study_language({})


def set_active_material_key(language):
    ACTIVE_MATERIAL_DB.set(material_db_path_for_language(scraper_language(language)))


def set_active_material_language(user):
    ACTIVE_MATERIAL_DB.set(material_db_path_for_language(study_language(user)))


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


def init_db(path=None):
    global DB_INITIALIZED
    if not isinstance(DB_INITIALIZED, set):
        DB_INITIALIZED = set()
    db_path = path or ACTIVE_MATERIAL_DB.get()
    if db_path in DB_INITIALIZED:
        return

    db_dir = os.path.dirname(db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    with get_db(db_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                name TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL DEFAULT '',
                practiced_count INTEGER NOT NULL DEFAULT 0,
                elo INTEGER NOT NULL DEFAULT 1200,
                daily_target INTEGER NOT NULL DEFAULT 20,
                daily_streak INTEGER NOT NULL DEFAULT 0,
                daily_last_completed TEXT NOT NULL DEFAULT '',
                daily_vacation_mode INTEGER NOT NULL DEFAULT 0,
                daily_state_json TEXT NOT NULL DEFAULT '',
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
                uid TEXT NOT NULL DEFAULT '',
                kind TEXT NOT NULL,
                verb_id INTEGER NOT NULL REFERENCES verbs(id) ON DELETE CASCADE,
                verb_form_id INTEGER REFERENCES verb_forms(id) ON DELETE CASCADE,
                prompt TEXT NOT NULL,
                answer TEXT NOT NULL,
                content_hash TEXT NOT NULL DEFAULT '',
                revision INTEGER NOT NULL DEFAULT 1,
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
                question_uid TEXT NOT NULL DEFAULT '',
                question_revision INTEGER NOT NULL DEFAULT 1,
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
                uid TEXT NOT NULL DEFAULT '',
                sentence TEXT NOT NULL UNIQUE,
                answer TEXT NOT NULL,
                translation TEXT NOT NULL,
                content_hash TEXT NOT NULL DEFAULT '',
                revision INTEGER NOT NULL DEFAULT 1,
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
                cloze_question_uid TEXT NOT NULL DEFAULT '',
                cloze_question_revision INTEGER NOT NULL DEFAULT 1,
                correct INTEGER NOT NULL,
                user_elo_before INTEGER NOT NULL,
                user_elo_after INTEGER NOT NULL,
                question_elo_before INTEGER NOT NULL,
                question_elo_after INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS user_card_state (
                user_name TEXT NOT NULL REFERENCES users(name) ON DELETE CASCADE,
                card_uid TEXT NOT NULL,
                card_type TEXT NOT NULL,
                first_seen TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_seen TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                seen_count INTEGER NOT NULL DEFAULT 0,
                correct_count INTEGER NOT NULL DEFAULT 0,
                card_revision INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (user_name, card_uid)
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

            CREATE TABLE IF NOT EXISTS content_sources (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                url TEXT NOT NULL,
                license_name TEXT NOT NULL,
                license_url TEXT NOT NULL,
                attribution TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )

        conn.execute(
            """
            INSERT INTO content_sources
                (slug, name, url, license_name, license_url, attribution)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(slug) DO UPDATE SET
                name = excluded.name,
                url = excluded.url,
                license_name = excluded.license_name,
                license_url = excluded.license_url,
                attribution = excluded.attribution
            """,
            (
                "verbecc",
                "Verbecc",
                "https://github.com/bretttolbert/verbecc",
                "GNU Lesser General Public License v3.0",
                "https://www.gnu.org/licenses/lgpl-3.0.html",
                "Italian conjugation data and templates generated through Verbecc with ML prediction disabled.",
            ),
        )

        user_columns = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(users)").fetchall()
        }
        user_migrations = {
            "elo": f"INTEGER NOT NULL DEFAULT {DEFAULT_ELO}",
            "daily_target": f"INTEGER NOT NULL DEFAULT {DEFAULT_DAILY_TARGET}",
            "daily_streak": "INTEGER NOT NULL DEFAULT 0",
            "daily_last_completed": "TEXT NOT NULL DEFAULT ''",
            "daily_vacation_mode": "INTEGER NOT NULL DEFAULT 0",
            "daily_state_json": "TEXT NOT NULL DEFAULT ''",
            "study_language": f"TEXT NOT NULL DEFAULT '{DEFAULT_STUDY_LANGUAGE}'",
        }
        for column, definition in user_migrations.items():
            if column not in user_columns:
                conn.execute(f"ALTER TABLE users ADD COLUMN {column} {definition}")

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
            if "source_id" not in columns:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN source_id INTEGER")

        for table in ("verbs", "verb_forms", "pending_content"):
            columns = {
                row["name"]
                for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
            }
            if "source_id" not in columns:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN source_id INTEGER")

        event_migrations = {
            "practice_events": {
                "question_uid": "TEXT NOT NULL DEFAULT ''",
                "question_revision": "INTEGER NOT NULL DEFAULT 1",
            },
            "cloze_practice_events": {
                "cloze_question_uid": "TEXT NOT NULL DEFAULT ''",
                "cloze_question_revision": "INTEGER NOT NULL DEFAULT 1",
            },
        }
        for table, migrations in event_migrations.items():
            columns = {
                row["name"]
                for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
            }
            for column, definition in migrations.items():
                if column not in columns:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

        is_italian_material_db = os.path.abspath(db_path) == os.path.abspath(MATERIAL_DB_PATHS["it_ja"])

        verb_count = conn.execute("SELECT COUNT(*) FROM verbs").fetchone()[0]
        if verb_count == 0 and is_italian_material_db:
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
        if cloze_count == 0 and is_italian_material_db:
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

        migrate_content_identity(conn)
        conn.execute(
            """
            UPDATE practice_events
            SET question_uid = (
                    SELECT uid FROM questions WHERE questions.id = practice_events.question_id
                ),
                question_revision = (
                    SELECT revision FROM questions WHERE questions.id = practice_events.question_id
                )
            WHERE question_uid = ''
                AND EXISTS (
                    SELECT 1 FROM questions WHERE questions.id = practice_events.question_id
                )
            """
        )
        conn.execute(
            """
            UPDATE cloze_practice_events
            SET cloze_question_uid = (
                    SELECT uid FROM cloze_questions WHERE cloze_questions.id = cloze_practice_events.cloze_question_id
                ),
                cloze_question_revision = (
                    SELECT revision FROM cloze_questions WHERE cloze_questions.id = cloze_practice_events.cloze_question_id
                )
            WHERE cloze_question_uid = ''
                AND EXISTS (
                    SELECT 1 FROM cloze_questions WHERE cloze_questions.id = cloze_practice_events.cloze_question_id
                )
            """
        )

        is_runtime_db = os.path.abspath(db_path) == os.path.abspath(DB_PATH)
        user_count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
        if is_runtime_db and user_count == 0 and os.path.exists(USERS_PATH):
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
                            daily_target,
                            daily_streak,
                            daily_last_completed,
                            daily_vacation_mode,
                            session_token,
                            password_reset_required,
                            is_admin,
                            state_json
                        )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        name,
                        user.get("password", ""),
                        int(state.get("practiced_count", 0)),
                        int(user.get("elo", DEFAULT_ELO)),
                        int(user.get("daily_target", DEFAULT_DAILY_TARGET)),
                        int(user.get("daily_streak", 0)),
                        user.get("daily_last_completed", ""),
                        1 if user.get("daily_vacation_mode") else 0,
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

    DB_INITIALIZED.add(db_path)


def load_users():
    init_db(DB_PATH)
    users = {}
    with get_runtime_db() as conn:
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
            "daily_target": int(row["daily_target"]),
            "daily_streak": int(row["daily_streak"]),
            "daily_last_completed": row["daily_last_completed"],
            "daily_vacation_mode": bool(row["daily_vacation_mode"]),
            "study_language": row["study_language"] if "study_language" in row.keys() else DEFAULT_STUDY_LANGUAGE,
            "state": state,
            "session_token": row["session_token"],
            "password_reset_required": bool(row["password_reset_required"]),
            "is_admin": bool(row["is_admin"]) or row["name"] == "admin",
        }
    return {"users": users}


def has_users():
    init_db(DB_PATH)
    with get_runtime_db() as conn:
        return conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] > 0


def save_users(data):
    init_db(DB_PATH)
    with get_runtime_db() as conn:
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
                        daily_target,
                        daily_streak,
                        daily_last_completed,
                        daily_vacation_mode,
                        study_language,
                        session_token,
                        password_reset_required,
                        is_admin,
                        state_json
                    )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    password_hash = excluded.password_hash,
                    practiced_count = excluded.practiced_count,
                    elo = excluded.elo,
                    daily_target = excluded.daily_target,
                    daily_streak = excluded.daily_streak,
                    daily_last_completed = excluded.daily_last_completed,
                    daily_vacation_mode = excluded.daily_vacation_mode,
                    study_language = excluded.study_language,
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
                    int(user.get("daily_target", DEFAULT_DAILY_TARGET)),
                    int(user.get("daily_streak", 0)),
                    user.get("daily_last_completed", ""),
                    1 if user.get("daily_vacation_mode") else 0,
                    study_language(user),
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


def render_first_admin_setup(error=""):
    error_html = f'<div class="login-error">{escape(error)}</div>' if error else ""
    return f"""<!doctype html>
<html lang="ja">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>初期設定</title>
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
        width: min(360px, calc(100vw - 40px));
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
        line-height: 1.5;
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
    <form method="post" action="/setup" class="login-window">
      <h1>初期設定</h1>
      <p>ユーザーがまだ存在しません。最初の管理者アカウントを作成してください。</p>
      {error_html}
      <label for="name">管理者名</label>
      <input id="name" name="name" type="text" value="admin" autocomplete="username" required />
      <label for="password">パスワード</label>
      <input id="password" name="password" type="password" autocomplete="new-password" required />
      <label for="confirm_password">パスワード確認</label>
      <input id="confirm_password" name="confirm_password" type="password" autocomplete="new-password" required />
      <button type="submit">管理者を作成</button>
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
<html lang="ja">
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
        max-width: 820px;
        margin: 0 auto;
        background: #fffef9;
        border: 1px solid #e8e0d4;
        border-radius: 12px;
        box-shadow: 0 12px 32px rgba(139, 125, 107, 0.12);
        padding: 24px;
      }}
      .top, .admin-actions {{
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
      a, .admin-button {{
        color: #8fa68e;
        font-weight: 600;
        text-decoration: none;
      }}
      .admin-button {{
        background: #8fa68e;
        border-radius: 10px;
        color: #fff;
        display: inline-block;
        padding: 11px 16px;
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
        .top, .admin-actions, form.create {{
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
      <div class="admin-actions">
        <a class="admin-button" href="/admin/content">カード管理</a>
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


def load_approved_cards():
    init_db()
    cards = []
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT
                q.id,
                q.kind,
                q.answer,
                q.elo,
                q.is_new,
                v.infinitive,
                v.ja,
                vf.tense,
                vf.pronoun,
                vf.gender
            FROM questions q
            JOIN verbs v ON v.id = q.verb_id
            LEFT JOIN verb_forms vf ON vf.id = q.verb_form_id
            WHERE q.active = 1 AND q.status = 'approved'
            ORDER BY q.kind, v.infinitive, q.id
            LIMIT 500
            """
        ).fetchall()
        for row in rows:
            cards.append(
                {
                    "id": row["id"],
                    "card_type": row["kind"],
                    "answer": row["answer"],
                    "elo": row["elo"],
                    "is_new": bool(row["is_new"]),
                    "infinitive": row["infinitive"],
                    "ja": row["ja"],
                    "tense": row["tense"] or "",
                    "pronoun": row["pronoun"] or "",
                    "gender": row["gender"] or "",
                }
            )

        rows = conn.execute(
            """
            SELECT id, uid, revision, sentence, answer, translation, elo, is_new
            FROM cloze_questions
            WHERE active = 1 AND status = 'approved'
            ORDER BY id DESC
            LIMIT 500
            """
        ).fetchall()
        for row in rows:
            cards.append(
                {
                    "id": row["id"],
                    "card_type": "cloze",
                    "sentence": row["sentence"],
                    "answer": row["answer"],
                    "translation": row["translation"],
                    "elo": row["elo"],
                    "is_new": bool(row["is_new"]),
                }
            )
    return cards


def source_id_by_slug(conn, slug):
    row = conn.execute(
        "SELECT id FROM content_sources WHERE slug = ?",
        (slug,),
    ).fetchone()
    return row["id"] if row else None


def get_verbecc_conjugator():
    global VERBECC_CONJUGATOR
    if VERBECC_CONJUGATOR is not None:
        return VERBECC_CONJUGATOR
    try:
        import verbecc
        import verbecc.src.defs.types.data.verbs as verbs_mod
    except ImportError as exc:
        raise RuntimeError("Verbecc is not installed.") from exc
    # Avoid Verbecc trying to train/write an ML fallback model at runtime.
    verbs_mod.config.ENABLE_ML_PREDICTION = False
    VERBECC_CONJUGATOR = verbecc.CompleteConjugator(verbecc.LangCodeISO639_1.it)
    return VERBECC_CONJUGATOR


def strip_verbecc_pronoun(value, pronoun):
    value = value.strip()
    prefix = f"{pronoun} "
    if pronoun and value.startswith(prefix):
        return value[len(prefix):].strip()
    return value


def lookup_verbecc_forms(infinitive, tense):
    tense_info = SUPPORTED_TENSES.get(tense)
    if not tense_info or "verbecc_tense" not in tense_info:
        raise ValueError("Unsupported tense.")
    conjugator = get_verbecc_conjugator()
    try:
        conjugation = conjugator.conjugate(infinitive)
        rows = conjugation.get_data()["moods"]["indicativo"][tense_info["verbecc_tense"]]
    except Exception as exc:
        raise ValueError(f"Verbecc could not conjugate {infinitive} {tense}: {exc}") from exc
    forms = []
    seen = set()
    for row in rows:
        pronoun = row.get("pr", "")
        person = row.get("p", "")
        number = "SG" if row.get("n") == "s" else "PL" if row.get("n") == "p" else ""
        gender = {"m": "masculine", "f": "feminine"}.get(row.get("g", ""), "")
        for raw_value in row.get("c", []):
            value = strip_verbecc_pronoun(raw_value, pronoun)
            key = (pronoun, gender, value)
            if not value or key in seen:
                continue
            seen.add(key)
            forms.append(
                {
                    "person": person,
                    "number": number,
                    "pronoun": pronoun,
                    "gender": gender,
                    "value": value,
                }
            )
    if not forms:
        raise ValueError(f"Verbecc returned no {tense} forms for {infinitive}.")
    return forms


def import_verbecc_verb_tense(infinitive, ja, tense):
    infinitive = infinitive.strip().lower()
    ja = ja.strip()
    tense = tense.strip()
    if not infinitive or not ja:
        return False, "Verb and translation are required."
    try:
        forms = lookup_verbecc_forms(infinitive, tense)
    except (RuntimeError, ValueError) as exc:
        return False, str(exc)
    with get_db() as conn:
        source_id = source_id_by_slug(conn, "verbecc")
        verb_id = find_or_create_verb(conn, infinitive, ja)
        conn.execute(
            "UPDATE verbs SET source_id = ? WHERE id = ?",
            (source_id, verb_id),
        )
        seen_form_ids = []
        for form in forms:
            pronoun = form["pronoun"]
            value = form["value"]
            gender = form.get("gender", "")
            form_row = conn.execute(
                """
                SELECT id FROM verb_forms
                WHERE verb_id = ? AND tense = ? AND pronoun = ? AND gender = ?
                """,
                (verb_id, tense, pronoun, gender),
            )
            form_row = form_row.fetchone()
            if form_row:
                form_id = form_row["id"]
                conn.execute(
                    """
                    UPDATE verb_forms
                    SET value = ?, source_id = ?
                    WHERE id = ?
                    """,
                    (value, source_id, form_id),
                )
            else:
                cursor = conn.execute(
                    """
                    INSERT INTO verb_forms
                        (verb_id, tense, pronoun, value, gender, source_id)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (verb_id, tense, pronoun, value, gender, source_id),
                )
                form_id = cursor.lastrowid
            seen_form_ids.append(form_id)
            prompt = f"{infinitive}|{ja}|{tense}|{pronoun}|{gender}"
            uid = make_question_uid("verb_form", prompt)
            content_hash = question_content_hash("verb_form", prompt, value)
            conn.execute(
                """
                INSERT INTO questions
                    (uid, kind, verb_id, verb_form_id, prompt, answer, content_hash, revision, elo, active, status, is_new, source_id)
                VALUES (?, 'verb_form', ?, ?, ?, ?, ?, 1, ?, 1, 'approved', 1, ?)
                ON CONFLICT(kind, verb_id, verb_form_id) DO UPDATE SET
                    prompt = excluded.prompt,
                    answer = excluded.answer,
                    revision = CASE WHEN questions.content_hash <> excluded.content_hash THEN questions.revision + 1 ELSE questions.revision END,
                    content_hash = excluded.content_hash,
                    active = 1,
                    status = 'approved',
                    is_new = 1,
                    source_id = excluded.source_id
                """,
                (uid, verb_id, form_id, prompt, value, content_hash, DEFAULT_ELO, source_id),
            )
        if seen_form_ids:
            placeholders = ",".join("?" for _ in seen_form_ids)
            conn.execute(
                f"""
                UPDATE questions
                SET active = 0
                WHERE kind = 'verb_form'
                    AND verb_id = ?
                    AND verb_form_id IN (
                        SELECT id FROM verb_forms
                        WHERE verb_id = ? AND tense = ? AND id NOT IN ({placeholders})
                    )
                """,
                (verb_id, verb_id, tense, *seen_form_ids),
            )
    return True, f"Imported {infinitive} {tense} from Verbecc."


def load_verb_trees():
    init_db()
    trees = []
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT
                v.id AS verb_id,
                v.infinitive,
                v.ja,
                vf.tense,
                vf.pronoun,
                vf.gender,
                vf.value,
                q.id AS question_id,
                q.elo,
                q.is_new
            FROM verbs v
            JOIN verb_forms vf ON vf.verb_id = v.id
            JOIN questions q ON q.verb_form_id = vf.id
            WHERE q.kind = 'verb_form'
                AND q.active = 1
                AND q.status = 'approved'
            ORDER BY v.infinitive, vf.tense, vf.id
            LIMIT 1200
            """
        ).fetchall()
    by_verb = {}
    for row in rows:
        verb = by_verb.setdefault(
            row["verb_id"],
            {
                "id": row["verb_id"],
                "infinitive": row["infinitive"],
                "ja": row["ja"],
                "tenses": {},
            },
        )
        tense = verb["tenses"].setdefault(row["tense"], [])
        tense.append(
            {
                "pronoun": row["pronoun"],
                "gender": row["gender"] or "",
                "value": row["value"],
                "question_id": row["question_id"],
                "elo": row["elo"],
                "is_new": bool(row["is_new"]),
            }
        )
    for verb in by_verb.values():
        trees.append(verb)
    return trees


def card_label(card_type):
    return {
        "cloze": "穴埋め",
        "flashcard": "単語カード",
        "verb_form": "動詞練習",
    }.get(card_type, card_type)


def pending_summary(item):
    payload = item["payload"]
    content_type = item["content_type"]
    if content_type == "cloze":
        return [
            ("文", payload.get("sentence", "")),
            ("答え", payload.get("answer", "")),
            ("訳", payload.get("translation", "")),
        ]
    if content_type == "flashcard":
        return [
            ("単語", payload.get("word") or payload.get("infinitive", "")),
            ("答え", payload.get("translation") or payload.get("answer") or payload.get("ja", "")),
        ]
    if content_type == "verb_form":
        return [
            ("動詞", payload.get("infinitive") or payload.get("word", "")),
            ("訳", payload.get("ja") or payload.get("translation", "")),
            ("時制", payload.get("tense", "")),
            ("代名詞", payload.get("pronoun", "")),
            ("性", payload.get("gender", "")),
            ("答え", payload.get("answer") or payload.get("value", "")),
        ]
    return [(key, value) for key, value in payload.items()]


def render_pending_item(item):
    fields = "".join(
        f'<div><strong>{escape(str(label))}:</strong> {escape(str(value))}</div>'
        for label, value in pending_summary(item)
    )
    return (
        '<div class="content-item pending-item">'
        f'<div class="meta">#{item["id"]} · {escape(card_label(item["content_type"]))} · pending</div>'
        f"{fields}"
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


def render_approved_card(card):
    card_type = card["card_type"]
    hidden = (
        f'<input type="hidden" name="card_type" value="{escape(card_type)}" />'
        f'<input type="hidden" name="id" value="{card["id"]}" />'
    )
    common = (
        f'<div class="meta">#{card["id"]} · {escape(card_label(card_type))} · '
        f'ELO {int(card.get("elo", DEFAULT_ELO))}'
        f'{" · NEW" if card.get("is_new") else ""}</div>'
    )
    if card_type == "cloze":
        fields = f"""
          <label>文<input name="sentence" value="{escape(card.get("sentence", ""))}" /></label>
          <label>答え<input name="answer" value="{escape(card.get("answer", ""))}" /></label>
          <label>訳<input name="translation" value="{escape(card.get("translation", ""))}" /></label>
        """
    elif card_type == "flashcard":
        fields = f"""
          <label>単語<input name="infinitive" value="{escape(card.get("infinitive", ""))}" /></label>
          <label>訳<input name="ja" value="{escape(card.get("ja", ""))}" /></label>
        """
    else:
        fields = f"""
          <label>動詞<input name="infinitive" value="{escape(card.get("infinitive", ""))}" /></label>
          <label>訳<input name="ja" value="{escape(card.get("ja", ""))}" /></label>
          <label>時制<input name="tense" value="{escape(card.get("tense", ""))}" /></label>
          <label>代名詞<input name="pronoun" value="{escape(card.get("pronoun", ""))}" /></label>
          <label>性<input name="gender" value="{escape(card.get("gender", ""))}" /></label>
          <label>答え<input name="answer" value="{escape(card.get("answer", ""))}" /></label>
        """
    return f"""
      <div class="content-item">
        {common}
        <form method="post" action="/admin/content/edit" class="edit-card">
          {hidden}
          <div class="field-grid">{fields}</div>
          <div class="actions-row">
            <button type="submit">編集を保存</button>
        </form>
        <form method="post" action="/admin/content/delete" class="delete-card">
          {hidden}
          <button class="danger" type="submit">削除</button>
        </form>
          </div>
      </div>
    """


def render_approved_card(card):
    card_type = card["card_type"]
    hidden = (
        f'<input type="hidden" name="card_type" value="{escape(card_type)}" />'
        f'<input type="hidden" name="id" value="{card["id"]}" />'
    )
    common = (
        f'<div class="meta">#{card["id"]} · {escape(card_label(card_type))} · '
        f'ELO {int(card.get("elo", DEFAULT_ELO))}'
        f'{" · NEW" if card.get("is_new") else ""}</div>'
    )
    if card_type == "cloze":
        fields = f"""
          <label>文<input name="sentence" value="{escape(card.get("sentence", ""))}" /></label>
          <label>答え<input name="answer" value="{escape(card.get("answer", ""))}" /></label>
          <label>訳<input name="translation" value="{escape(card.get("translation", ""))}" /></label>
        """
    elif card_type == "flashcard":
        fields = f"""
          <label>単語<input name="infinitive" value="{escape(card.get("infinitive", ""))}" /></label>
          <label>訳<input name="ja" value="{escape(card.get("ja", ""))}" /></label>
        """
    else:
        fields = f"""
          <label>動詞<input name="infinitive" value="{escape(card.get("infinitive", ""))}" /></label>
          <label>訳<input name="ja" value="{escape(card.get("ja", ""))}" /></label>
          <label>時制<input name="tense" value="{escape(card.get("tense", ""))}" /></label>
          <label>代名詞<input name="pronoun" value="{escape(card.get("pronoun", ""))}" /></label>
          <label>性<input name="gender" value="{escape(card.get("gender", ""))}" /></label>
          <label>答え<input name="answer" value="{escape(card.get("answer", ""))}" /></label>
        """
    return f"""
      <div class="content-item">
        {common}
        <form method="post" action="/admin/content/edit" class="edit-card">
          {hidden}
          <div class="field-grid">{fields}</div>
          <div class="actions-row">
            <button type="submit">編集を保存</button>
          </div>
        </form>
        <div class="actions-row">
          <form method="post" action="/admin/content/delete" class="delete-card">
            {hidden}
            <button class="danger" type="submit">削除</button>
          </form>
        </div>
      </div>
    """


def compact_field(name, value, width_class=""):
    return (
        f'<input class="compact-input {width_class}" '
        f'name="{escape(name)}" value="{escape(value or "")}" />'
    )


def render_approved_card(card):
    card_type = card["card_type"]
    hidden = (
        f'<input type="hidden" name="card_type" value="{escape(card_type)}" />'
        f'<input type="hidden" name="id" value="{card["id"]}" />'
    )
    new_badge = '<span class="status-new">NEW</span>' if card.get("is_new") else ""
    meta = (
        f'<div class="compact-meta">#{card["id"]} '
        f'{escape(card_label(card_type))} '
        f'<span>ELO {int(card.get("elo", DEFAULT_ELO))}</span>{new_badge}</div>'
    )
    if card_type == "cloze":
        fields = (
            compact_field("sentence", card.get("sentence", ""), "wide")
            + compact_field("answer", card.get("answer", ""), "short")
            + compact_field("translation", card.get("translation", ""), "medium")
        )
    elif card_type == "flashcard":
        fields = (
            compact_field("infinitive", card.get("infinitive", ""), "medium")
            + compact_field("ja", card.get("ja", ""), "medium")
        )
    else:
        fields = (
            compact_field("infinitive", card.get("infinitive", ""), "medium")
            + compact_field("ja", card.get("ja", ""), "medium")
            + compact_field("tense", card.get("tense", ""), "short")
            + compact_field("pronoun", card.get("pronoun", ""), "short")
            + compact_field("gender", card.get("gender", ""), "short")
            + compact_field("answer", card.get("answer", ""), "short")
        )
    return f"""
      <div class="content-item compact-card">
        {meta}
        <form method="post" action="/admin/content/edit" class="compact-edit">
          {hidden}
          <div class="compact-fields">{fields}</div>
          <button title="保存" aria-label="保存" type="submit">💾</button>
        </form>
        <form method="post" action="/admin/content/reset-elo" class="compact-action">
          {hidden}
          <button title="ELOをリセット" aria-label="ELOをリセット" type="submit">↺</button>
        </form>
        <form method="post" action="/admin/content/delete" class="compact-action">
          {hidden}
          <button class="danger" title="削除" aria-label="削除" type="submit">🗑</button>
        </form>
      </div>
    """


def render_approved_card(card):
    card_type = card["card_type"]
    hidden = (
        f'<input type="hidden" name="card_type" value="{escape(card_type)}" />'
        f'<input type="hidden" name="id" value="{card["id"]}" />'
    )
    new_badge = '<span class="status-new">NEW</span>' if card.get("is_new") else ""
    meta = (
        f'<div class="compact-meta">#{card["id"]} '
        f'{escape(card_label(card_type))} '
        f'<span>ELO {int(card.get("elo", DEFAULT_ELO))}</span>{new_badge}</div>'
    )
    if card_type == "cloze":
        fields = (
            compact_field("sentence", card.get("sentence", ""), "wide")
            + compact_field("answer", card.get("answer", ""), "short")
            + compact_field("translation", card.get("translation", ""), "medium")
        )
    elif card_type == "flashcard":
        fields = (
            compact_field("infinitive", card.get("infinitive", ""), "medium")
            + compact_field("ja", card.get("ja", ""), "medium")
        )
    else:
        fields = (
            compact_field("infinitive", card.get("infinitive", ""), "medium")
            + compact_field("ja", card.get("ja", ""), "medium")
            + compact_field("tense", card.get("tense", ""), "short")
            + compact_field("pronoun", card.get("pronoun", ""), "short")
            + compact_field("gender", card.get("gender", ""), "short")
            + compact_field("answer", card.get("answer", ""), "short")
        )
    return f"""
      <div class="content-item compact-card">
        {meta}
        <form method="post" action="/admin/content/edit" class="compact-edit">
          {hidden}
          <div class="compact-fields">{fields}</div>
          <button title="Save" aria-label="Save" type="submit">&#128190;</button>
        </form>
        <form method="post" action="/admin/content/reset-elo" class="compact-action">
          {hidden}
          <button title="Reset ELO" aria-label="Reset ELO" type="submit">&#8634;</button>
        </form>
        <form method="post" action="/admin/content/delete" class="compact-action">
          {hidden}
          <button class="danger" title="Delete" aria-label="Delete" type="submit">&#128465;</button>
        </form>
      </div>
    """


def render_content_admin(items=None, approved_cards=None, message="", error=""):
    items = load_pending_content() if items is None else items
    approved_cards = load_approved_cards() if approved_cards is None else approved_cards
    message_html = f'<div class="notice ok">{escape(message)}</div>' if message else ""
    error_html = f'<div class="notice bad">{escape(error)}</div>' if error else ""
    pending_html = (
        "".join(render_pending_item(item) for item in items)
        if items
        else '<div class="empty">レビュー待ちのカードはありません。</div>'
    )
    approved_html = (
        "".join(render_approved_card(card) for card in approved_cards)
        if approved_cards
        else '<div class="empty">承認済みカードはありません。</div>'
    )
    return f"""<!doctype html>
<html lang="ja">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>カード管理</title>
    <style>
      body {{
        font-family: Georgia, "Times New Roman", serif;
        background: #f5f0e6;
        color: #3d3630;
        margin: 0;
        padding: 32px;
      }}
      .panel {{
        max-width: 1120px;
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
      a {{
        color: #8fa68e;
        font-weight: 600;
        text-decoration: none;
      }}
      .content-list {{
        display: grid;
        gap: 6px;
        max-height: 70vh;
        overflow-y: auto;
        padding-right: 4px;
      }}
      .content-item {{
        background: #faf7f0;
        border: 1px solid #e8e0d4;
        border-radius: 10px;
        padding: 16px;
      }}
      .compact-card {{
        align-items: center;
        display: grid;
        gap: 6px;
        grid-template-columns: 150px minmax(0, 1fr) 32px 32px;
        padding: 7px 8px;
      }}
      .meta, .empty {{
        color: #7a7065;
        font-size: 13px;
        margin-bottom: 8px;
      }}
      .compact-meta {{
        color: #6b635c;
        font-size: 12px;
        min-width: 0;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }}
      .status-new {{
        background: #c4706a;
        border-radius: 999px;
        color: #fff;
        display: inline-block;
        font-size: 10px;
        margin-left: 4px;
        padding: 2px 5px;
      }}
      .compact-edit {{
        align-items: center;
        display: grid;
        gap: 6px;
        grid-template-columns: minmax(0, 1fr) 32px;
        margin: 0;
        min-width: 0;
      }}
      .compact-fields {{
        align-items: center;
        display: flex;
        gap: 5px;
        min-width: 0;
        overflow-x: auto;
      }}
      .field-grid {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
        gap: 10px;
      }}
      label {{
        color: #6b635c;
        display: block;
        font-size: 13px;
      }}
      .compact-input {{
        flex: 1 1 130px;
        margin-top: 0;
        min-width: 72px;
        padding: 6px 7px;
      }}
      .compact-input.short {{
        flex-basis: 84px;
      }}
      .compact-input.medium {{
        flex-basis: 140px;
      }}
      .compact-input.wide {{
        flex-basis: 240px;
      }}
      input {{
        box-sizing: border-box;
        width: 100%;
        padding: 9px 10px;
        font-size: 14px;
        border: 1px solid #d8d0c4;
        border-radius: 8px;
        background: #fffef9;
        margin-top: 4px;
      }}
      button {{
        background: #8fa68e;
        color: #fff;
        border: 0;
        border-radius: 8px;
        cursor: pointer;
        font-size: 14px;
        height: 32px;
        padding: 0;
        width: 32px;
      }}
      button.secondary {{
        background: #b8aa97;
      }}
      button.danger {{
        background: #c4706a;
      }}
      .actions-row {{
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
        justify-content: flex-end;
        margin-top: 12px;
      }}
      .actions-row form {{
        margin: 0;
      }}
      .compact-action {{
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
        .top {{
          align-items: flex-start;
          flex-direction: column;
        }}
        .compact-card {{
          grid-template-columns: 1fr 32px 32px;
        }}
        .compact-meta {{
          grid-column: 1 / -1;
        }}
      }}
    </style>
  </head>
  <body>
    <main class="panel">
      <div class="top">
        <h1>カード管理</h1>
        <a href="/admin">管理へ戻る</a>
      </div>
      {message_html}
      {error_html}
      <h2>レビュー待ち</h2>
      <div class="content-list">{pending_html}</div>
      <h2>承認済みカード</h2>
      <div class="content-list">{approved_html}</div>
    </main>
  </body>
</html>"""


def admin_tab_link(tab, label, active_tab):
    css = "active" if tab == active_tab else ""
    return f'<a class="{css}" href="/admin/content?tab={escape(tab)}">{escape(label)}</a>'


def render_vocab_cards(cards):
    vocab = [card for card in cards if card["card_type"] == "flashcard"]
    return (
        "".join(render_approved_card(card) for card in vocab)
        if vocab
        else '<div class="empty">No vocabulary cards.</div>'
    )


def render_cloze_cards(cards):
    cloze = [card for card in cards if card["card_type"] == "cloze"]
    return (
        "".join(render_approved_card(card) for card in cloze)
        if cloze
        else '<div class="empty">No cloze cards.</div>'
    )


def tense_options(selected="presente"):
    return "".join(
        f'<option value="{escape(key)}" {"selected" if key == selected else ""}>{escape(info["label"])}</option>'
        for key, info in SUPPORTED_TENSES.items()
    )


def render_tense_import_form():
    return f"""
      <form method="post" action="/admin/content/import-tense" class="tense-import">
        <input name="infinitive" placeholder="andare" autocomplete="off" required />
        <input name="ja" placeholder="行く" autocomplete="off" required />
        <select name="tense">{tense_options()}</select>
        <button title="Import from Verbecc" aria-label="Import from Verbecc" type="submit">&#128190;</button>
      </form>
    """


def render_verb_trees():
    trees = load_verb_trees()
    if not trees:
        return '<div class="empty">No tense cards.</div>'
    html = []
    slot_order = {label: index for index, (_, _, label) in enumerate(PERSON_SLOTS)}
    for verb in trees:
        tense_blocks = []
        for tense, forms in sorted(verb["tenses"].items()):
            ordered = sorted(forms, key=lambda item: slot_order.get(item["pronoun"], 99))
            tense_hidden = (
                '<input type="hidden" name="card_type" value="verb_tense" />'
                f'<input type="hidden" name="verb_id" value="{verb["id"]}" />'
                f'<input type="hidden" name="tense" value="{escape(tense)}" />'
            )
            rows = []
            for item in ordered:
                new_badge = '<span class="status-new">NEW</span>' if item["is_new"] else ""
                pronoun_label = item["pronoun"]
                if item.get("gender"):
                    pronoun_label = f'{pronoun_label} ({item["gender"]})'
                rows.append(
                    '<div class="conj-row">'
                    f'<div class="pronoun-cell">{escape(pronoun_label)}</div>'
                    f'<div class="form-cell">{escape(item["value"])}</div>'
                    f'<div class="elo-cell">ELO {int(item["elo"])} {new_badge}</div>'
                    '</div>'
                )
            tense_blocks.append(
                '<div class="tense-block">'
                '<div class="tense-title-row">'
                f'<div class="tense-title">{escape(tense)}</div>'
                '<div class="tense-actions">'
                '<form method="post" action="/admin/content/reset-elo" class="mini-action">'
                f'{tense_hidden}<button title="Reset ELO" aria-label="Reset ELO" type="submit">&#8634;</button>'
                '</form>'
                '<form method="post" action="/admin/content/delete" class="mini-action">'
                f'{tense_hidden}<button class="danger" title="Delete" aria-label="Delete" type="submit">&#128465;</button>'
                '</form>'
                '</div>'
                '</div>'
                f'{"".join(rows)}'
                '</div>'
            )
        html.append(
            '<div class="verb-tree-card">'
            f'<div class="verb-tree-head"><strong>{escape(verb["infinitive"])}</strong><span>{escape(verb["ja"])}</span></div>'
            f'{"".join(tense_blocks)}'
            '</div>'
        )
    return "".join(html)


def render_content_admin(items=None, approved_cards=None, message="", error="", active_tab="review"):
    items = load_pending_content() if items is None else items
    approved_cards = load_approved_cards() if approved_cards is None else approved_cards
    message_html = f'<div class="notice ok">{escape(message)}</div>' if message else ""
    error_html = f'<div class="notice bad">{escape(error)}</div>' if error else ""
    tabs = "".join(
        [
            admin_tab_link("review", "Review", active_tab),
            admin_tab_link("vocab", "Vocab", active_tab),
            admin_tab_link("cloze", "Cloze", active_tab),
            admin_tab_link("tenses", "Tenses", active_tab),
        ]
    )
    if active_tab == "vocab":
        title = "Vocabulary cards"
        body_html = f'<div class="content-list">{render_vocab_cards(approved_cards)}</div>'
    elif active_tab == "cloze":
        title = "Cloze cards"
        body_html = f'<div class="content-list">{render_cloze_cards(approved_cards)}</div>'
    elif active_tab == "tenses":
        title = "Tense tables"
        body_html = render_tense_import_form() + f'<div class="tree-list">{render_verb_trees()}</div>'
    else:
        title = "Pending review"
        pending_html = (
            "".join(render_pending_item(item) for item in items)
            if items
            else '<div class="empty">No pending cards.</div>'
        )
        body_html = f'<div class="content-list">{pending_html}</div>'
    return f"""<!doctype html>
<html lang="ja">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>カード管理</title>
    <style>
      body {{
        font-family: Georgia, "Times New Roman", serif;
        background: #f5f0e6;
        color: #3d3630;
        margin: 0;
        padding: 32px;
      }}
      .panel {{
        max-width: 1180px;
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
        margin-bottom: 14px;
      }}
      h1, h2 {{
        margin: 0 0 14px;
      }}
      h1 {{
        font-size: 24px;
      }}
      h2 {{
        font-size: 18px;
        margin-top: 18px;
      }}
      a {{
        color: #8fa68e;
        font-weight: 600;
        text-decoration: none;
      }}
      .tabs {{
        display: flex;
        flex-wrap: wrap;
        gap: 8px;
        margin-bottom: 16px;
      }}
      .tabs a {{
        border: 1px solid #d8d0c4;
        border-radius: 8px;
        color: #6b635c;
        padding: 8px 12px;
      }}
      .tabs a.active {{
        background: #8fa68e;
        border-color: #8fa68e;
        color: #fff;
      }}
      .content-list, .tree-list {{
        display: grid;
        gap: 6px;
        max-height: 70vh;
        overflow-y: auto;
        padding-right: 4px;
      }}
      .content-item, .verb-tree-card {{
        background: #faf7f0;
        border: 1px solid #e8e0d4;
        border-radius: 10px;
        padding: 16px;
      }}
      .compact-card {{
        align-items: center;
        display: grid;
        gap: 6px;
        grid-template-columns: 150px minmax(0, 1fr) 32px 32px;
        padding: 7px 8px;
      }}
      .meta, .empty {{
        color: #7a7065;
        font-size: 13px;
        margin-bottom: 8px;
      }}
      .compact-meta {{
        color: #6b635c;
        font-size: 12px;
        min-width: 0;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }}
      .status-new {{
        background: #c4706a;
        border-radius: 999px;
        color: #fff;
        display: inline-block;
        font-size: 10px;
        margin-left: 4px;
        padding: 2px 5px;
      }}
      .compact-edit {{
        align-items: center;
        display: grid;
        gap: 6px;
        grid-template-columns: minmax(0, 1fr) 32px;
        margin: 0;
        min-width: 0;
      }}
      .compact-fields {{
        align-items: center;
        display: flex;
        gap: 5px;
        min-width: 0;
        overflow-x: auto;
      }}
      .compact-input {{
        flex: 1 1 130px;
        margin-top: 0;
        min-width: 72px;
        padding: 6px 7px;
      }}
      .compact-input.short {{
        flex-basis: 84px;
      }}
      .compact-input.medium {{
        flex-basis: 140px;
      }}
      .compact-input.wide {{
        flex-basis: 240px;
      }}
      input, select {{
        box-sizing: border-box;
        width: 100%;
        padding: 9px 10px;
        font-size: 14px;
        border: 1px solid #d8d0c4;
        border-radius: 8px;
        background: #fffef9;
      }}
      button {{
        background: #8fa68e;
        color: #fff;
        border: 0;
        border-radius: 8px;
        cursor: pointer;
        font-size: 14px;
        height: 32px;
        padding: 0;
        width: 32px;
      }}
      button.secondary {{
        background: #b8aa97;
      }}
      button.danger {{
        background: #c4706a;
      }}
      .actions-row {{
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
        justify-content: flex-end;
        margin-top: 12px;
      }}
      .actions-row form, .compact-action, .mini-action {{
        margin: 0;
      }}
      .tense-import {{
        align-items: center;
        display: grid;
        gap: 8px;
        grid-template-columns: minmax(130px, 1fr) minmax(130px, 1fr) 160px 32px;
        margin-bottom: 14px;
      }}
      .verb-tree-card {{
        padding: 12px;
      }}
      .verb-tree-head {{
        align-items: baseline;
        display: flex;
        gap: 12px;
        margin-bottom: 10px;
      }}
      .verb-tree-head strong {{
        font-size: 20px;
      }}
      .verb-tree-head span {{
        color: #6b635c;
      }}
      .tense-block {{
        border-top: 1px dashed #d8d0c4;
        padding-top: 8px;
      }}
      .tense-title {{
        color: #8fa68e;
        font-size: 13px;
        font-weight: 700;
        margin-bottom: 6px;
      }}
      .tense-title-row {{
        align-items: center;
        display: flex;
        justify-content: space-between;
        gap: 10px;
        margin-bottom: 6px;
      }}
      .tense-actions {{
        display: flex;
        gap: 6px;
      }}
      .conj-row {{
        align-items: center;
        display: grid;
        gap: 8px;
        grid-template-columns: 84px minmax(120px, 1fr) 120px;
        min-height: 30px;
      }}
      .pronoun-cell {{
        color: #6b635c;
        font-weight: 700;
      }}
      .form-cell {{
        font-size: 16px;
      }}
      .elo-cell {{
        color: #7a7065;
        font-size: 12px;
        text-align: right;
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
      @media (max-width: 760px) {{
        body {{
          padding: 20px;
        }}
        .top {{
          align-items: flex-start;
          flex-direction: column;
        }}
        .compact-card, .conj-row, .tense-import {{
          grid-template-columns: 1fr;
        }}
        .compact-meta {{
          grid-column: 1 / -1;
        }}
        .elo-cell {{
          text-align: left;
        }}
      }}
    </style>
  </head>
  <body>
    <main class="panel">
      <div class="top">
        <h1>カード管理</h1>
        <a href="/admin">管理へ戻る</a>
      </div>
      {message_html}
      {error_html}
      <nav class="tabs">{tabs}</nav>
      <h2>{escape(title)}</h2>
      {body_html}
    </main>
  </body>
</html>"""


def find_or_create_verb(conn, infinitive, ja):
    infinitive = infinitive.strip()
    ja = ja.strip()
    row = conn.execute(
        "SELECT id FROM verbs WHERE infinitive = ?",
        (infinitive,),
    ).fetchone()
    if row:
        if ja:
            conn.execute("UPDATE verbs SET ja = ? WHERE id = ?", (ja, row["id"]))
        return row["id"]
    cursor = conn.execute(
        "INSERT INTO verbs (infinitive, ja) VALUES (?, ?)",
        (infinitive, ja),
    )
    return cursor.lastrowid


def approve_pending_content(conn, row, username):
    payload = json.loads(row["payload_json"])
    content_type = row["content_type"]
    if content_type == "cloze":
        sentence = payload.get("sentence", "").strip()
        answer = payload.get("answer", "").strip()
        translation = payload.get("translation", "").strip()
        if not sentence or not answer or not translation:
            return False, "候補の内容が足りません。"
        uid = make_cloze_uid(sentence, answer)
        content_hash = cloze_content_hash(sentence, answer, translation)
        conn.execute(
            """
            INSERT OR IGNORE INTO cloze_questions
                (uid, sentence, answer, translation, content_hash, revision, elo, active, status, is_new)
            VALUES (?, ?, ?, ?, ?, 1, ?, 1, 'approved', 1)
            """,
            (uid, sentence, answer, translation, content_hash, DEFAULT_ELO),
        )
    elif content_type == "flashcard":
        infinitive = (payload.get("infinitive") or payload.get("word") or "").strip()
        ja = (payload.get("ja") or payload.get("translation") or payload.get("answer") or "").strip()
        if not infinitive or not ja:
            return False, "候補の内容が足りません。"
        verb_id = find_or_create_verb(conn, infinitive, ja)
        uid = make_question_uid("flashcard", infinitive)
        content_hash = question_content_hash("flashcard", infinitive, ja)
        conn.execute(
            """
            INSERT OR IGNORE INTO questions
                (uid, kind, verb_id, verb_form_id, prompt, answer, content_hash, revision, elo, active, status, is_new)
            VALUES (?, 'flashcard', ?, NULL, ?, ?, ?, 1, ?, 1, 'approved', 1)
            """,
            (uid, verb_id, infinitive, ja, content_hash, DEFAULT_ELO),
        )
    elif content_type == "verb_form":
        infinitive = (payload.get("infinitive") or payload.get("word") or "").strip()
        ja = (payload.get("ja") or payload.get("translation") or "").strip()
        tense = payload.get("tense", "").strip()
        pronoun = payload.get("pronoun", "").strip()
        gender = payload.get("gender", "").strip()
        answer = (payload.get("answer") or payload.get("value") or "").strip()
        if not infinitive or not ja or not tense or not pronoun or not answer:
            return False, "候補の内容が足りません。"
        verb_id = find_or_create_verb(conn, infinitive, ja)
        form_row = conn.execute(
            """
            SELECT id FROM verb_forms
            WHERE verb_id = ? AND tense = ? AND pronoun = ? AND gender = ?
            """,
            (verb_id, tense, pronoun, gender),
        ).fetchone()
        if form_row:
            form_id = form_row["id"]
            conn.execute(
                "UPDATE verb_forms SET value = ? WHERE id = ?",
                (answer, form_id),
            )
        else:
            cursor = conn.execute(
                """
                INSERT INTO verb_forms (verb_id, tense, pronoun, value, gender)
                VALUES (?, ?, ?, ?, ?)
                """,
                (verb_id, tense, pronoun, answer, gender),
            )
            form_id = cursor.lastrowid
        prompt = f"{infinitive}|{ja}|{tense}|{pronoun}|{gender}"
        uid = make_question_uid("verb_form", prompt)
        content_hash = question_content_hash("verb_form", prompt, answer)
        conn.execute(
            """
            INSERT OR IGNORE INTO questions
                (uid, kind, verb_id, verb_form_id, prompt, answer, content_hash, revision, elo, active, status, is_new)
            VALUES (?, 'verb_form', ?, ?, ?, ?, ?, 1, ?, 1, 'approved', 1)
            """,
            (uid, verb_id, form_id, prompt, answer, content_hash, DEFAULT_ELO),
        )
    else:
        return False, "未対応の種類です。"

    conn.execute(
        """
        UPDATE pending_content
        SET status = 'approved',
            reviewed_by = ?,
            reviewed_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (username, row["id"]),
    )
    return True, "承認しました。"


def update_approved_card(form):
    card_type = form.get("card_type", "")
    card_id = form.get("id", "")
    with get_db() as conn:
        if card_type == "cloze":
            sentence = form.get("sentence", "").strip()
            answer = form.get("answer", "").strip()
            translation = form.get("translation", "").strip()
            new_hash = cloze_content_hash(sentence, answer, translation)
            conn.execute(
                """
                UPDATE cloze_questions
                SET sentence = ?,
                    answer = ?,
                    translation = ?,
                    revision = CASE WHEN content_hash <> ? THEN revision + 1 ELSE revision END,
                    content_hash = ?
                WHERE id = ?
                """,
                (
                    sentence,
                    answer,
                    translation,
                    new_hash,
                    new_hash,
                    card_id,
                ),
            )
            return True

        row = conn.execute(
            """
            SELECT q.id, q.kind, q.verb_id, q.verb_form_id
            FROM questions q
            WHERE q.id = ?
            """,
            (card_id,),
        ).fetchone()
        if not row:
            return False
        infinitive = form.get("infinitive", "").strip()
        ja = form.get("ja", "").strip()
        conn.execute(
            "UPDATE verbs SET infinitive = ?, ja = ? WHERE id = ?",
            (infinitive, ja, row["verb_id"]),
        )
        if card_type == "flashcard":
            new_hash = question_content_hash("flashcard", infinitive, ja)
            conn.execute(
                """
                UPDATE questions
                SET prompt = ?,
                    answer = ?,
                    revision = CASE WHEN content_hash <> ? THEN revision + 1 ELSE revision END,
                    content_hash = ?
                WHERE id = ?
                """,
                (infinitive, ja, new_hash, new_hash, card_id),
            )
        elif card_type == "verb_form":
            tense = form.get("tense", "").strip()
            pronoun = form.get("pronoun", "").strip()
            gender = form.get("gender", "").strip()
            answer = form.get("answer", "").strip()
            conn.execute(
                """
                UPDATE verb_forms
                SET tense = ?, pronoun = ?, gender = ?, value = ?
                WHERE id = ?
                """,
                (tense, pronoun, gender, answer, row["verb_form_id"]),
            )
            prompt = f"{infinitive}|{ja}|{tense}|{pronoun}|{gender}"
            new_hash = question_content_hash("verb_form", prompt, answer)
            conn.execute(
                """
                UPDATE questions
                SET prompt = ?,
                    answer = ?,
                    revision = CASE WHEN content_hash <> ? THEN revision + 1 ELSE revision END,
                    content_hash = ?
                WHERE id = ?
                """,
                (prompt, answer, new_hash, new_hash, card_id),
            )
        else:
            return False
    return True


def delete_approved_card(form):
    card_type = form.get("card_type", "")
    card_id = form.get("id", "")
    with get_db() as conn:
        if card_type == "cloze":
            conn.execute(
                "UPDATE cloze_questions SET active = 0 WHERE id = ?",
                (card_id,),
            )
        elif card_type in ("flashcard", "verb_form"):
            conn.execute(
                "UPDATE questions SET active = 0 WHERE id = ?",
                (card_id,),
            )
        elif card_type == "verb_tense":
            conn.execute(
                """
                UPDATE questions
                SET active = 0
                WHERE id IN (
                    SELECT q.id
                    FROM questions q
                    JOIN verb_forms vf ON vf.id = q.verb_form_id
                    WHERE q.kind = 'verb_form'
                        AND q.verb_id = ?
                        AND vf.tense = ?
                        AND q.status = 'approved'
                )
                """,
                (form.get("verb_id", ""), form.get("tense", "")),
            )
        else:
            return False
    return True


def reset_approved_card_elo(form):
    card_type = form.get("card_type", "")
    card_id = form.get("id", "")
    with get_db() as conn:
        if card_type == "cloze":
            conn.execute(
                """
                UPDATE cloze_questions
                SET elo = ?, is_new = 1
                WHERE id = ? AND status = 'approved'
                """,
                (DEFAULT_ELO, card_id),
            )
        elif card_type in ("flashcard", "verb_form"):
            conn.execute(
                """
                UPDATE questions
                SET elo = ?, is_new = 1
                WHERE id = ? AND status = 'approved'
                """,
                (DEFAULT_ELO, card_id),
            )
        elif card_type == "verb_tense":
            conn.execute(
                """
                UPDATE questions
                SET elo = ?, is_new = 1
                WHERE id IN (
                    SELECT q.id
                    FROM questions q
                    JOIN verb_forms vf ON vf.id = q.verb_form_id
                    WHERE q.kind = 'verb_form'
                        AND q.verb_id = ?
                        AND vf.tense = ?
                        AND q.status = 'approved'
                )
                """,
                (DEFAULT_ELO, form.get("verb_id", ""), form.get("tense", "")),
            )
        else:
            return False
    return True


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


def record_user_card_seen(conn, username, card_uid, card_type, revision, correct):
    conn.execute(
        """
        INSERT INTO user_card_state
            (user_name, card_uid, card_type, seen_count, correct_count, card_revision)
        VALUES (?, ?, ?, 1, ?, ?)
        ON CONFLICT(user_name, card_uid) DO UPDATE SET
            last_seen = CURRENT_TIMESTAMP,
            seen_count = seen_count + 1,
            correct_count = correct_count + excluded.correct_count,
            card_revision = excluded.card_revision
        """,
        (username, card_uid, card_type, 1 if correct else 0, revision),
    )


def update_elo(username, question_id, correct, game):
    init_db()
    init_db(DB_PATH)
    with get_runtime_db() as runtime_conn:
        user_row = runtime_conn.execute("SELECT elo FROM users WHERE name = ?", (username,)).fetchone()
    with get_db() as conn:
        question_row = conn.execute(
            "SELECT elo, uid, revision FROM questions WHERE id = ?", (question_id,)
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

    with get_db() as conn:
        conn.execute(
            "UPDATE questions SET elo = ? WHERE id = ?",
            (question_after, question_id),
        )
    with get_runtime_db() as runtime_conn:
        runtime_conn.execute(
            "UPDATE users SET elo = ? WHERE name = ?", (user_after, username)
        )
        record_user_card_seen(
            runtime_conn,
            username,
            question_row["uid"],
            game,
            int(question_row["revision"]),
            bool(correct),
        )
        runtime_conn.execute(
            """
            INSERT INTO practice_events
                (
                    user_name,
                    question_id,
                    question_uid,
                    question_revision,
                    game,
                    correct,
                    user_elo_before,
                    user_elo_after,
                    question_elo_before,
                    question_elo_after
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                username,
                question_id,
                question_row["uid"],
                int(question_row["revision"]),
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
    init_db(DB_PATH)
    with get_runtime_db() as runtime_conn:
        user_row = runtime_conn.execute("SELECT elo FROM users WHERE name = ?", (username,)).fetchone()
    with get_db() as conn:
        question_row = conn.execute(
            "SELECT elo, uid, revision FROM cloze_questions WHERE id = ?", (question_id,)
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

    with get_db() as conn:
        conn.execute(
            "UPDATE cloze_questions SET elo = ? WHERE id = ?",
            (question_after, question_id),
        )
    with get_runtime_db() as runtime_conn:
        runtime_conn.execute(
            "UPDATE users SET elo = ? WHERE name = ?", (user_after, username)
        )
        record_user_card_seen(
            runtime_conn,
            username,
            question_row["uid"],
            "cloze",
            int(question_row["revision"]),
            bool(correct),
        )
        runtime_conn.execute(
            """
            INSERT INTO cloze_practice_events
                (
                    user_name,
                    cloze_question_id,
                    cloze_question_uid,
                    cloze_question_revision,
                    correct,
                    user_elo_before,
                    user_elo_after,
                    question_elo_before,
                    question_elo_after
                )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                username,
                question_id,
                question_row["uid"],
                int(question_row["revision"]),
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


def user_seen_card_uids(username, card_type):
    init_db(DB_PATH)
    with get_runtime_db() as conn:
        return {
            row["card_uid"]
            for row in conn.execute(
                """
                SELECT card_uid
                FROM user_card_state
                WHERE user_name = ? AND card_type = ?
                """,
                (username, card_type),
            ).fetchall()
        }


def choose_user_card_subset(rows, conn, user, card_type, force_new):
    rows = list(rows)
    if not rows:
        return rows
    seen = user_seen_card_uids(user.get("name", ""), card_type)
    if force_new:
        unseen_rows = [row for row in rows if row["uid"] not in seen]
        if unseen_rows:
            return unseen_rows
    seen_rows = [row for row in rows if row["uid"] in seen]
    return seen_rows or rows


def exclude_card_uids(rows, excluded_uids):
    if not excluded_uids:
        return list(rows)
    return [row for row in rows if row["uid"] not in excluded_uids]


def weighted_question_row(user, kind, excluded_uids=None):
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
                    """,
                    (user["name"],),
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
                    """
                ).fetchall()
            rows = exclude_card_uids(rows, excluded_uids)
            rows = choose_user_card_subset(rows, conn, user, "flashcard", force_new)
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
                """
            ).fetchall()
            rows = exclude_card_uids(rows, excluded_uids)
            rows = choose_user_card_subset(rows, conn, user, "verb_form", force_new)

    return weighted_row_by_elo(rows, user_elo)


def pick_cloze_question(user, excluded_uids=None):
    init_db()
    force_new = (
        random.random() < NEW_CONTENT_CHANCE
        and not user.get("_skip_new")
    )
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT id, uid, revision, sentence, answer, translation, elo, is_new
            FROM cloze_questions
            WHERE active = 1
                AND status = 'approved'
            """,
        ).fetchall()
        rows = exclude_card_uids(rows, excluded_uids)
        rows = choose_user_card_subset(rows, conn, user, "cloze", force_new)
    row = weighted_row_by_elo(rows, int(user.get("elo", DEFAULT_ELO)))
    if not row:
        return None
    return {
        "question_id": row["id"],
        "card_uid": row["uid"],
        "card_revision": int(row["revision"]),
        "sentence": row["sentence"],
        "answer": row["answer"],
        "translation": row["translation"],
        "question_elo": row["elo"],
        "is_new": bool(row["is_new"]),
    }


def pick_question(user=None, excluded_uids=None, allow_fallback=True):
    row = weighted_question_row(
        user or {"name": "", "elo": DEFAULT_ELO},
        "verb_form",
        excluded_uids=excluded_uids,
    )
    if row:
        return {
            "question_id": row["id"],
            "card_uid": row["uid"],
            "card_revision": int(row["revision"]),
            "question_elo": row["elo"],
            "is_new": bool(row["is_new"]),
            "infinitive": row["infinitive"],
            "ja": row["ja"],
            "tense": row["tense"],
            "pronoun": row["pronoun"],
            "answer": row["answer"],
            "gender": row["gender"],
        }
    if not allow_fallback:
        return None
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


def pick_flashcard(user, excluded_uids=None, allow_fallback=True):
    row = weighted_question_row(user, "flashcard", excluded_uids=excluded_uids)
    if row:
        card = {
            "question_id": row["id"],
            "card_uid": row["uid"],
            "card_revision": int(row["revision"]),
            "question_elo": row["elo"],
            "is_new": bool(row["is_new"]),
            "word": row["infinitive"],
            "translation": row["answer"],
        }
    else:
        if not allow_fallback:
            return None, []
        cards = user_flashcard_pool(user)
        if not cards:
            return None, []
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
    init_db(DB_PATH)
    with get_runtime_db() as conn:
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


def today_key():
    return datetime.now(APP_TIMEZONE).date().isoformat()


def distribute_daily_counts(total):
    verb_count = max(1, round(total * 0.25)) if total > 1 else total
    cloze_count = max(0, total - verb_count)
    return {
        "verb_form": verb_count,
        "flashcard": 0,
        "cloze": cloze_count,
    }


def remember_daily_card(used_uids, item):
    uid = item.get("card_uid")
    if uid:
        used_uids.add(uid)


def build_daily_state(user, target=None):
    total = max(1, min(100, int(target or user.get("daily_target", DEFAULT_DAILY_TARGET))))
    if STUDY_LANGUAGES[study_language(user)].get("verb_enabled"):
        counts = distribute_daily_counts(total)
    else:
        counts = {"verb_form": 0, "flashcard": 0, "cloze": total}
    items = []
    used_uids = set()

    for _ in range(counts["verb_form"]):
        question = pick_question(user, excluded_uids=used_uids, allow_fallback=False)
        if not question:
            continue
        item = {
            "game": "verb_form",
            "question_id": question.get("question_id", ""),
            "card_uid": question.get("card_uid", ""),
            "card_revision": int(question.get("card_revision", 1)),
            "question_elo": int(question.get("question_elo", DEFAULT_ELO)),
            "is_new": bool(question.get("is_new")),
            "infinitive": question["infinitive"],
            "ja": question["ja"],
            "tense": question["tense"],
            "pronoun": question["pronoun"],
            "gender": question.get("gender", ""),
            "answer": question["answer"],
        }
        remember_daily_card(used_uids, item)
        items.append(
            item
        )

    for _ in range(counts["flashcard"]):
        card, options = pick_flashcard(user, excluded_uids=used_uids, allow_fallback=False)
        if not card:
            continue
        item = {
            "game": "flashcard",
            "question_id": card.get("question_id", ""),
            "card_uid": card.get("card_uid", ""),
            "card_revision": int(card.get("card_revision", 1)),
            "question_elo": int(card.get("question_elo", DEFAULT_ELO)),
            "is_new": bool(card.get("is_new")),
            "word": card["word"],
            "translation": card["translation"],
            "options": options,
        }
        remember_daily_card(used_uids, item)
        items.append(
            item
        )

    for _ in range(counts["cloze"]):
        question = pick_cloze_question(user, excluded_uids=used_uids)
        if not question:
            continue
        item = {
            "game": "cloze",
            "question_id": question.get("question_id", ""),
            "card_uid": question.get("card_uid", ""),
            "card_revision": int(question.get("card_revision", 1)),
            "question_elo": int(question.get("question_elo", DEFAULT_ELO)),
            "is_new": bool(question.get("is_new")),
            "sentence": question["sentence"],
            "answer": question["answer"],
            "translation": question["translation"],
        }
        remember_daily_card(used_uids, item)
        items.append(
            item
        )

    random.shuffle(items)
    return {
        "date": today_key(),
        "index": 0,
        "total": len(items),
        "items": items,
        "history": [],
    }


def decode_daily_state(value):
    try:
        state = json.loads(base64.urlsafe_b64decode(value.encode("ascii")).decode("utf-8"))
        if not isinstance(state.get("items"), list):
            raise ValueError
        state["date"] = state.get("date", "")
        state["index"] = int(state.get("index", 0))
        state["total"] = int(state.get("total", len(state["items"])))
        state["history"] = list(state.get("history", []))
        return state
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def complete_daily(username):
    today = today_key()
    yesterday = (datetime.now(APP_TIMEZONE).date() - timedelta(days=1)).isoformat()
    init_db(DB_PATH)
    with get_runtime_db() as conn:
        row = conn.execute(
            """
            SELECT daily_streak, daily_last_completed, daily_vacation_mode
            FROM users
            WHERE name = ?
            """,
            (username,),
        ).fetchone()
        if not row:
            return None

        previous = row["daily_last_completed"] or ""
        streak = int(row["daily_streak"])
        vacation = bool(row["daily_vacation_mode"])
        if previous == today:
            new_streak = streak
        elif previous == yesterday or vacation:
            new_streak = streak + 1
        else:
            new_streak = 1

        conn.execute(
            """
            UPDATE users
            SET daily_streak = ?,
                daily_last_completed = ?
            WHERE name = ?
            """,
            (new_streak, today, username),
        )
    return new_streak


def daily_completed_today(user):
    return user.get("daily_last_completed") == today_key()


def load_saved_daily_state(username):
    init_db(DB_PATH)
    with get_runtime_db() as conn:
        row = conn.execute(
            "SELECT daily_state_json FROM users WHERE name = ?",
            (username,),
        ).fetchone()
    if not row or not row["daily_state_json"]:
        return None
    state = decode_daily_state(
        base64.urlsafe_b64encode(row["daily_state_json"].encode("utf-8")).decode("ascii")
    )
    if not state or state.get("date") != today_key():
        clear_saved_daily_state(username)
        return None
    if int(state.get("index", 0)) >= int(state.get("total", 0)):
        clear_saved_daily_state(username)
        return None
    return state


def save_daily_state(username, state):
    init_db(DB_PATH)
    with get_runtime_db() as conn:
        conn.execute(
            """
            UPDATE users
            SET daily_state_json = ?
            WHERE name = ?
            """,
            (json.dumps(state, ensure_ascii=False), username),
        )


def clear_saved_daily_state(username):
    init_db(DB_PATH)
    with get_runtime_db() as conn:
        conn.execute(
            "UPDATE users SET daily_state_json = '' WHERE name = ?",
            (username,),
        )


def daily_progress(username, user):
    if daily_completed_today(user):
        return {"status": "completed", "done": int(user.get("daily_target", DEFAULT_DAILY_TARGET)), "total": int(user.get("daily_target", DEFAULT_DAILY_TARGET))}
    state = load_saved_daily_state(username)
    if state:
        return {
            "status": "in_progress",
            "done": int(state.get("index", 0)),
            "total": int(state.get("total", 0)),
        }
    return {
        "status": "not_started",
        "done": 0,
        "total": int(user.get("daily_target", DEFAULT_DAILY_TARGET)),
    }


def update_daily_settings(username, target, vacation_mode, language=None):
    try:
        target_value = int(target)
    except (TypeError, ValueError):
        target_value = DEFAULT_DAILY_TARGET
    target_value = max(3, min(100, target_value))
    language_value = language if language in STUDY_LANGUAGES else None
    init_db(DB_PATH)
    with get_runtime_db() as conn:
        if language_value:
            conn.execute(
                """
                UPDATE users
                SET daily_target = ?,
                    daily_vacation_mode = ?,
                    study_language = ?,
                    daily_state_json = ''
                WHERE name = ?
                """,
                (target_value, 1 if vacation_mode else 0, language_value, username),
            )
            return
        conn.execute(
            """
            UPDATE users
            SET daily_target = ?,
                daily_vacation_mode = ?
            WHERE name = ?
            """,
            (target_value, 1 if vacation_mode else 0, username),
        )


def render_nav(username, user, active=""):
    admin_link = (
        '<a href="/admin">管理</a>' if user.get("is_admin") else ""
    )
    links = [
        ('href="/"', "メニュー"),
        ('href="/verbs"', "動詞練習"),
        ('href="/flashcards"', "単語カード"),
        ('href="/cloze"', "穴埋め"),
        ('href="/settings"', "設定"),
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


def render_nav(username, user, active=""):
    admin_link = '<a href="/admin">管理</a>' if user.get("is_admin") else ""
    links = [
        ('href="/"', "メニュー"),
        ('href="/daily"', "今日の練習"),
        ('href="/flashcards"', "単語カード"),
        ('href="/cloze"', "穴埋め"),
        ('href="/settings"', "設定"),
    ]
    if STUDY_LANGUAGES[study_language(user)].get("verb_enabled"):
        links.insert(2, ('href="/verbs"', "動詞練習"))
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


def render_daily(username, user, state, result=None, finished=False, streak=None):
    nav_html = render_nav(username, user, "今日の練習")
    total = max(1, int(state.get("total", 0) or 1))
    index = min(int(state.get("index", 0)), total)
    progress = f"{index + 1 if not finished else total}/{total}"

    result_html = ""
    if result:
        css_class = "ok" if result["ok"] else "bad"
        text = "正解です。" if result["ok"] else "不正解です。"
        result_html = (
            f'<div class="result {css_class}">{text} '
            f'答え: {escape(result["answer"])}</div>'
        )

    if finished:
        streak_value = streak if streak is not None else user.get("daily_streak", 0)
        card_html = f"""
          <div class="complete">
            <h1>今日の練習完了</h1>
            <p>次の日まで待ってください。</p>
            <p>連続記録: {int(streak_value)}日</p>
            <a class="next" href="/">メニューへ</a>
          </div>
        """
    else:
        item = state["items"][index]
        new_badge = '<span class="new-badge">NEW</span>' if item.get("is_new") else ""
        hidden_state = escape(encode_state(state))
        game = item["game"]
        game_label = {
            "verb_form": "動詞練習",
            "flashcard": "単語カード",
            "cloze": "穴埋め",
        }.get(game, "練習")
        elo_line = (
            f'<div class="meta">あなたのELO: {int(user.get("elo", DEFAULT_ELO))} / '
            f'問題ELO: {int(item.get("question_elo", DEFAULT_ELO))}</div>'
        )

        if game == "verb_form":
            tense_label = escape(build_tense_label(item["tense"]))
            gender_label = escape(build_gender_label(item.get("gender", "")))
            gender_html = f'<div class="meta">{gender_label}</div>' if gender_label else ""
            card_html = f"""
              <div class="kicker">{game_label}</div>
              <div class="word">{escape(item["infinitive"])} {escape(item["ja"])} {new_badge}</div>
              <div class="meta">{tense_label}</div>
              {gender_html}
              {elo_line}
              <form method="post" action="/daily" class="answer-form">
                <span class="pronoun-inline">{escape(item["pronoun"])}</span>
                <input name="answer" type="text" autocomplete="off" autofocus />
                <button type="submit">確認</button>
                <input type="hidden" name="state" value="{hidden_state}" />
              </form>
            """
        elif game == "flashcard":
            option_buttons = "".join(
                f'<button type="submit" name="answer" value="{escape(option)}">{escape(option)}</button>'
                for option in item.get("options", [])
            )
            card_html = f"""
              <div class="kicker">{game_label}</div>
              <div class="prompt">この単語の意味は？</div>
              <div class="word">{escape(item["word"])} {new_badge}</div>
              {elo_line}
              <form method="post" action="/daily" class="options">
                <input type="hidden" name="state" value="{hidden_state}" />
                {option_buttons}
              </form>
            """
        else:
            card_html = f"""
              <div class="kicker">{game_label}</div>
              <div class="sentence">{escape(item["sentence"])} {new_badge}</div>
              <div class="translation">{escape(item["translation"])}</div>
              {elo_line}
              <form method="post" action="/daily" class="answer-form">
                <input name="answer" type="text" autocomplete="off" autofocus />
                <button type="submit">確認</button>
                <input type="hidden" name="state" value="{hidden_state}" />
              </form>
            """

    return f"""<!doctype html>
<html lang="ja">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>今日の練習</title>
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
      .nav a, .logout, .next {{
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
      .progress, .kicker, .prompt, .meta, .translation {{
        color: #6b635c;
        font-size: 14px;
        margin-bottom: 10px;
      }}
      .kicker {{
        color: #8fa68e;
        font-weight: 700;
      }}
      .word, .sentence {{
        font-size: 34px;
        font-weight: 600;
        line-height: 1.3;
        margin-bottom: 12px;
      }}
      .sentence {{
        font-size: 28px;
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
      .answer-form {{
        display: flex;
        align-items: center;
        gap: 10px;
        margin-top: 18px;
      }}
      .pronoun-inline {{
        font-size: 18px;
        font-weight: 600;
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
      button, .next {{
        background: #8fa68e;
        color: #fff;
        border: 0;
        border-radius: 10px;
        cursor: pointer;
        display: inline-block;
        font-size: 16px;
        padding: 12px 18px;
        text-align: center;
      }}
      .options {{
        display: grid;
        gap: 10px;
        margin-top: 18px;
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
      .complete h1 {{
        margin-top: 0;
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
        .word, .sentence {{
          font-size: 26px;
        }}
      }}
    </style>
  </head>
  <body>
    <main class="wrap">
      {nav_html}
      <section class="card">
        <div class="progress">{progress}</div>
        {result_html}
        {card_html}
      </section>
    </main>
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


def render_menu(username, user):
    nav_html = render_nav(username, user, "メニュー")
    daily_target = int(user.get("daily_target", DEFAULT_DAILY_TARGET))
    daily_streak = int(user.get("daily_streak", 0))
    vacation_checked = "checked" if user.get("daily_vacation_mode") else ""
    vacation_text = "有効" if user.get("daily_vacation_mode") else "無効"
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
      .daily-panel, .game {{
        background: #fffef9;
        border: 1px solid #e8e0d4;
        border-radius: 12px;
        box-shadow: 0 12px 32px rgba(139, 125, 107, 0.12);
        color: inherit;
        padding: 22px;
      }}
      .daily-panel {{
        margin-bottom: 16px;
      }}
      .daily-header {{
        display: flex;
        justify-content: space-between;
        gap: 16px;
        align-items: center;
        margin-bottom: 14px;
      }}
      .daily-header h2, .game h2 {{
        margin: 0 0 8px;
        font-size: 20px;
      }}
      .daily-stats, .game p {{
        color: #6b635c;
        font-size: 14px;
        line-height: 1.5;
        margin: 0;
      }}
      .daily-actions {{
        display: grid;
        grid-template-columns: 1fr auto;
        gap: 12px;
        align-items: end;
      }}
      .settings {{
        display: flex;
        flex-wrap: wrap;
        gap: 12px;
        align-items: center;
      }}
      .settings label {{
        color: #6b635c;
        font-size: 13px;
      }}
      .settings input[type="number"] {{
        width: 72px;
        padding: 8px 10px;
        border: 1px solid #d8d0c4;
        border-radius: 8px;
        background: #fffef9;
      }}
      .settings button, .start-daily {{
        background: #8fa68e;
        border: 0;
        border-radius: 10px;
        color: #fff;
        cursor: pointer;
        font-size: 15px;
        font-weight: 600;
        padding: 11px 16px;
        text-decoration: none;
      }}
      .games {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
        gap: 16px;
      }}
      .game {{
        display: block;
        text-decoration: none;
      }}
      @media (max-width: 640px) {{
        body {{
          padding: 20px;
        }}
        .topline, .daily-header {{
          align-items: flex-start;
          flex-direction: column;
        }}
        .daily-actions {{
          grid-template-columns: 1fr;
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
      <section class="daily-panel">
        <div class="daily-header">
          <div>
            <h2>今日の練習</h2>
            <p class="daily-stats">連続記録: {daily_streak}日 · {daily_target}問 · 休暇モード: {vacation_text}</p>
          </div>
          <a class="start-daily" href="/daily">開始</a>
        </div>
        <form method="post" action="/daily/settings" class="settings">
          <label>
            問題数
            <input type="number" name="daily_target" min="3" max="100" value="{daily_target}" />
          </label>
          <label>
            学習する言語
            <select name="study_language">{language_options}</select>
          </label>
          <label>
            学習する言語
            <select name="study_language">{language_options}</select>
          </label>
          <label>
            <select name="study_language">{language_options}</select>
          </label>
          <label>
            <input type="checkbox" name="daily_vacation_mode" value="1" {vacation_checked} />
            休暇モード
          </label>
          <button type="submit">保存</button>
        </form>
      </section>
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


def render_menu(username, user):
    nav_html = render_nav(username, user, "メニュー")
    progress = daily_progress(username, user)
    daily_streak = int(user.get("daily_streak", 0))
    daily_target = int(user.get("daily_target", DEFAULT_DAILY_TARGET))
    language_info = STUDY_LANGUAGES[study_language(user)]
    verb_card = (
        f'''<a class="game" href="/verbs">
          <h2>動詞練習</h2>
          <p>{escape(language_info["short"])}の動詞活用を入力して練習します。</p>
        </a>'''
        if language_info.get("verb_enabled")
        else ""
    )

    if progress["status"] == "completed":
        daily_text = "今日の練習は完了しました。次の日まで待ってください。"
        daily_action = '<span class="start-daily disabled">完了</span>'
    elif progress["status"] == "in_progress":
        daily_text = f'途中です: {progress["done"]}/{progress["total"]}問完了'
        daily_action = '<a class="start-daily" href="/daily">続ける</a>'
    else:
        daily_text = f'今日の練習を始めましょう: {daily_target}問'
        daily_action = '<a class="start-daily" href="/daily">開始</a>'

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
      .daily-panel, .game {{
        background: #fffef9;
        border: 1px solid #e8e0d4;
        border-radius: 12px;
        box-shadow: 0 12px 32px rgba(139, 125, 107, 0.12);
        color: inherit;
        padding: 22px;
      }}
      .daily-panel {{
        display: flex;
        justify-content: space-between;
        gap: 16px;
        align-items: center;
        margin-bottom: 16px;
      }}
      .daily-panel h2, .game h2 {{
        margin: 0 0 8px;
        font-size: 20px;
      }}
      .daily-stats, .game p {{
        color: #6b635c;
        font-size: 14px;
        line-height: 1.5;
        margin: 0;
      }}
      .start-daily {{
        background: #8fa68e;
        border-radius: 10px;
        color: #fff;
        display: inline-block;
        font-size: 15px;
        font-weight: 600;
        padding: 11px 16px;
        text-decoration: none;
        white-space: nowrap;
      }}
      .start-daily.disabled {{
        background: #b8b0a5;
      }}
      .games {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
        gap: 16px;
      }}
      .game {{
        display: block;
        text-decoration: none;
      }}
      @media (max-width: 640px) {{
        body {{
          padding: 20px;
        }}
        .topline, .daily-panel {{
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
      <section class="daily-panel">
        <div>
          <h2>今日の練習</h2>
          <p class="daily-stats">{daily_text}</p>
          <p class="daily-stats">連続記録: {daily_streak}日</p>
        </div>
        {daily_action}
      </section>
      <section class="games">
        {verb_card}
        <a class="game" href="/flashcards">
          <h2>単語カード</h2>
          <p>{escape(language_info["flashcard_description"])}</p>
        </a>
        <a class="game" href="/cloze">
          <h2>穴埋め</h2>
          <p>{escape(language_info["cloze_description"])}</p>
        </a>
      </section>
    </main>
  </body>
</html>"""


def render_settings(username, user):
    nav_html = render_nav(username, user, "設定")
    daily_target = int(user.get("daily_target", DEFAULT_DAILY_TARGET))
    vacation_checked = "checked" if user.get("daily_vacation_mode") else ""
    current_language = study_language(user)
    language_options = "".join(
        f'<option value="{escape(key)}" {"selected" if key == current_language else ""}>{escape(info["label"])}</option>'
        for key, info in STUDY_LANGUAGES.items()
    )
    return f"""<!doctype html>
<html lang="ja">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>設定</title>
    <style>
      body {{
        font-family: Georgia, "Times New Roman", serif;
        background: #f5f0e6;
        color: #3d3630;
        margin: 0;
        padding: 32px;
      }}
      .wrap {{
        max-width: 720px;
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
        padding: 24px;
      }}
      h1 {{
        margin: 0 0 18px;
        font-size: 28px;
      }}
      label {{
        display: block;
        color: #6b635c;
        font-size: 14px;
        margin: 0 0 14px;
      }}
      input[type="number"], select {{
        display: block;
        margin-top: 6px;
        width: min(280px, 100%);
        padding: 10px 12px;
        border: 1px solid #d8d0c4;
        border-radius: 8px;
        background: #fffef9;
        font-size: 16px;
      }}
      button {{
        background: #8fa68e;
        border: 0;
        border-radius: 10px;
        color: #fff;
        cursor: pointer;
        font-size: 15px;
        font-weight: 600;
        padding: 11px 16px;
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
      <section class="card">
        <h1>設定</h1>
        <form method="post" action="/settings">
          <label>
            今日の練習の問題数
            <input type="number" name="daily_target" min="3" max="100" value="{daily_target}" />
          </label>
          <label>
            学習する言語
            <select name="study_language">{language_options}</select>
          </label>
          <label>
            <input type="checkbox" name="daily_vacation_mode" value="1" {vacation_checked} />
            休暇モード
          </label>
          <button type="submit">保存</button>
        </form>
      </section>
    </main>
  </body>
</html>"""


def load_content_sources():
    init_db()
    with get_db() as conn:
        rows = conn.execute(
            """
            SELECT name, url, license_name, license_url, attribution
            FROM content_sources
            ORDER BY name
            """
        ).fetchall()
    return [dict(row) for row in rows]


def render_settings(username, user):
    nav_html = render_nav(username, user, "設定")
    daily_target = int(user.get("daily_target", DEFAULT_DAILY_TARGET))
    vacation_checked = "checked" if user.get("daily_vacation_mode") else ""
    current_language = study_language(user)
    language_options = "".join(
        f'<option value="{escape(key)}" {"selected" if key == current_language else ""}>{escape(info["label"])}</option>'
        for key, info in STUDY_LANGUAGES.items()
    )
    return f"""<!doctype html>
<html lang="ja">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>設定</title>
    <style>
      body {{
        font-family: Georgia, "Times New Roman", serif;
        background: #f5f0e6;
        color: #3d3630;
        margin: 0;
        padding: 32px;
      }}
      .wrap {{
        max-width: 720px;
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
      .nav a, .logout, .plain-link {{
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
        padding: 24px;
      }}
      h1 {{
        margin: 0 0 18px;
        font-size: 28px;
      }}
      label {{
        display: block;
        color: #6b635c;
        font-size: 14px;
        margin: 0 0 14px;
      }}
      input[type="number"] {{
        display: block;
        margin-top: 6px;
        width: 96px;
        padding: 10px 12px;
        border: 1px solid #d8d0c4;
        border-radius: 8px;
        background: #fffef9;
        font-size: 16px;
      }}
      button {{
        background: #8fa68e;
        border: 0;
        border-radius: 10px;
        color: #fff;
        cursor: pointer;
        font-size: 15px;
        font-weight: 600;
        padding: 11px 16px;
      }}
      .setting-links {{
        border-top: 1px dashed #dcd4c8;
        margin-top: 18px;
        padding-top: 16px;
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
      <section class="card">
        <h1>設定</h1>
        <form method="post" action="/settings">
          <label>
            今日の練習の問題数
            <input type="number" name="daily_target" min="3" max="100" value="{daily_target}" />
          </label>
          <label>
            学習する言語
            <select name="study_language">{language_options}</select>
          </label>
          <label>
            <input type="checkbox" name="daily_vacation_mode" value="1" {vacation_checked} />
            休暇モード
          </label>
          <button type="submit">保存</button>
        </form>
        <div class="setting-links">
          <a class="plain-link" href="/licenses">データとライセンス</a>
        </div>
      </section>
    </main>
  </body>
</html>"""


def render_licenses(username, user):
    nav_html = render_nav(username, user, "設定")
    source_items = []
    for source in load_content_sources():
        source_items.append(
            '<div class="source-item">'
            f'<h2>{escape(source["name"])}</h2>'
            f'<p>{escape(source["attribution"])}</p>'
            f'<p><a href="{escape(source["url"])}">{escape(source["url"])}</a></p>'
            f'<p>License: <a href="{escape(source["license_url"])}">{escape(source["license_name"])}</a></p>'
            '</div>'
        )
    sources_html = "".join(source_items) or '<p class="muted">No external data sources registered.</p>'
    return f"""<!doctype html>
<html lang="ja">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>データとライセンス</title>
    <style>
      body {{
        font-family: Georgia, "Times New Roman", serif;
        background: #f5f0e6;
        color: #3d3630;
        margin: 0;
        padding: 32px;
      }}
      .wrap {{
        max-width: 820px;
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
      .nav a, .logout, a {{
        color: #8fa68e;
        font-weight: 600;
        text-decoration: none;
      }}
      .nav a {{
        font-size: 13px;
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
        padding: 24px;
      }}
      h1 {{
        margin: 0 0 18px;
        font-size: 28px;
      }}
      h2 {{
        font-size: 18px;
        margin: 0 0 8px;
      }}
      p {{
        color: #6b635c;
        line-height: 1.5;
        margin: 6px 0;
      }}
      .source-item {{
        border-top: 1px dashed #dcd4c8;
        padding: 16px 0;
      }}
      .source-item:first-of-type {{
        border-top: 0;
        padding-top: 0;
      }}
      .muted {{
        color: #7a7065;
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
      <section class="card">
        <h1>データとライセンス</h1>
        {sources_html}
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


SCRAPER_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.7,en;q=0.6",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Upgrade-Insecure-Requests": "1",
}


def browser_like_headers(url, referer=""):
    headers = dict(SCRAPER_BROWSER_HEADERS)
    if referer:
        headers["Referer"] = referer
    return headers


def fetch_url_text(url, opener=None, referer=""):
    opener = opener or build_opener(HTTPCookieProcessor(CookieJar()))
    request = Request(
        url,
        headers=browser_like_headers(url, referer=referer),
    )
    with opener.open(request, timeout=SCRAPER_TIMEOUT_SECONDS) as response:
        content_type = response.headers.get_content_charset() or "utf-8"
        raw = response.read(1_500_000)
    return raw.decode(content_type, errors="replace")


def site_root(url):
    match = re.match(r"^(https?://[^/]+)/?", url)
    return match.group(1) + "/" if match else url


def html_to_text(raw):
    cleaned = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", raw)
    cleaned = re.sub(r"(?s)<!--.*?-->", " ", cleaned)
    cleaned = re.sub(r"(?s)<[^>]+>", " ", cleaned)
    cleaned = unescape(cleaned)
    return re.sub(r"\s+", " ", cleaned).strip()


def extract_links(raw, base_url):
    links = []
    for match in re.finditer(r"(?is)<link>\s*(.*?)\s*</link>", raw):
        links.append(urljoin(base_url, unescape(match.group(1).strip())))
    for match in re.finditer(r'''(?is)<a\s+[^>]*href=["']([^"']+)["']''', raw):
        links.append(urljoin(base_url, unescape(match.group(1).strip())))
    deduped = []
    seen = set()
    for link in links:
        if not link.startswith(("http://", "https://")) or link in seen:
            continue
        seen.add(link)
        deduped.append(link)
    return deduped[:SCRAPER_MAX_SOURCE_LINKS]


def sentence_candidates(text, min_chars=0, max_chars=320):
    # Intentionally simple first pass: keep spans between full stops.
    return [
        part.strip()
        for part in text.split(".")
        if part.strip() and min_chars <= len(part.strip()) <= max_chars
    ]


def content_sentence_items(raw, url, min_chars=0, max_chars=320):
    stripped = raw.lstrip()
    if is_tatoeba_api_url(url) and stripped.startswith("{"):
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError:
            return [
                {"sentence": sentence, "translation": ""}
                for sentence in sentence_candidates(html_to_text(raw), min_chars=min_chars, max_chars=max_chars)
            ]
        items = []
        for row in data.get("data", []):
            text = str(row.get("text", "")).strip()
            if min_chars <= len(text) <= max_chars:
                translations = []
                raw_translations = row.get("translations", [])
                if raw_translations and isinstance(raw_translations[0], list):
                    translation_groups = raw_translations
                else:
                    translation_groups = [raw_translations]
                for group in translation_groups:
                    for translation in group or []:
                        if translation.get("lang") == "jpn" and translation.get("text"):
                            translations.append(str(translation["text"]).strip())
                items.append(
                    {
                        "sentence": text.rstrip("."),
                        "translation": translations[0] if translations else "",
                    }
                )
        return items
    return [
        {"sentence": sentence, "translation": ""}
        for sentence in sentence_candidates(html_to_text(raw), min_chars=min_chars, max_chars=max_chars)
    ]


def is_tatoeba_api_url(url):
    return "api.tatoeba.org/" in url and "/v1/sentences" in url


def tatoeba_next_url(raw):
    if not raw.lstrip().startswith("{"):
        return ""
    try:
        data = json.loads(raw.lstrip())
    except json.JSONDecodeError:
        return ""
    paging = data.get("paging", {}) or {}
    return paging.get("next") or ""


def content_sentence_count(raw, url):
    stripped = raw.lstrip()
    if is_tatoeba_api_url(url) and stripped.startswith("{"):
        try:
            data = json.loads(stripped)
        except json.JSONDecodeError:
            return len(sentence_candidates(html_to_text(raw), min_chars=0, max_chars=1000))
        return len(data.get("data", []))
    return len(sentence_candidates(html_to_text(raw), min_chars=0, max_chars=1000))


def normalized_span_match(text, terms):
    def span_normalize(value):
        normalized = value.casefold()
        normalized = re.sub(r"([aeiou])['`Â´]", r"\1", normalized)
        normalized = unicodedata.normalize("NFD", normalized)
        normalized = "".join(char for char in normalized if unicodedata.category(char) != "Mn")
        normalized = normalized.replace("'", "").replace("`", "").replace("Â´", "")
        return normalized

    normalized_text = span_normalize(text)
    best = None
    for term in sorted((term for term in terms if term.strip()), key=len, reverse=True):
        normalized_term = span_normalize(term.strip())
        if not normalized_term:
            continue
        index = normalized_text.find(normalized_term)
        if index != -1:
            best = (index, index + len(normalized_term))
            break
    if best is None:
        return ""
    cursor = 0
    start = None
    end = None
    for index, char in enumerate(text):
        next_cursor = cursor + len(span_normalize(char))
        if start is None and next_cursor > best[0]:
            start = index
        if start is not None and next_cursor >= best[1]:
            end = index + 1
            break
        cursor = next_cursor
    if start is None or end is None:
        return ""
    return text[start:end].strip()


def normalize_match_text(value):
    text = value.strip().casefold()
    text = re.sub(r"([aeiou])['`´]", r"\1", text)
    text = unicodedata.normalize("NFD", text)
    text = "".join(char for char in text if unicodedata.category(char) != "Mn")
    text = text.replace("'", "").replace("`", "").replace("´", "")
    return text


def scraper_word_pattern(terms):
    terms = sorted({normalize_match_text(term) for term in terms if term.strip()}, key=len, reverse=True)
    if not terms:
        return None
    alternatives = []
    for term in terms:
        escaped_words = [re.escape(part) for part in term.split()]
        alternatives.append(r"\s+".join(escaped_words))
    return re.compile(
        r"(?<![\wÀ-ÖØ-öø-ÿ])(?:" + "|".join(alternatives) + r")(?![\wÀ-ÖØ-öø-ÿ])",
    )


def verbecc_search_terms(infinitive, tense):
    infinitive = infinitive.strip().lower()
    if not infinitive:
        raise ValueError("Verb is required.")
    terms = []
    seen = set()
    for form in lookup_verbecc_forms(infinitive, tense):
        value = form["value"]
        if value not in seen:
            seen.add(value)
            terms.append(value)
    return terms


def scraper_search_terms(word, tense, language):
    if scraper_language(language) == "it_ja" and tense:
        return verbecc_search_terms(word, tense)
    word = word.strip()
    if not word:
        raise ValueError("Search word is required.")
    return [word]


def expand_source_urls(source_lines, word, search_terms):
    urls = []
    seen = set()
    query_terms = search_terms or [word]
    for line in source_lines:
        source = line.strip()
        if not source.startswith(("http://", "https://")):
            continue
        expanded = []
        if "{query}" in source:
            for term in query_terms[:12]:
                expanded.append(source.replace("{query}", quote_plus(term)))
        else:
            expanded.append(source)
        for url in expanded:
            if url not in seen:
                seen.add(url)
                urls.append(url)
    return urls


def scrape_example_sentences(search_terms, source_urls, result_limit=80, min_chars=0, max_chars=320):
    results = []
    errors = []
    report = None
    for event in iter_scrape_events(search_terms, source_urls, result_limit, min_chars, max_chars):
        if event["type"] == "result":
            results.append(event["item"])
        elif event["type"] == "error":
            errors.append(event["message"])
        elif event["type"] == "report":
            report = event["report"]
    return results, errors, report or {}


def iter_scrape_events(search_terms, source_urls, result_limit=80, min_chars=0, max_chars=320):
    word_pattern = scraper_word_pattern(search_terms)
    result_limit = max(1, min(int(result_limit), SCRAPER_MAX_SENTENCES))
    min_chars = max(0, min(int(min_chars), 1000))
    max_chars = max(1, min(int(max_chars), 1000))
    if min_chars > max_chars:
        min_chars, max_chars = max_chars, min_chars
    report = {
        "sources": len(source_urls),
        "terms": len(search_terms),
        "search_terms": list(search_terms),
        "result_limit": result_limit,
        "min_chars": min_chars,
        "max_chars": max_chars,
        "visited": 0,
        "links_found": 0,
        "sentences_seen": 0,
        "filtered_by_length": 0,
        "sentences_checked": 0,
        "matches": 0,
        "per_url": {},
    }
    visited = set()
    results_count = 0
    opener = build_opener(HTTPCookieProcessor(CookieJar()))

    def process_raw_url(url, raw):
        nonlocal results_count
        before_matches = results_count
        events = []
        candidate_count = content_sentence_count(raw, url)
        filtered_items = content_sentence_items(raw, url, min_chars=min_chars, max_chars=max_chars)
        report["sentences_seen"] += candidate_count
        report["filtered_by_length"] += max(0, candidate_count - len(filtered_items))
        for item_data in filtered_items:
            sentence = item_data["sentence"]
            report["sentences_checked"] += 1
            if word_pattern and word_pattern.search(normalize_match_text(sentence)):
                results_count += 1
                target = normalized_span_match(sentence, search_terms)
                item = {
                    "sentence": sentence + ".",
                    "source": url,
                    "target": target,
                    "translation": item_data.get("translation", ""),
                }
                events.append({"type": "result", "item": item})
                if results_count >= result_limit:
                    break
        found_here = results_count - before_matches
        if found_here:
            report["per_url"][url] = found_here
        return events

    def scan_url(url, follow_links=False):
        nonlocal results_count
        if url in visited or results_count >= result_limit:
            return []
        visited.add(url)
        report["visited"] += 1
        events = [{"type": "status", "message": f"Checking {url}"}]
        try:
            raw = fetch_url_text(url, opener=opener)
        except HTTPError as exc:
            if exc.code == 403:
                root = site_root(url)
                try:
                    events.append({"type": "status", "message": f"Retrying {url} after opening {root}"})
                    fetch_url_text(root, opener=opener)
                    raw = fetch_url_text(url, opener=opener, referer=root)
                except HTTPError as retry_exc:
                    if retry_exc.code in {403, 404}:
                        events.append({"type": "status", "message": f"Skipped {url}: HTTP {retry_exc.code}"})
                    else:
                        events.append({"type": "error", "message": f"{url}: HTTP {retry_exc.code}"})
                    return events
                except Exception as retry_exc:
                    events.append({"type": "error", "message": f"{url}: {retry_exc}"})
                    return events
            elif exc.code == 404:
                events.append({"type": "status", "message": f"Skipped {url}: HTTP 404"})
                return events
            else:
                events.append({"type": "error", "message": f"{url}: HTTP {exc.code}"})
                return events
        except Exception as exc:
            message = f"{url}: {exc}"
            events.append({"type": "error", "message": message})
            return events
        events.extend(process_raw_url(url, raw))
        if results_count >= result_limit:
            report["matches"] = results_count
            return events
        if follow_links:
            links = extract_links(raw, url)
            report["links_found"] += len(links)
            events.append({"type": "status", "message": f"Found {len(links)} article links in {url}"})
            for link in links:
                events.extend(scan_url(link, follow_links=False))
                if results_count >= result_limit:
                    report["matches"] = results_count
                    return events
        return events

    def scan_tatoeba_source(url):
        nonlocal results_count
        next_url = url
        page = 1
        while next_url and results_count < result_limit:
            if next_url in visited:
                return
            visited.add(next_url)
            report["visited"] += 1
            yield {"type": "status", "message": f"Checking Tatoeba page {page}: {next_url}"}
            try:
                raw = fetch_url_text(next_url)
            except HTTPError as exc:
                yield {"type": "error", "message": f"{next_url}: HTTP {exc.code}"}
                return
            except Exception as exc:
                yield {"type": "error", "message": f"{next_url}: {exc}"}
                return
            for event in process_raw_url(next_url, raw):
                yield event
            if results_count >= result_limit:
                return
            next_url = tatoeba_next_url(raw)
            page += 1

    for source_url in source_urls:
        if is_tatoeba_api_url(source_url):
            yield from scan_tatoeba_source(source_url)
        else:
            for event in scan_url(source_url, follow_links=True):
                yield event
        if results_count >= result_limit:
            break
    report["matches"] = results_count
    yield {"type": "report", "report": report}
    yield {"type": "done", "message": f"Done. Found {results_count} results."}


def create_cloze_from_phrase(phrase, answer, translation):
    phrase = phrase.strip()
    answer = answer.strip()
    translation = translation.strip()
    if not phrase or not answer or not translation:
        return False, "Phrase, cloze text, and translation are required."
    def span_normalize(value):
        text = value.casefold()
        text = re.sub(r"([aeiou])['`Â´]", r"\1", text)
        text = unicodedata.normalize("NFD", text)
        text = "".join(char for char in text if unicodedata.category(char) != "Mn")
        text = text.replace("'", "").replace("`", "").replace("Â´", "")
        return text

    normalized_phrase = span_normalize(phrase)
    normalized_answer = span_normalize(answer.strip())
    normalized_index = normalized_phrase.find(normalized_answer)
    if normalized_index == -1:
        return False, "The cloze text was not found inside the selected phrase."
    cursor = 0
    start = None
    end = None
    for index, char in enumerate(phrase):
        normalized_char = span_normalize(char)
        next_cursor = cursor + len(normalized_char)
        if start is None and next_cursor > normalized_index:
            start = index
        if start is not None and next_cursor >= normalized_index + len(normalized_answer):
            end = index + 1
            break
        cursor = next_cursor
    if start is None or end is None:
        return False, "The cloze text was not found inside the selected phrase."
    stored_answer = phrase[start:end].strip()
    cloze_sentence = phrase[:start] + "____" + phrase[end:]
    uid = make_cloze_uid(cloze_sentence, stored_answer)
    content_hash = cloze_content_hash(cloze_sentence, stored_answer, translation)
    with get_db() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO cloze_questions
                (uid, sentence, answer, translation, content_hash, revision, elo, active, status, is_new)
            VALUES (?, ?, ?, ?, ?, 1, ?, 1, 'approved', 1)
            """,
            (uid, cloze_sentence, stored_answer, translation, content_hash, DEFAULT_ELO),
        )
    return True, "Cloze card created."


def extract_response_text(data):
    if data.get("output_text"):
        return data["output_text"]
    chunks = []
    for output in data.get("output", []):
        for content in output.get("content", []):
            if content.get("type") in {"output_text", "text"} and content.get("text"):
                chunks.append(content["text"])
    return "\n".join(chunks).strip()


def translate_sentences_with_openai(sentences, api_key="", material_language=DEFAULT_STUDY_LANGUAGE):
    api_key = (api_key or os.environ.get("OPENAI_API_KEY", "")).strip()
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")
    clean_sentences = [sentence.strip() for sentence in sentences if sentence.strip()]
    if not clean_sentences:
        return []
    model = os.environ.get("OPENAI_TRANSLATION_MODEL", "gpt-4.1-mini")
    source_name = "English" if scraper_language(material_language) == "ja_en" else "Italian"
    prompt = (
        f"Translate these {source_name} sentences into natural Japanese. "
        "Return only a JSON object with key \"translations\", whose value is an array of strings in the same order.\n\n"
        + json.dumps(clean_sentences, ensure_ascii=False)
    )
    payload = json.dumps(
        {
            "model": model,
            "input": prompt,
            "text": {"format": {"type": "json_object"}},
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = Request(
        "https://api.openai.com/v1/responses",
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urlopen(request, timeout=45) as response:
        data = json.loads(response.read().decode("utf-8"))
    text = extract_response_text(data)
    parsed = json.loads(text)
    if isinstance(parsed, dict):
        parsed = parsed.get("translations", [])
    if not isinstance(parsed, list):
        raise RuntimeError("OpenAI response did not contain a translation list.")
    return [str(item) for item in parsed]


def highlight_sentence_html(sentence, target):
    if not target:
        return escape(sentence)
    start = normalize_match_text(sentence).find(normalize_match_text(target))
    if start == -1:
        return escape(sentence)
    match = normalized_span_match(sentence, [target])
    if not match:
        return escape(sentence)
    raw_start = sentence.find(match)
    if raw_start == -1:
        return escape(sentence)
    raw_end = raw_start + len(match)
    return (
        escape(sentence[:raw_start])
        + f'<span class="cloze-hit">{escape(sentence[raw_start:raw_end])}</span>'
        + escape(sentence[raw_end:])
    )


def render_sentence_scraper(
    username,
    user,
    material_language=None,
    word="",
    tense="",
    sources="",
    result_limit=20,
    min_chars=40,
    max_chars=180,
    results=None,
    errors=None,
    report=None,
    message="",
):
    nav_html = render_nav(username, user, "管理")
    material_language = scraper_language(material_language or study_language(user))
    default_source_list = SCRAPER_DEFAULT_SOURCES_BY_LANGUAGE.get(material_language, SCRAPER_DEFAULT_SOURCES)
    source_library = SCRAPER_SOURCE_LIBRARY_BY_LANGUAGE.get(material_language, SCRAPER_SOURCE_LIBRARY)
    default_sources = "\n".join(default_source_list)
    sources_value = sources if sources else default_sources
    results = results or []
    errors = errors or []
    report = report or {}
    message_html = f'<div class="notice ok">{escape(message)}</div>' if message else ""
    search_tense_options = '<option value="" selected>単語だけ</option>'
    search_tense_options += "".join(
        f'<option value="{escape(key)}" {"selected" if key == tense else ""}>{escape(info["label"])}</option>'
        for key, info in SUPPORTED_TENSES.items()
    )
    language_options = "".join(
        f'<option value="{escape(key)}" {"selected" if key == material_language else ""}>{escape(info["label"])}</option>'
        for key, info in STUDY_LANGUAGES.items()
    )
    result_html = (
        "".join(
            '<div class="result-item">'
            f'<input class="result-check" type="checkbox" />'
            '<div class="result-main">'
            f'<div class="sentence">{highlight_sentence_html(item["sentence"], item.get("target", ""))}</div>'
            f'<button class="mini-button create-card-button" type="button" data-sentence="{escape(item["sentence"])}" data-target="{escape(item.get("target", ""))}" data-translation="{escape(item.get("translation", ""))}" onclick="openClozeModal(this)">+</button>'
            '</div>'
            f'<div class="translation">{escape(item.get("translation", ""))}</div>'
            f'<div class="source">{escape(item["source"])}</div>'
            "</div>"
            for item in results
        )
        if results
        else '<div class="empty">まだ例文はありません。</div>'
    )
    errors_html = (
        '<div class="errors">'
        + "".join(f'<div>{escape(error)}</div>' for error in errors[:12])
        + "</div>"
        if errors
        else ""
    )
    report_html = ""
    if report:
        per_url = report.get("per_url", {})
        per_url_html = "".join(
            f'<li>{escape(url)}: {count}</li>'
            for url, count in per_url.items()
        )
        terms_preview = ", ".join(report.get("search_terms", [])[:24])
        terms_html = f'<div class="terms-preview">{escape(terms_preview)}</div>' if terms_preview else ""
        report_html = f"""
        <div class="run-report">
          <strong>収集レポート</strong>
          <div>入力ソース: {int(report.get("sources", 0))}</div>
          <div>検索フォーム数: {int(report.get("terms", 0))}</div>
          <div>結果上限: {int(report.get("result_limit", result_limit))}</div>
          <div>最小文字数: {int(report.get("min_chars", min_chars))}</div>
          <div>最大文字数: {int(report.get("max_chars", max_chars))}</div>
          {terms_html}
          <div>確認したURL: {int(report.get("visited", 0))}</div>
          <div>見つけた記事リンク: {int(report.get("links_found", 0))}</div>
          <div>取得した文: {int(report.get("sentences_seen", 0))}</div>
          <div>文字数で除外: {int(report.get("filtered_by_length", 0))}</div>
          <div>確認した文候補: {int(report.get("sentences_checked", 0))}</div>
          <div>一致した例文: {int(report.get("matches", 0))}</div>
          <ul>{per_url_html}</ul>
        </div>
        """
    source_library_html = "".join(
        '<label class="source-choice">'
        f'<input type="checkbox" value="{escape(url)}" />'
        f'<span><strong>{escape(name)}</strong><em>{escape(kind)}</em><code>{escape(url)}</code></span>'
        "</label>"
        for name, kind, url in source_library
    )
    all_source_urls = "\n".join(url for _, _, url in source_library)
    sources_by_language_json = json.dumps(
        {
            key: "\n".join(value)
            for key, value in SCRAPER_DEFAULT_SOURCES_BY_LANGUAGE.items()
        },
        ensure_ascii=False,
    )
    source_library_by_language_json = json.dumps(
        {
            key: [
                {"name": name, "kind": kind, "url": url}
                for name, kind, url in value
            ]
            for key, value in SCRAPER_SOURCE_LIBRARY_BY_LANGUAGE.items()
        },
        ensure_ascii=False,
    )
    return f"""<!doctype html>
<html lang="ja">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>例文スクレイパー</title>
    <style>
      body {{
        font-family: Georgia, "Times New Roman", serif;
        background: #f5f0e6;
        color: #3d3630;
        margin: 0;
        padding: 32px;
      }}
      .wrap {{
        max-width: 980px;
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
      .card {{
        background: #fffef9;
        border: 1px solid #e8e0d4;
        border-radius: 12px;
        box-shadow: 0 12px 32px rgba(139, 125, 107, 0.12);
        padding: 24px;
      }}
      h1 {{
        margin: 0 0 18px;
        font-size: 26px;
      }}
      label {{
        color: #6b635c;
        display: block;
        font-size: 13px;
        font-weight: 600;
        margin: 12px 0 6px;
      }}
      input, textarea, select {{
        box-sizing: border-box;
        width: 100%;
        padding: 10px 12px;
        font-size: 15px;
        border: 1px solid #d8d0c4;
        border-radius: 8px;
        background: #fffef9;
      }}
      .search-grid {{
        display: grid;
        gap: 12px;
        grid-template-columns: minmax(0, 1fr) 170px 170px 120px 120px 120px;
      }}
      textarea {{
        min-height: 120px;
        resize: vertical;
      }}
      button {{
        background: #8fa68e;
        border: 0;
        border-radius: 10px;
        color: #fff;
        cursor: pointer;
        font-size: 15px;
        font-weight: 600;
        margin-top: 14px;
        padding: 11px 16px;
      }}
      button.secondary {{
        background: #b8aa97;
      }}
      .result-list {{
        display: grid;
        gap: 8px;
        margin-top: 18px;
      }}
      .result-item {{
        background: #faf7f0;
        border: 1px solid #e8e0d4;
        border-radius: 8px;
        display: grid;
        gap: 8px 10px;
        grid-template-columns: auto minmax(0, 1fr);
        padding: 12px;
      }}
      .result-check {{
        margin-top: 3px;
        width: auto;
      }}
      .result-main, .source, .translation {{
        grid-column: 2;
      }}
      .sentence {{
        font-size: 15px;
        line-height: 1.45;
      }}
      .cloze-hit {{
        background: #ffe08a;
        border-radius: 4px;
        color: #513f13;
        padding: 0 3px;
      }}
      .result-main {{
        align-items: flex-start;
        display: grid;
        gap: 10px;
        grid-template-columns: minmax(0, 1fr) auto;
      }}
      .create-card-button {{
        margin-top: 0;
      }}
      .source, .empty {{
        color: #7a7065;
        font-size: 12px;
        margin-top: 5px;
      }}
      .translation {{
        color: #557a53;
        font-size: 13px;
      }}
      .created-card {{
        opacity: 0.62;
      }}
      .scrape-actions {{
        align-items: center;
        display: flex;
        flex-wrap: wrap;
        gap: 10px;
      }}
      #openai-api-key {{
        max-width: 260px;
      }}
      .source-library {{
        border-top: 1px solid #e8e0d4;
        margin-top: 16px;
        padding-top: 14px;
      }}
      .source-library-head {{
        align-items: center;
        display: flex;
        gap: 12px;
        justify-content: space-between;
        margin-bottom: 6px;
      }}
      .source-library-head h2 {{
        font-size: 15px;
        margin: 0;
      }}
      .source-summary {{
        color: #7a7065;
        font-size: 12px;
        margin-top: 8px;
      }}
      .source-choice {{
        align-items: start;
        border-bottom: 1px solid #eee7dc;
        display: grid;
        gap: 10px;
        grid-template-columns: auto minmax(0, 1fr);
        padding: 8px 0;
      }}
      .source-choice input {{
        margin-top: 3px;
        width: auto;
      }}
      .source-choice em {{
        color: #7a7065;
        display: block;
        font-size: 11px;
        font-style: normal;
      }}
      .source-choice code {{
        background: #faf7f0;
        border: 1px solid #e8e0d4;
        border-radius: 6px;
        color: #6b635c;
        font-family: Consolas, monospace;
        font-size: 12px;
        min-width: 0;
        overflow: hidden;
        padding: 5px 7px;
        text-overflow: ellipsis;
        white-space: nowrap;
      }}
      .source-picker-list {{
        max-height: 52vh;
        overflow: auto;
      }}
      .mini-button {{
        border-radius: 7px;
        font-size: 13px;
        line-height: 1;
        margin: 0;
        min-width: 30px;
        padding: 7px 8px;
      }}
      .errors {{
        background: #f7e7e4;
        border-radius: 8px;
        color: #9b4d48;
        font-size: 12px;
        margin-top: 14px;
        padding: 10px 12px;
      }}
      .run-report, .working {{
        background: #f0ebe3;
        border-radius: 8px;
        color: #6b635c;
        font-size: 13px;
        line-height: 1.45;
        margin-top: 14px;
        padding: 10px 12px;
      }}
      .run-report ul {{
        margin: 6px 0 0 18px;
        padding: 0;
      }}
      .terms-preview {{
        color: #7a7065;
        font-size: 12px;
        margin: 4px 0 6px;
      }}
      .working {{
        display: none;
      }}
      .notice {{
        border-radius: 8px;
        font-size: 13px;
        margin-bottom: 14px;
        padding: 10px 12px;
      }}
      .ok {{
        background: #e9f1e8;
        color: #557a53;
      }}
      .modal-backdrop {{
        align-items: center;
        background: rgba(61, 54, 48, 0.42);
        display: none;
        inset: 0;
        justify-content: center;
        padding: 20px;
        position: fixed;
        z-index: 20;
      }}
      .modal {{
        background: #fffef9;
        border: 1px solid #e8e0d4;
        border-radius: 10px;
        box-shadow: 0 20px 60px rgba(61, 54, 48, 0.24);
        max-width: 720px;
        padding: 18px;
        width: min(720px, 100%);
      }}
      .modal h2 {{
        font-size: 18px;
        margin: 0 0 8px;
      }}
      .modal-actions {{
        display: flex;
        gap: 10px;
        justify-content: flex-end;
      }}
      .modal-actions .secondary {{
        background: #b8aa97;
      }}
      @media (max-width: 720px) {{
        .search-grid {{
          grid-template-columns: 1fr;
        }}
      }}
    </style>
    <script>
      function showScrapeStatus() {{
        var box = document.getElementById("scrape-status");
        if (box) {{
          box.style.display = "block";
          box.textContent = "ソースと記事リンクを確認中です。各ページは最大{SCRAPER_TIMEOUT_SECONDS}秒でタイムアウトし、各ソースから最大{SCRAPER_MAX_SOURCE_LINKS}件の記事を確認します。";
        }}
      }}
      function escapeHtml(value) {{
        return String(value).replace(/[&<>"']/g, function(char) {{
          return {{"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}}[char];
        }});
      }}
      var scrapeController = null;
      var scraperDefaultSources = {sources_by_language_json};
      var scraperSourceLibrary = {source_library_by_language_json};
      function scraperLanguage() {{
        var input = document.querySelector("select[name='material_language']");
        return input ? input.value : "{escape(material_language)}";
      }}
      function sourceStorageKey() {{
        return "verbiScraperSourcesV4:" + scraperLanguage();
      }}
      function highlightTarget(sentence, target) {{
        if (!target) {{
          return escapeHtml(sentence);
        }}
        var index = sentence.toLocaleLowerCase().indexOf(target.toLocaleLowerCase());
        if (index === -1) {{
          return escapeHtml(sentence);
        }}
        return escapeHtml(sentence.slice(0, index)) +
          '<span class="cloze-hit">' + escapeHtml(sentence.slice(index, index + target.length)) + '</span>' +
          escapeHtml(sentence.slice(index + target.length));
      }}
      function appendScrapeResult(item) {{
        var list = document.getElementById("result-list");
        if (!list) {{
          return;
        }}
        var empty = list.querySelector(".empty");
        if (empty) {{
          empty.remove();
        }}
        var div = document.createElement("div");
        div.className = "result-item";
        div.dataset.sentence = item.sentence || "";
        div.dataset.target = item.target || "";
        div.dataset.translation = item.translation || "";
        div.innerHTML =
          '<input class="result-check" type="checkbox" />' +
          '<div class="result-main">' +
          '<div class="sentence">' + highlightTarget(item.sentence || "", item.target || "") + '</div>' +
          '<button class="mini-button create-card-button" type="button" data-sentence="' + escapeHtml(item.sentence || "") + '" data-target="' + escapeHtml(item.target || "") + '" data-translation="' + escapeHtml(item.translation || "") + '" onclick="openClozeModal(this)">+</button>' +
          '</div>' +
          '<div class="translation">' + escapeHtml(item.translation || "") + '</div>' +
          '<div class="source">' + escapeHtml(item.source) + '</div>';
        list.appendChild(div);
      }}
      function appendScrapeError(message) {{
        var box = document.getElementById("errors-container");
        if (!box) {{
          return;
        }}
        var errors = box.querySelector(".errors");
        if (!errors) {{
          errors = document.createElement("div");
          errors.className = "errors";
          box.appendChild(errors);
        }}
        var line = document.createElement("div");
        line.textContent = message;
        errors.appendChild(line);
      }}
      function updateScrapeReport(report) {{
        var box = document.getElementById("report-container");
        if (!box || !report) {{
          return;
        }}
        var terms = (report.search_terms || []).slice(0, 24).join(", ");
        var perUrl = Object.entries(report.per_url || {{}}).map(function(entry) {{
          return "<li>" + escapeHtml(entry[0]) + ": " + Number(entry[1]) + "</li>";
        }}).join("");
        box.innerHTML =
          '<div class="run-report">' +
          '<strong>収集レポート</strong>' +
          '<div>入力ソース: ' + Number(report.sources || 0) + '</div>' +
          '<div>検索フォーム数: ' + Number(report.terms || 0) + '</div>' +
          '<div>結果上限: ' + Number(report.result_limit || 0) + '</div>' +
          '<div>最小文字数: ' + Number(report.min_chars || 0) + '</div>' +
          '<div>最大文字数: ' + Number(report.max_chars || 0) + '</div>' +
          (terms ? '<div class="terms-preview">' + escapeHtml(terms) + '</div>' : '') +
          '<div>確認したURL: ' + Number(report.visited || 0) + '</div>' +
          '<div>見つけた記事リンク: ' + Number(report.links_found || 0) + '</div>' +
          '<div>取得した文: ' + Number(report.sentences_seen || 0) + '</div>' +
          '<div>文字数で除外: ' + Number(report.filtered_by_length || 0) + '</div>' +
          '<div>確認した文候補: ' + Number(report.sentences_checked || 0) + '</div>' +
          '<div>一致した例文: ' + Number(report.matches || 0) + '</div>' +
          '<ul>' + perUrl + '</ul>' +
          '</div>';
      }}
      function setScrapeStatus(message) {{
        var box = document.getElementById("scrape-status");
        if (box) {{
          box.style.display = "block";
          box.textContent = message;
        }}
      }}
      function startScrapeStream(form) {{
        if (!window.fetch || !window.TextDecoder || !window.ReadableStream) {{
          showScrapeStatus();
          return true;
        }}
        showScrapeStatus();
        scrapeController = new AbortController();
        document.getElementById("stop-scrape-button").style.display = "inline-block";
        document.getElementById("result-list").innerHTML = '<div class="empty">検索中...</div>';
        document.getElementById("errors-container").innerHTML = "";
        document.getElementById("report-container").innerHTML = "";
        fetch("/admin/sentence-scraper/stream", {{
          method: "POST",
          body: new URLSearchParams(new FormData(form))
          , signal: scrapeController.signal
        }}).then(function(response) {{
          if (!response.body) {{
            form.submit();
            return;
          }}
          var reader = response.body.getReader();
          var decoder = new TextDecoder();
          var buffer = "";
          function pump() {{
            return reader.read().then(function(chunk) {{
              if (chunk.done) {{
                if (buffer.trim()) {{
                  handleScrapeLine(buffer.trim());
                }}
                return;
              }}
              buffer += decoder.decode(chunk.value, {{stream: true}});
              var lines = buffer.split("\\n");
              buffer = lines.pop();
              lines.forEach(handleScrapeLine);
              return pump();
            }});
          }}
          return pump();
        }}).catch(function(error) {{
          if (error.name === "AbortError") {{
            setScrapeStatus("Stopped.");
          }} else {{
            appendScrapeError(error.message || String(error));
          }}
        }}).finally(function() {{
          document.getElementById("stop-scrape-button").style.display = "none";
          scrapeController = null;
        }});
        return false;
      }}
      function stopScrape() {{
        if (scrapeController) {{
          scrapeController.abort();
        }}
      }}
      function selectedResultItems() {{
        return Array.from(document.querySelectorAll(".result-item")).filter(function(item) {{
          var checkbox = item.querySelector(".result-check");
          return checkbox && checkbox.checked;
        }});
      }}
      function setResultSelection(mode) {{
        document.querySelectorAll(".result-item").forEach(function(item) {{
          var checkbox = item.querySelector(".result-check");
          if (!checkbox) {{
            return;
          }}
          if (mode === "all") {{
            checkbox.checked = true;
          }} else if (mode === "missing") {{
            checkbox.checked = !(item.dataset.translation || "").trim();
          }} else if (mode === "translated") {{
            checkbox.checked = Boolean((item.dataset.translation || "").trim());
          }} else if (mode === "clear") {{
            checkbox.checked = false;
          }}
        }});
      }}
      function translateSelectedResults() {{
        var items = selectedResultItems();
        if (!items.length) {{
          setScrapeStatus("No results selected.");
          return;
        }}
        setScrapeStatus("Translating selected results...");
        var sentences = items.map(function(item) {{ return item.dataset.sentence || ""; }});
        var apiKeyInput = document.getElementById("openai-api-key");
        var apiKey = apiKeyInput ? apiKeyInput.value : "";
        fetch("/admin/sentence-scraper/translate", {{
          method: "POST",
          body: new URLSearchParams({{items: JSON.stringify(sentences), api_key: apiKey, material_language: scraperLanguage()}})
        }}).then(function(response) {{
          return response.json();
        }}).then(function(data) {{
          if (data.error) {{
            appendScrapeError(data.error);
            return;
          }}
          (data.translations || []).forEach(function(translation, index) {{
            var item = items[index];
            if (!item) {{
              return;
            }}
            item.dataset.translation = translation;
            var translationBox = item.querySelector(".translation");
            if (translationBox) {{
              translationBox.textContent = translation;
            }}
            var button = item.querySelector(".create-card-button");
            if (button) {{
              button.setAttribute("data-translation", translation);
            }}
          }});
          setScrapeStatus("Translations added.");
        }}).catch(function(error) {{
          appendScrapeError(error.message || String(error));
        }});
      }}
      function createSelectedCards() {{
        var items = selectedResultItems();
        if (!items.length) {{
          setScrapeStatus("No results selected.");
          return;
        }}
        var cards = items.map(function(item) {{
          return {{
            phrase: item.dataset.sentence || "",
            answer: item.dataset.target || "",
            translation: item.dataset.translation || ""
          }};
        }});
        setScrapeStatus("Creating selected cards...");
        fetch("/admin/sentence-scraper/create-cloze-batch", {{
          method: "POST",
          body: new URLSearchParams({{items: JSON.stringify(cards), material_language: scraperLanguage()}})
        }}).then(function(response) {{
          return response.json();
        }}).then(function(data) {{
          if (data.error) {{
            appendScrapeError(data.error);
            return;
          }}
          (data.results || []).forEach(function(result, index) {{
            var item = items[index];
            if (!item) {{
              return;
            }}
            if (result.ok) {{
              item.classList.add("created-card");
              var checkbox = item.querySelector(".result-check");
              if (checkbox) {{
                checkbox.checked = false;
              }}
            }} else {{
              appendScrapeError(result.error || "Card could not be created.");
            }}
          }});
          setScrapeStatus("Created " + Number(data.created || 0) + " cards. Skipped " + Number(data.skipped || 0) + ".");
        }}).catch(function(error) {{
          appendScrapeError(error.message || String(error));
        }});
      }}
      function handleScrapeLine(line) {{
        if (!line) {{
          return;
        }}
        var event = JSON.parse(line);
        if (event.type === "status") {{
          setScrapeStatus(event.message);
        }} else if (event.type === "result") {{
          appendScrapeResult(event.item);
        }} else if (event.type === "error") {{
          appendScrapeError(event.message);
        }} else if (event.type === "report") {{
          updateScrapeReport(event.report);
        }} else if (event.type === "done") {{
          setScrapeStatus(event.message);
        }}
      }}
      function addSource(button) {{
        var textarea = document.querySelector("textarea[name='sources']");
        var url = button.getAttribute("data-source");
        if (!textarea || !url) {{
          return;
        }}
        addSources([url]);
      }}
      function addSources(urls) {{
        var textarea = document.querySelector("textarea[name='sources']");
        if (!textarea) {{
          return;
        }}
        var lines = textarea.value.split(/\\r?\\n/).map(function(line) {{ return line.trim(); }});
        urls.forEach(function(url) {{
          if (lines.indexOf(url) === -1) {{
            lines.push(url);
          }}
        }});
        lines = lines.filter(function(line, index) {{
          return line && lines.indexOf(line) === index;
        }});
        textarea.value = lines.join("\\n");
      }}
      function addAllSources() {{
        var urls = document.getElementById("all-source-urls").value.split(/\\r?\\n/);
        addSources(urls);
      }}
      function renderSourceChoices() {{
        var list = document.querySelector("#source-modal .source-picker-list");
        if (!list) {{
          return;
        }}
        var sources = scraperSourceLibrary[scraperLanguage()] || [];
        list.innerHTML = sources.map(function(source) {{
          return '<label class="source-choice">' +
            '<input type="checkbox" value="' + escapeHtml(source.url || "") + '" />' +
            '<span><strong>' + escapeHtml(source.name || "") + '</strong>' +
            '<em>' + escapeHtml(source.kind || "") + '</em>' +
            '<code>' + escapeHtml(source.url || "") + '</code></span>' +
            '</label>';
        }}).join("");
        var allUrls = document.getElementById("all-source-urls");
        if (allUrls) {{
          allUrls.value = sources.map(function(source) {{ return source.url || ""; }}).join("\\n");
        }}
      }}
      function sourceTextarea() {{
        return document.querySelector("textarea[name='sources']");
      }}
      function sourceLines() {{
        var textarea = sourceTextarea();
        if (!textarea) {{
          return [];
        }}
        return textarea.value.split(/\\r?\\n/).map(function(line) {{ return line.trim(); }}).filter(Boolean);
      }}
      function updateSourceSummary() {{
        var summary = document.getElementById("source-summary");
        if (summary) {{
          summary.textContent = sourceLines().length + " sources selected";
        }}
      }}
      function openSourceModal() {{
        var selected = sourceLines();
        document.querySelectorAll("#source-modal input[type='checkbox']").forEach(function(input) {{
          input.checked = selected.indexOf(input.value) !== -1;
        }});
        document.getElementById("source-modal").style.display = "flex";
      }}
      function closeSourceModal() {{
        document.getElementById("source-modal").style.display = "none";
      }}
      function applySourceSelection() {{
        var urls = [];
        document.querySelectorAll("#source-modal input[type='checkbox']:checked").forEach(function(input) {{
          urls.push(input.value);
        }});
        var textarea = sourceTextarea();
        if (textarea) {{
          textarea.value = urls.join("\\n");
          localStorage.setItem(sourceStorageKey(), textarea.value);
        }}
        updateSourceSummary();
        closeSourceModal();
      }}
      function setAllSourceChoices(checked) {{
        document.querySelectorAll("#source-modal input[type='checkbox']").forEach(function(input) {{
          input.checked = checked;
        }});
      }}
      function useRecommendedSources() {{
        var textarea = sourceTextarea();
        var defaults = document.getElementById("default-source-urls");
        if (textarea && defaults) {{
          textarea.value = defaults.value;
          localStorage.setItem(sourceStorageKey(), textarea.value);
        }}
        updateSourceSummary();
        closeSourceModal();
      }}
      function restoreSavedSources() {{
        var saved = localStorage.getItem(sourceStorageKey());
        var textarea = sourceTextarea();
        if (saved && textarea) {{
          textarea.value = saved;
        }}
        updateSourceSummary();
      }}
      function changeScraperLanguage() {{
        renderSourceChoices();
        var textarea = sourceTextarea();
        if (textarea) {{
          var saved = localStorage.getItem(sourceStorageKey());
          textarea.value = saved || scraperDefaultSources[scraperLanguage()] || "";
        }}
        var tense = document.querySelector("select[name='tense']");
        if (tense) {{
          var italian = scraperLanguage() === "it_ja";
          tense.disabled = !italian;
          if (!italian) {{
            tense.value = "";
          }}
        }}
        var hiddenLanguage = document.querySelector("#cloze-modal input[name='material_language']");
        if (hiddenLanguage) {{
          hiddenLanguage.value = scraperLanguage();
        }}
        updateSourceSummary();
      }}
      function openClozeModal(button) {{
        var sentence = button.getAttribute("data-sentence") || "";
        var target = button.getAttribute("data-target") || "";
        var translation = button.getAttribute("data-translation") || "";
        var hiddenLanguage = document.querySelector("#cloze-modal input[name='material_language']");
        if (hiddenLanguage) {{
          hiddenLanguage.value = scraperLanguage();
        }}
        document.getElementById("cloze-phrase").value = sentence;
        document.getElementById("cloze-answer").value = target;
        document.getElementById("cloze-translation").value = translation;
        document.getElementById("cloze-modal").style.display = "flex";
        document.getElementById("cloze-answer").focus();
      }}
      function closeClozeModal() {{
        document.getElementById("cloze-modal").style.display = "none";
      }}
      function useSelectedClozeText() {{
        var phrase = document.getElementById("cloze-phrase");
        var answer = document.getElementById("cloze-answer");
        if (!phrase || !answer) {{
          return;
        }}
        var selected = phrase.value.substring(phrase.selectionStart, phrase.selectionEnd).trim();
        if (selected) {{
          answer.value = selected;
        }}
      }}
      document.addEventListener("DOMContentLoaded", function() {{
        restoreSavedSources();
        changeScraperLanguage();
      }});
    </script>
  </head>
  <body>
    <main class="wrap">
      {nav_html}
      <section class="card">
        <h1>例文スクレイパー</h1>
        {message_html}
        <form method="post" action="/admin/sentence-scraper" onsubmit="return startScrapeStream(this)">
          <div class="search-grid">
            <div>
              <label>検索する語 / 動詞</label>
              <input name="word" value="{escape(word)}" placeholder="andare" required />
            </div>
            <div>
              <label>教材</label>
              <select name="material_language" onchange="changeScraperLanguage()">{language_options}</select>
            </div>
            <div>
              <label>時制</label>
              <select name="tense">{search_tense_options}</select>
            </div>
            <div>
              <label>結果数</label>
              <input name="result_limit" type="number" min="1" max="{SCRAPER_MAX_SENTENCES}" value="{int(result_limit)}" />
            </div>
            <div>
              <label>最小文字数</label>
              <input name="min_chars" type="number" min="0" max="1000" value="{int(min_chars)}" />
            </div>
            <div>
              <label>最大文字数</label>
              <input name="max_chars" type="number" min="1" max="1000" value="{int(max_chars)}" />
            </div>
          </div>
          <label>ソースURL（RSSまたはページ、1行に1つ）</label>
          <textarea name="sources">{escape(sources_value)}</textarea>
          <div class="source-library">
            <div class="source-library-head">
              <h2>ソース選択</h2>
              <button class="mini-button" type="button" onclick="openSourceModal()">選択</button>
            </div>
            <div id="source-summary" class="source-summary"></div>
          </div>
          <div class="scrape-actions">
            <button type="submit">収集</button>
            <button id="stop-scrape-button" class="secondary" type="button" onclick="stopScrape()" style="display:none">停止</button>
            <button class="secondary" type="button" onclick="setResultSelection('all')">全部選択</button>
            <button class="secondary" type="button" onclick="setResultSelection('missing')">未翻訳を選択</button>
            <button class="secondary" type="button" onclick="setResultSelection('translated')">翻訳済みを選択</button>
            <button class="secondary" type="button" onclick="setResultSelection('clear')">選択解除</button>
            <input id="openai-api-key" type="password" autocomplete="off" placeholder="OpenAI API key" />
            <button class="secondary" type="button" onclick="translateSelectedResults()">選択を翻訳</button>
            <button class="secondary" type="button" onclick="createSelectedCards()">選択をカード化</button>
          </div>
        </form>
        <textarea id="all-source-urls" hidden>{escape(all_source_urls)}</textarea>
        <textarea id="default-source-urls" hidden>{escape(default_sources)}</textarea>
        <div id="scrape-status" class="working"></div>
        <div id="report-container">{report_html}</div>
        <div id="errors-container">{errors_html}</div>
        <div id="result-list" class="result-list">
          {result_html}
        </div>
      </section>
      <div id="cloze-modal" class="modal-backdrop">
        <form class="modal" method="post" action="/admin/sentence-scraper/create-cloze">
          <h2>クローズカード作成</h2>
          <input type="hidden" name="material_language" value="{escape(material_language)}" />
          <label>カードに使う文の範囲</label>
          <textarea id="cloze-phrase" name="phrase" required></textarea>
          <label>穴埋めにする部分</label>
          <button class="mini-button" type="button" onclick="useSelectedClozeText()">選択</button>
          <input id="cloze-answer" name="answer" required />
          <label>翻訳</label>
          <textarea id="cloze-translation" name="translation" required></textarea>
          <div class="modal-actions">
            <button class="secondary" type="button" onclick="closeClozeModal()">閉じる</button>
            <button type="submit">保存</button>
          </div>
        </form>
      </div>
      <div id="source-modal" class="modal-backdrop">
        <div class="modal">
          <h2>ソース選択</h2>
          <div class="modal-actions">
            <button class="secondary" type="button" onclick="useRecommendedSources()">おすすめ</button>
            <button class="secondary" type="button" onclick="setAllSourceChoices(true)">全部</button>
            <button class="secondary" type="button" onclick="setAllSourceChoices(false)">クリア</button>
          </div>
          <div class="source-picker-list">
            {source_library_html}
          </div>
          <div class="modal-actions">
            <button class="secondary" type="button" onclick="closeSourceModal()">閉じる</button>
            <button type="button" onclick="applySourceSelection()">保存</button>
          </div>
        </div>
      </div>
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


def answer_key(value):
    return normalize_match_text(normalize_answer(value))


def answers_match(user_answer, correct_answer):
    return answer_key(user_answer) == answer_key(correct_answer)


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

    if not has_users():
        if path == "/setup" and environ.get("REQUEST_METHOD") == "POST":
            form = parse_post(environ)
            name = form.get("name", "").strip() or "admin"
            password = form.get("password", "")
            confirm_password = form.get("confirm_password", "")
            if len(password) < 4:
                body = render_first_admin_setup("4文字以上で入力してください。")
                start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
                return [body.encode("utf-8")]
            if password != confirm_password:
                body = render_first_admin_setup("パスワードが一致しません。")
                start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
                return [body.encode("utf-8")]

            token = secrets.token_urlsafe(32)
            save_users(
                {
                    "users": {
                        name: {
                            "name": name,
                            "password": password_hash(password),
                            "elo": DEFAULT_ELO,
                            "password_reset_required": False,
                            "state": {"practiced_count": 0},
                            "session_token": token,
                            "is_admin": True,
                        }
                    }
                }
            )
            headers = []
            set_session_cookie(headers, token)
            return redirect(start_response, "/", headers)

        body = render_first_admin_setup()
        start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
        return [body.encode("utf-8")]

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
    set_active_material_language(user)

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

    if path == "/admin/sentence-scraper/stream" and environ.get("REQUEST_METHOD") == "POST":
        if not user.get("is_admin"):
            return redirect(start_response, "/")
        form = parse_post(environ)
        word = form.get("word", "").strip()
        tense = form.get("tense", "").strip()
        material_language = scraper_language(form.get("material_language", ""))
        try:
            result_limit = int(form.get("result_limit", "20"))
        except ValueError:
            result_limit = 20
        try:
            min_chars = int(form.get("min_chars", "40"))
        except ValueError:
            min_chars = 40
        try:
            max_chars = int(form.get("max_chars", "180"))
        except ValueError:
            max_chars = 180
        def stream():
            try:
                set_active_material_key(material_language)
                search_terms = scraper_search_terms(word, tense, material_language)
                source_urls = expand_source_urls(
                    form.get("sources", "").splitlines(),
                    word,
                    search_terms,
                )
                for event in iter_scrape_events(
                    search_terms,
                    source_urls,
                    result_limit=result_limit,
                    min_chars=min_chars,
                    max_chars=max_chars,
                ):
                    yield (json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8")
            except (RuntimeError, ValueError) as exc:
                yield (json.dumps({"type": "error", "message": str(exc)}, ensure_ascii=False) + "\n").encode("utf-8")
                report = {
                    "sources": 0,
                    "terms": 0,
                    "result_limit": result_limit,
                    "min_chars": min_chars,
                    "max_chars": max_chars,
                    "visited": 0,
                    "links_found": 0,
                    "sentences_seen": 0,
                    "filtered_by_length": 0,
                    "sentences_checked": 0,
                    "matches": 0,
                    "per_url": {},
                }
                yield (json.dumps({"type": "report", "report": report}, ensure_ascii=False) + "\n").encode("utf-8")
                yield (json.dumps({"type": "done", "message": "Done. Found 0 results."}, ensure_ascii=False) + "\n").encode("utf-8")

        start_response(
            "200 OK",
            [
                ("Content-Type", "application/x-ndjson; charset=utf-8"),
                ("Cache-Control", "no-cache"),
                ("X-Accel-Buffering", "no"),
            ],
        )
        return stream()

    if path == "/admin/sentence-scraper/translate" and environ.get("REQUEST_METHOD") == "POST":
        if not user.get("is_admin"):
            start_response("403 Forbidden", [("Content-Type", "application/json; charset=utf-8")])
            return [json.dumps({"error": "Forbidden"}).encode("utf-8")]
        form = parse_post(environ)
        try:
            sentences = json.loads(form.get("items", "[]"))
            translations = translate_sentences_with_openai(
                sentences,
                form.get("api_key", ""),
                form.get("material_language", ""),
            )
            body = {"translations": translations}
        except Exception as exc:
            body = {"error": str(exc)}
        start_response("200 OK", [("Content-Type", "application/json; charset=utf-8")])
        return [json.dumps(body, ensure_ascii=False).encode("utf-8")]

    if path == "/admin/sentence-scraper":
        if not user.get("is_admin"):
            return redirect(start_response, "/")
        if environ.get("REQUEST_METHOD") == "POST":
            form = parse_post(environ)
            word = form.get("word", "").strip()
            tense = form.get("tense", "").strip()
            material_language = scraper_language(form.get("material_language", ""))
            try:
                result_limit = int(form.get("result_limit", "20"))
            except ValueError:
                result_limit = 20
            try:
                min_chars = int(form.get("min_chars", "40"))
            except ValueError:
                min_chars = 40
            try:
                max_chars = int(form.get("max_chars", "180"))
            except ValueError:
                max_chars = 180
            sources = form.get("sources", "")
            try:
                set_active_material_key(material_language)
                search_terms = scraper_search_terms(word, tense, material_language)
                source_urls = expand_source_urls(sources.splitlines(), word, search_terms)
                results, errors, report = scrape_example_sentences(
                    search_terms,
                    source_urls,
                    result_limit=result_limit,
                    min_chars=min_chars,
                    max_chars=max_chars,
                )
            except (RuntimeError, ValueError) as exc:
                results, errors, report = [], [str(exc)], {
                    "sources": 0,
                    "terms": 0,
                    "result_limit": result_limit,
                    "min_chars": min_chars,
                    "max_chars": max_chars,
                }
            body = render_sentence_scraper(
                username,
                user,
                material_language=material_language,
                word=word,
                tense=tense,
                sources=sources,
                result_limit=result_limit,
                min_chars=min_chars,
                max_chars=max_chars,
                results=results,
                errors=errors,
                report=report,
            )
        else:
            body = render_sentence_scraper(username, user)
        start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
        return [body.encode("utf-8")]

    if path == "/admin/sentence-scraper/create-cloze" and environ.get("REQUEST_METHOD") == "POST":
        if not user.get("is_admin"):
            return redirect(start_response, "/")
        form = parse_post(environ)
        material_language = scraper_language(form.get("material_language", ""))
        set_active_material_key(material_language)
        ok, text = create_cloze_from_phrase(
            form.get("phrase", ""),
            form.get("answer", ""),
            form.get("translation", ""),
        )
        body = render_sentence_scraper(
            username,
            user,
            material_language=material_language,
            message=text if ok else "",
            errors=[] if ok else [text],
        )
        start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
        return [body.encode("utf-8")]

    if path == "/admin/sentence-scraper/create-cloze-batch" and environ.get("REQUEST_METHOD") == "POST":
        if not user.get("is_admin"):
            start_response("403 Forbidden", [("Content-Type", "application/json; charset=utf-8")])
            return [json.dumps({"error": "Forbidden"}).encode("utf-8")]
        form = parse_post(environ)
        try:
            material_language = scraper_language(form.get("material_language", ""))
            set_active_material_key(material_language)
            items = json.loads(form.get("items", "[]"))
            if not isinstance(items, list):
                raise ValueError("Invalid card list.")
            results = []
            created = 0
            for item in items[:SCRAPER_MAX_SENTENCES]:
                if not isinstance(item, dict):
                    results.append({"ok": False, "error": "Invalid selected item."})
                    continue
                ok, text = create_cloze_from_phrase(
                    str(item.get("phrase", "")),
                    str(item.get("answer", "")),
                    str(item.get("translation", "")),
                )
                if ok:
                    created += 1
                    results.append({"ok": True})
                else:
                    results.append({"ok": False, "error": text})
            body = {
                "created": created,
                "skipped": max(0, len(items[:SCRAPER_MAX_SENTENCES]) - created),
                "results": results,
            }
        except Exception as exc:
            body = {"error": str(exc)}
        start_response("200 OK", [("Content-Type", "application/json; charset=utf-8")])
        return [json.dumps(body, ensure_ascii=False).encode("utf-8")]

    if path == "/admin/content":
        if not user.get("is_admin"):
            return redirect(start_response, "/")
        query = parse_qs(environ.get("QUERY_STRING", ""))
        active_tab = (query.get("tab") or ["review"])[0]
        body = render_content_admin(load_pending_content(), active_tab=active_tab)
        start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
        return [body.encode("utf-8")]

    if path == "/admin/content/import-tense" and environ.get("REQUEST_METHOD") == "POST":
        if not user.get("is_admin"):
            return redirect(start_response, "/")
        form = parse_post(environ)
        ok, text = import_verbecc_verb_tense(
            form.get("infinitive", ""),
            form.get("ja", ""),
            form.get("tense", "presente"),
        )
        if ok:
            body = render_content_admin(message=text, active_tab="tenses")
        else:
            body = render_content_admin(error=text, active_tab="tenses")
        start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
        return [body.encode("utf-8")]

    if path == "/admin/content/approve" and environ.get("REQUEST_METHOD") == "POST":
        if not user.get("is_admin"):
            return redirect(start_response, "/")
        form = parse_post(environ)
        content_id = form.get("id", "")
        message = ""
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
            else:
                ok, text = approve_pending_content(conn, row, username)
                if ok:
                    message = text
                else:
                    error = text
        body = render_content_admin(message=message, error=error)
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

    if path == "/admin/content/edit" and environ.get("REQUEST_METHOD") == "POST":
        if not user.get("is_admin"):
            return redirect(start_response, "/")
        form = parse_post(environ)
        if update_approved_card(form):
            body = render_content_admin(message="カードを更新しました。")
        else:
            body = render_content_admin(error="カードを更新できませんでした。")
        start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
        return [body.encode("utf-8")]

    if path == "/admin/content/delete" and environ.get("REQUEST_METHOD") == "POST":
        if not user.get("is_admin"):
            return redirect(start_response, "/")
        form = parse_post(environ)
        if delete_approved_card(form):
            body = render_content_admin(message="カードを削除しました。")
        else:
            body = render_content_admin(error="カードを削除できませんでした。")
        start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
        return [body.encode("utf-8")]

    if path == "/admin/content/reset-elo" and environ.get("REQUEST_METHOD") == "POST":
        if not user.get("is_admin"):
            return redirect(start_response, "/")
        form = parse_post(environ)
        if reset_approved_card_elo(form):
            body = render_content_admin(message="ELOをリセットしました。")
        else:
            body = render_content_admin(error="ELOをリセットできませんでした。")
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

    if path == "/settings":
        if environ.get("REQUEST_METHOD") == "POST":
            form = parse_post(environ)
            update_daily_settings(
                username,
                form.get("daily_target", DEFAULT_DAILY_TARGET),
                form.get("daily_vacation_mode") == "1",
                form.get("study_language"),
            )
            return redirect(start_response, "/settings")
        body = render_settings(username, user)
        start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
        return [body.encode("utf-8")]

    if path == "/licenses":
        body = render_licenses(username, user)
        start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
        return [body.encode("utf-8")]

    if path == "/daily/settings" and environ.get("REQUEST_METHOD") == "POST":
        form = parse_post(environ)
        update_daily_settings(
            username,
            form.get("daily_target", DEFAULT_DAILY_TARGET),
            form.get("daily_vacation_mode") == "1",
            form.get("study_language"),
        )
        return redirect(start_response, "/")

    if path == "/daily":
        result = None
        finished = False
        streak = None
        if daily_completed_today(user):
            body = render_daily(username, user, {"total": 1, "index": 1, "items": []}, finished=True)
            start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
            return [body.encode("utf-8")]
        if environ.get("REQUEST_METHOD") == "POST":
            form = parse_post(environ)
            state = decode_daily_state(form.get("state", ""))
            if not state or not state.get("items"):
                return redirect(start_response, "/daily")
            index = int(state.get("index", 0))
            if index >= len(state["items"]):
                streak = complete_daily(username)
                clear_saved_daily_state(username)
                user = load_users()["users"].get(username, user)
                body = render_daily(username, user, state, finished=True, streak=streak)
                start_response("200 OK", [("Content-Type", "text/html; charset=utf-8")])
                return [body.encode("utf-8")]

            item = state["items"][index]
            raw_answer = form.get("answer", "")
            if item["game"] == "flashcard":
                correct_answer = item["translation"]
                ok = raw_answer == correct_answer
                game = "flashcard"
                update_function = update_elo
            elif item["game"] == "cloze":
                correct_answer = normalize_answer(item["answer"])
                ok = answers_match(raw_answer, item["answer"])
                game = "cloze"
                update_function = update_cloze_elo
            else:
                correct_answer = normalize_answer(item["answer"])
                ok = answers_match(raw_answer, item["answer"])
                game = "verb_form"
                update_function = update_elo

            question_id = item.get("question_id", "")
            if question_id:
                if update_function == update_cloze_elo:
                    update_function(username, int(question_id), ok)
                else:
                    update_function(username, int(question_id), ok, game)

            state["history"].append(
                {
                    "game": item["game"],
                    "ok": ok,
                    "answer": correct_answer,
                }
            )
            state["index"] = index + 1
            user = increment_practiced_count(username) or user
            result = {"ok": ok, "answer": correct_answer}

            if state["index"] >= len(state["items"]):
                finished = True
                streak = complete_daily(username)
                clear_saved_daily_state(username)
                user = load_users()["users"].get(username, user)
            else:
                save_daily_state(username, state)
        else:
            state = load_saved_daily_state(username)
            if not state:
                state = build_daily_state(user)
                save_daily_state(username, state)

        body = render_daily(
            username,
            user,
            state,
            result=result,
            finished=finished,
            streak=streak,
        )
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
            ok = answers_match(user_answer, correct_answer)
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

    if path.startswith("/verbs") and not STUDY_LANGUAGES[study_language(user)].get("verb_enabled"):
        return redirect(start_response, "/")

    if path == "/verbs" and environ.get("REQUEST_METHOD") == "POST":
        form = parse_post(environ)
        state = decode_state(form.get("state", ""))
        user_answer = normalize_answer(form.get("user_answer", ""))
        correct = normalize_answer(form.get("q_answer", ""))
        ok = answers_match(user_answer, correct)
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

