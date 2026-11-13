#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Clockify Clone PT-BR - Sistema Completo de Controle de Horas, Planilha Semanal,
Projetos, Clientes, Equipe, Relatorios e Auto-Tracker (Windows / AutoCAD).
"""

import ctypes
from ctypes import wintypes
import datetime
import json
import os
import sqlite3
import threading
import time
import urllib.parse
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "clockify_local.db")
PORT = 8765

db_lock = threading.Lock()


def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db_lock:
        conn = get_db()
        cur = conn.cursor()

        cur.execute("""
            CREATE TABLE IF NOT EXISTS clients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                status TEXT DEFAULT 'ATIVO',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT DEFAULT '',
                name TEXT NOT NULL,
                client_id INTEGER,
                color TEXT DEFAULT '#03a9f4',
                billable INTEGER DEFAULT 1,
                hourly_rate REAL DEFAULT 0,
                budget_hours REAL DEFAULT 0,
                dwg_pattern TEXT DEFAULT '',
                status TEXT DEFAULT 'ATIVO',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(client_id) REFERENCES clients(id)
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT DEFAULT '',
                role TEXT DEFAULT 'Membro',
                hourly_rate REAL DEFAULT 0
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS time_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER,
                user_name TEXT DEFAULT 'Voce',
                description TEXT DEFAULT '',
                tag TEXT DEFAULT '',
                billable INTEGER DEFAULT 1,
                source TEXT DEFAULT 'TIMER',
                dwg_file TEXT DEFAULT '',
                start_time TEXT NOT NULL,
                end_time TEXT,
                duration_seconds INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(project_id) REFERENCES projects(id)
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS auto_tracker_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                app_name TEXT DEFAULT '',
                window_title TEXT NOT NULL,
                start_time TEXT NOT NULL,
                end_time TEXT NOT NULL,
                duration_seconds INTEGER DEFAULT 0
            )
        """)

        cur.execute("""
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)

        # Dados iniciais de exemplo estilo Clockify
        if cur.execute("SELECT COUNT(*) AS c FROM clients").fetchone()["c"] == 0:
            cur.execute("INSERT INTO clients (name, email) VALUES ('Fortbras / Interno', 'contato@empresa.com.br')")
            cur.execute("INSERT INTO clients (name, email) VALUES ('Cliente Engenharia S/A', 'projetos@cliente.com.br')")

        if cur.execute("SELECT COUNT(*) AS c FROM projects").fetchone()["c"] == 0:
            cur.execute("""
                INSERT INTO projects (code, name, client_id, color, billable, hourly_rate, budget_hours, dwg_pattern)
                VALUES
                ('PRJ-01', 'Projeto Arquitetônico / AutoCAD', 2, '#03a9f4', 1, 150.0, 80, 'planta,arq,dwg'),
                ('PRJ-02', 'Detalhamento Executivo', 2, '#8bc34a', 1, 180.0, 40, 'det,exec'),
                ('INT-01', 'Reuniões e Gestão Interna', 1, '#ff9800', 0, 0.0, 20, '')
            """)

        if cur.execute("SELECT COUNT(*) AS c FROM tags").fetchone()["c"] == 0:
            for t in ["AutoCAD", "Desenho 2D/3D", "Reunião", "Revisão", "Levantamento", "Urgente"]:
                cur.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (t,))

        default_user = os.environ.get("USERNAME", "Projetista")
        if cur.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"] == 0:
            cur.execute("INSERT INTO users (name, email, role, hourly_rate) VALUES (?, '', 'Admin', 150.0)", (default_user,))

        # Se for um banco antigo antes da confirmacao do Auto-Rastreador, inicia desligado ate o usuario confirmar
        has_confirmed_key = cur.execute("SELECT value FROM settings WHERE key='auto_tracker_confirmed'").fetchone()
        if not has_confirmed_key:
            cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('auto_tracker_enabled', '0')")
            cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('auto_tracker_confirmed', '0')")

        default_settings = {
            "user_name": default_user,
            "idle_timeout_seconds": "300",
            "auto_tracker_enabled": "0",
            "auto_tracker_confirmed": "0"
        }
        for k, v in default_settings.items():
            cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))

        conn.commit()
        conn.close()


# ==============================================================================
# AUTO TRACKER (MONITOR DE JANELAS ATIVAS DO WINDOWS ESTILO CLOCKIFY DESKTOP)
# ==============================================================================

class LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


def get_windows_idle_seconds():
    if os.name != "nt":
        return 0
    try:
        lii = LASTINPUTINFO()
        lii.cbSize = ctypes.sizeof(LASTINPUTINFO)
        if ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
            millis = ctypes.windll.kernel32.GetTickCount() - lii.dwTime
            return max(0, int(millis / 1000))
    except Exception:
        pass
    return 0


def get_active_window_title():
    if os.name != "nt":
        return ""
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return ""
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return ""
        buff = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buff, length + 1)
        return buff.value.strip()
    except Exception:
        return ""


class ActiveTimerState:
    def __init__(self):
        self.lock = threading.Lock()
        self.running = False
        self.log_id = None
        self.project_id = 1
        self.description = ""
        self.tag = ""
        self.billable = 1
        self.start_ts = None
        self.start_str = ""

        # Auto Tracker current window
        self.current_win_title = ""
        self.current_win_id = None
        self.idle_seconds = 0


timer_state = ActiveTimerState()


def detect_app_name(win_title):
    low = (win_title or "").lower()
    if "autocad" in low or ".dwg" in low or "civil 3d" in low or "autodesk" in low:
        return "AutoCAD"
    if "revit" in low or ".rvt" in low:
        return "Revit"
    if "excel" in low or ".xlsx" in low or ".csv" in low:
        return "Excel"
    if " - " in win_title:
        return win_title.split(" - ")[-1].strip() or "Aplicativo"
    return "Aplicativo"


def background_worker():
    while True:
        time.sleep(2)
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            idle_sec = get_windows_idle_seconds()
            win_title = get_active_window_title()

            with db_lock:
                conn = get_db()
                cur = conn.cursor()

                en_row = cur.execute("SELECT value FROM settings WHERE key='auto_tracker_enabled'").fetchone()
                auto_enabled = (en_row["value"] == "1") if en_row else False

                idle_row = cur.execute("SELECT value FROM settings WHERE key='idle_timeout_seconds'").fetchone()
                try:
                    idle_limit = int(idle_row["value"]) if idle_row and idle_row["value"] else 300
                except Exception:
                    idle_limit = 300

                with timer_state.lock:
                    timer_state.idle_seconds = idle_sec

                    # 1. Atualiza Cronometro Oficial se estiver rodando
                    if timer_state.running and timer_state.log_id and timer_state.start_ts:
                        elapsed = max(1, int(time.time() - timer_state.start_ts))
                        cur.execute("""
                            UPDATE time_logs
                            SET end_time = ?, duration_seconds = ?
                            WHERE id = ?
                        """, (now_str, elapsed, timer_state.log_id))

                    # 2. Auto-Tracker: grava em segundo plano SOMENTE se estiver ativado pelo usuario
                    is_own_panel = ("Clockify —" in win_title) or ("localhost:8765" in win_title) or ("omni-clockify" in win_title.lower())
                    if auto_enabled and win_title and idle_sec < idle_limit and not is_own_panel:
                        app_guess = detect_app_name(win_title)
                        if timer_state.current_win_title == win_title and timer_state.current_win_id:
                            cur.execute("""
                                UPDATE auto_tracker_events
                                SET end_time = ?, duration_seconds = duration_seconds + 2
                                WHERE id = ?
                            """, (now_str, timer_state.current_win_id))
                        else:
                            timer_state.current_win_title = win_title
                            cur.execute("""
                                INSERT INTO auto_tracker_events (app_name, window_title, start_time, end_time, duration_seconds)
                                VALUES (?, ?, ?, ?, 2)
                            """, (app_guess, win_title, now_str, now_str))
                            timer_state.current_win_id = cur.lastrowid
                    else:
                        timer_state.current_win_title = ""
                        timer_state.current_win_id = None

                conn.commit()
                conn.close()
        except Exception:
            pass


# ==============================================================================
# HTTP HANDLER
# ==============================================================================

class ClockifyHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Private-Network", "true")

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def _send_json(self, data, status=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self._send_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html"):
            with open(os.path.join(BASE_DIR, "index.html"), "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
            return

        if path == "/api/state":
            with db_lock:
                conn = get_db()
                cur = conn.cursor()

                clients = [dict(r) for r in cur.execute("SELECT * FROM clients ORDER BY name").fetchall()]
                tags = [dict(r) for r in cur.execute("SELECT * FROM tags ORDER BY name").fetchall()]
                users = [dict(r) for r in cur.execute("SELECT * FROM users ORDER BY name").fetchall()]

                projects = [dict(r) for r in cur.execute("""
                    SELECT p.*, c.name AS client_name,
                           COALESCE(SUM(t.duration_seconds), 0) AS total_seconds,
                           COUNT(t.id) AS entries_count
                    FROM projects p
                    LEFT JOIN clients c ON c.id = p.client_id
                    LEFT JOIN time_logs t ON t.project_id = p.id
                    GROUP BY p.id
                    ORDER BY p.id DESC
                """).fetchall()]

                logs = [dict(r) for r in cur.execute("""
                    SELECT t.*,
                           p.name AS project_name,
                           p.code AS project_code,
                           p.color AS project_color,
                           p.hourly_rate AS project_rate,
                           c.name AS client_name
                    FROM time_logs t
                    LEFT JOIN projects p ON p.id = t.project_id
                    LEFT JOIN clients c ON c.id = p.client_id
                    ORDER BY t.start_time DESC, t.id DESC
                    LIMIT 400
                """).fetchall()]

                auto_events = [dict(r) for r in cur.execute("""
                    SELECT * FROM auto_tracker_events
                    WHERE duration_seconds >= 2
                    ORDER BY id DESC
                    LIMIT 80
                """).fetchall()]

                settings = {r["key"]: r["value"] for r in cur.execute("SELECT key, value FROM settings").fetchall()}
                conn.close()

            auto_enabled = (settings.get("auto_tracker_enabled") == "1")
            with timer_state.lock:
                elapsed = max(0, int(time.time() - timer_state.start_ts)) if timer_state.running and timer_state.start_ts else 0
                timer = {
                    "running": timer_state.running,
                    "log_id": timer_state.log_id,
                    "project_id": timer_state.project_id,
                    "description": timer_state.description,
                    "tag": timer_state.tag,
                    "billable": timer_state.billable,
                    "elapsed": elapsed,
                    "current_win_title": timer_state.current_win_title if auto_enabled else "",
                    "idle_seconds": timer_state.idle_seconds,
                    "auto_tracker_enabled": auto_enabled,
                }

            self._send_json({
                "timer": timer,
                "clients": clients,
                "projects": projects,
                "tags": tags,
                "users": users,
                "logs": logs,
                "auto_events": auto_events,
                "settings": settings
            })
            return

        if path == "/api/export.csv":
            with db_lock:
                conn = get_db()
                rows = conn.execute("""
                    SELECT t.id, p.code, p.name AS project_name, c.name AS client_name,
                           t.description, t.tag, t.user_name, t.billable,
                           t.start_time, t.end_time, t.duration_seconds, p.hourly_rate
                    FROM time_logs t
                    LEFT JOIN projects p ON p.id = t.project_id
                    LEFT JOIN clients c ON c.id = p.client_id
                    ORDER BY t.start_time DESC
                """).fetchall()
                conn.close()

            header = "ID;Projeto;Cliente;Descricao;Etiqueta;Usuario;Faturavel;Inicio;Fim;Duracao (h);Valor Hora (R$);Valor Total (R$)"
            lines = [header]
            for r in rows:
                hrs = round((r["duration_seconds"] or 0) / 3600.0, 2)
                rate = float(r["hourly_rate"] or 0) if r["billable"] else 0.0
                val = round(hrs * rate, 2)
                lines.append(
                    f'{r["id"]};"{r["project_name"] or "Sem Projeto"}";"{r["client_name"] or ""}";'
                    f'"{(r["description"] or "").replace(chr(34), chr(39))}";"{r["tag"] or ""}";'
                    f'"{r["user_name"] or ""}";"{"Sim" if r["billable"] else "Nao"}";'
                    f'"{r["start_time"] or ""}";"{r["end_time"] or ""}";'
                    f'{str(hrs).replace(".", ",")};{str(rate).replace(".", ",")};{str(val).replace(".", ",")}'
                )
            csv_bytes = ("\ufeff" + "\r\n".join(lines)).encode("utf-8")
            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Type", "text/csv; charset=utf-8")
            self.send_header("Content-Disposition", 'attachment; filename="clockify_relatorio_horas.csv"')
            self.send_header("Content-Length", str(len(csv_bytes)))
            self.end_headers()
            self.wfile.write(csv_bytes)
            return

        self.send_error(404)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
        data = json.loads(raw or "{}")
        path = urllib.parse.urlparse(self.path).path
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if path == "/api/timer/start":
            project_id = int(data.get("project_id") or 1)
            description = (data.get("description") or "").strip() or "(Sem descrição)"
            tag = (data.get("tag") or "").strip()
            billable = 1 if data.get("billable", True) else 0

            with db_lock:
                conn = get_db()
                cur = conn.cursor()
                u_row = cur.execute("SELECT value FROM settings WHERE key='user_name'").fetchone()
                user_name = u_row["value"] if u_row else "Projetista"

                cur.execute("""
                    INSERT INTO time_logs (project_id, user_name, description, tag, billable, source, start_time, end_time, duration_seconds)
                    VALUES (?, ?, ?, ?, ?, 'TIMER', ?, ?, 1)
                """, (project_id, user_name, description, tag, billable, now_str, now_str))
                log_id = cur.lastrowid
                conn.commit()
                conn.close()

            with timer_state.lock:
                timer_state.running = True
                timer_state.log_id = log_id
                timer_state.project_id = project_id
                timer_state.description = description
                timer_state.tag = tag
                timer_state.billable = billable
                timer_state.start_ts = time.time()
                timer_state.start_str = now_str

            self._send_json({"ok": True, "log_id": log_id})
            return

        if path == "/api/timer/stop":
            with timer_state.lock:
                if timer_state.running and timer_state.log_id:
                    elapsed = max(1, int(time.time() - timer_state.start_ts))
                    log_id = timer_state.log_id
                    desc = data.get("description", timer_state.description)
                    proj_id = int(data.get("project_id") or timer_state.project_id)
                    tag = data.get("tag", timer_state.tag)
                    billable = 1 if data.get("billable", timer_state.billable) else 0
                    timer_state.running = False
                    timer_state.log_id = None
                    timer_state.start_ts = None
                else:
                    log_id = None

            if log_id:
                with db_lock:
                    conn = get_db()
                    conn.execute("""
                        UPDATE time_logs
                        SET project_id = ?, description = ?, tag = ?, billable = ?, end_time = ?, duration_seconds = ?
                        WHERE id = ?
                    """, (proj_id, desc, tag, billable, now_str, elapsed, log_id))
                    conn.commit()
                    conn.close()

            self._send_json({"ok": True})
            return

        if path == "/api/logs/add":
            project_id = int(data.get("project_id") or 1)
            description = (data.get("description") or "").strip() or "(Sem descrição)"
            tag = (data.get("tag") or "").strip()
            billable = 1 if data.get("billable", True) else 0
            date_str = data.get("date") or datetime.date.today().strftime("%Y-%m-%d")
            start_hm = data.get("start_hm") or "09:00"
            end_hm = data.get("end_hm") or "10:00"
            duration_sec = int(data.get("duration_seconds") or 0)

            if duration_sec <= 0:
                try:
                    t1 = datetime.datetime.strptime(f"{date_str} {start_hm}", "%Y-%m-%d %H:%M")
                    t2 = datetime.datetime.strptime(f"{date_str} {end_hm}", "%Y-%m-%d %H:%M")
                    if t2 < t1:
                        t2 += datetime.timedelta(days=1)
                    duration_sec = max(60, int((t2 - t1).total_seconds()))
                except Exception:
                    duration_sec = 3600

            start_full = f"{date_str} {start_hm}:00"
            end_full = f"{date_str} {end_hm}:00"

            with db_lock:
                conn = get_db()
                cur = conn.cursor()
                u_row = cur.execute("SELECT value FROM settings WHERE key='user_name'").fetchone()
                user_name = u_row["value"] if u_row else "Projetista"
                cur.execute("""
                    INSERT INTO time_logs (project_id, user_name, description, tag, billable, source, start_time, end_time, duration_seconds)
                    VALUES (?, ?, ?, ?, ?, 'MANUAL', ?, ?, ?)
                """, (project_id, user_name, description, tag, billable, start_full, end_full, duration_sec))
                conn.commit()
                conn.close()
            self._send_json({"ok": True})
            return

        if path == "/api/logs/delete":
            log_id = int(data.get("id") or 0)
            with db_lock:
                conn = get_db()
                conn.execute("DELETE FROM time_logs WHERE id = ?", (log_id,))
                conn.commit()
                conn.close()
            self._send_json({"ok": True})
            return

        if path == "/api/projects/add":
            with db_lock:
                conn = get_db()
                conn.execute("""
                    INSERT INTO projects (code, name, client_id, color, billable, hourly_rate, budget_hours)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    (data.get("code") or "").strip(),
                    (data.get("name") or "Novo Projeto").strip(),
                    int(data.get("client_id") or 1),
                    data.get("color") or "#03a9f4",
                    1 if data.get("billable", True) else 0,
                    float(data.get("hourly_rate") or 0),
                    float(data.get("budget_hours") or 0),
                ))
                conn.commit()
                conn.close()
            self._send_json({"ok": True})
            return

        if path == "/api/projects/delete":
            pid = int(data.get("id") or 0)
            with db_lock:
                conn = get_db()
                conn.execute("DELETE FROM projects WHERE id = ?", (pid,))
                conn.commit()
                conn.close()
            self._send_json({"ok": True})
            return

        if path == "/api/clients/add":
            with db_lock:
                conn = get_db()
                conn.execute("INSERT INTO clients (name, email, notes) VALUES (?, ?, ?)", (
                    (data.get("name") or "").strip(),
                    (data.get("email") or "").strip(),
                    (data.get("notes") or "").strip(),
                ))
                conn.commit()
                conn.close()
            self._send_json({"ok": True})
            return

        if path == "/api/clients/delete":
            cid = int(data.get("id") or 0)
            with db_lock:
                conn = get_db()
                conn.execute("DELETE FROM clients WHERE id = ?", (cid,))
                conn.commit()
                conn.close()
            self._send_json({"ok": True})
            return

        if path == "/api/tags/add":
            name = (data.get("name") or "").strip()
            if name:
                with db_lock:
                    conn = get_db()
                    conn.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (name,))
                    conn.commit()
                    conn.close()
            self._send_json({"ok": True})
            return

        if path == "/api/tags/delete":
            tid = int(data.get("id") or 0)
            with db_lock:
                conn = get_db()
                conn.execute("DELETE FROM tags WHERE id = ?", (tid,))
                conn.commit()
                conn.close()
            self._send_json({"ok": True})
            return

        if path == "/api/users/add":
            with db_lock:
                conn = get_db()
                conn.execute("INSERT INTO users (name, email, role, hourly_rate) VALUES (?, ?, ?, ?)", (
                    (data.get("name") or "").strip(),
                    (data.get("email") or "").strip(),
                    (data.get("role") or "Membro").strip(),
                    float(data.get("hourly_rate") or 0),
                ))
                conn.commit()
                conn.close()
            self._send_json({"ok": True})
            return

        if path == "/api/autotracker/toggle":
            enabled = bool(data.get("enabled", True))
            val = "1" if enabled else "0"
            with db_lock:
                conn = get_db()
                conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('auto_tracker_enabled', ?)", (val,))
                conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('auto_tracker_confirmed', '1')")
                conn.commit()
                conn.close()

            if not enabled:
                with timer_state.lock:
                    timer_state.current_win_title = ""
                    timer_state.current_win_id = None

            self._send_json({"ok": True, "auto_tracker_enabled": val})
            return

        if path == "/api/autotracker/delete":
            ev_id = int(data.get("event_id") or 0)
            with db_lock:
                conn = get_db()
                conn.execute("DELETE FROM auto_tracker_events WHERE id = ?", (ev_id,))
                conn.commit()
                conn.close()
            self._send_json({"ok": True})
            return

        if path == "/api/autotracker/convert":
            # Converte um evento automatico (ex: janela do AutoCAD) em apontamento oficial de projeto
            ev_id = int(data.get("event_id") or 0)
            project_id = int(data.get("project_id") or 1)
            with db_lock:
                conn = get_db()
                cur = conn.cursor()
                ev = cur.execute("SELECT * FROM auto_tracker_events WHERE id = ?", (ev_id,)).fetchone()
                if ev:
                    u_row = cur.execute("SELECT value FROM settings WHERE key='user_name'").fetchone()
                    user_name = u_row["value"] if u_row else "Projetista"
                    cur.execute("""
                        INSERT INTO time_logs (project_id, user_name, description, tag, billable, source, start_time, end_time, duration_seconds)
                        VALUES (?, ?, ?, 'AutoCAD', 1, 'AUTO_TRACKER', ?, ?, ?)
                    """, (project_id, user_name, ev["window_title"], ev["start_time"], ev["end_time"], ev["duration_seconds"]))
                    cur.execute("DELETE FROM auto_tracker_events WHERE id = ?", (ev_id,))
                    conn.commit()
                conn.close()
            self._send_json({"ok": True})
            return

        self.send_error(404)


def main():
    init_db()
    with db_lock:
        conn = get_db()
        row = conn.execute("SELECT value FROM settings WHERE key='auto_tracker_enabled'").fetchone()
        is_auto_on = (row["value"] == "1") if row else False
        conn.close()

    t = threading.Thread(target=background_worker, daemon=True)
    t.start()

    server = HTTPServer(("0.0.0.0", PORT), ClockifyHandler)
    base_url = f"http://localhost:{PORT}"
    open_url = base_url if is_auto_on else f"{base_url}/#autotracker"
    print("=" * 65)
    print("  CLOCKIFY PRO (PT-BR) - CONTROLE DE HORAS E PROJETOS")
    print(f"  Acesse no navegador: {base_url}")
    print(f"  Auto-Rastreador: {'ATIVO (LIGADO)' if is_auto_on else 'AGUARDANDO START NO PAINEL'}")
    print("=" * 65)

    threading.Timer(1.0, lambda: webbrowser.open(open_url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
