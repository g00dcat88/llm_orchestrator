"""Persistent session storage for multi-user conversations and self-learning."""
import json
import sqlite3
import time
from pathlib import Path
from typing import Optional


class SessionStore:
    def __init__(self, db_path: str | Path):
        self.db_path = str(db_path)
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._init_tables()

    def _init_tables(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                scope TEXT,
                tool_calls TEXT,
                created_at REAL DEFAULT (strftime('%s','now'))
            );
            CREATE INDEX IF NOT EXISTS idx_conv_user_session
                ON conversations(user_id, session_id);

            CREATE TABLE IF NOT EXISTS learned_patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                pattern_type TEXT NOT NULL,
                input_prompt TEXT,
                output_response TEXT,
                scope TEXT,
                tools_used TEXT,
                success_rating REAL DEFAULT 1.0,
                created_at REAL DEFAULT (strftime('%s','now'))
            );
            CREATE INDEX IF NOT EXISTS idx_patterns_scope
                ON learned_patterns(scope);

            CREATE TABLE IF NOT EXISTS knowledge_additions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT NOT NULL,
                content TEXT NOT NULL,
                added_by TEXT,
                created_at REAL DEFAULT (strftime('%s','now'))
            );
        """)
        self._conn.commit()

    # ── Conversations ──────────────────────────────────────────────

    def save_message(self, user_id: str, session_id: str, role: str,
                     content: str, scope: str = None, tool_calls: list = None):
        self._conn.execute(
            "INSERT INTO conversations (user_id, session_id, role, content, scope, tool_calls) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, session_id, role, content, scope,
             json.dumps(tool_calls) if tool_calls else None)
        )
        self._conn.commit()

    def get_history(self, user_id: str, session_id: str, limit: int = 20) -> list[dict]:
        rows = self._conn.execute(
            "SELECT role, content, scope, tool_calls, created_at "
            "FROM conversations WHERE user_id=? AND session_id=? "
            "ORDER BY id DESC LIMIT ?",
            (user_id, session_id, limit)
        ).fetchall()
        return [
            {"role": r["role"], "content": r["content"], "scope": r["scope"],
             "tool_calls": json.loads(r["tool_calls"]) if r["tool_calls"] else [],
             "created_at": r["created_at"]}
            for r in reversed(rows)
        ]

    def clear_session(self, user_id: str, session_id: str):
        self._conn.execute(
            "DELETE FROM conversations WHERE user_id=? AND session_id=?",
            (user_id, session_id)
        )
        self._conn.commit()

    # ── Learned patterns ───────────────────────────────────────────

    def save_pattern(self, user_id: str, pattern_type: str, input_prompt: str,
                     output_response: str, scope: str = None,
                     tools_used: list = None, success_rating: float = 1.0):
        self._conn.execute(
            "INSERT INTO learned_patterns "
            "(user_id, pattern_type, input_prompt, output_response, scope, tools_used, success_rating) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (user_id, pattern_type, input_prompt, output_response, scope,
             json.dumps(tools_used) if tools_used else None, success_rating)
        )
        self._conn.commit()

    def get_patterns(self, user_id: str = None, pattern_type: str = None,
                     scope: str = None, limit: int = 50) -> list[dict]:
        query = "SELECT * FROM learned_patterns WHERE 1=1"
        params = []
        if user_id:
            query += " AND user_id=?"
            params.append(user_id)
        if pattern_type:
            query += " AND pattern_type=?"
            params.append(pattern_type)
        if scope:
            query += " AND scope=?"
            params.append(scope)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(query, params).fetchall()
        return [
            {"id": r["id"], "user_id": r["user_id"], "pattern_type": r["pattern_type"],
             "input_prompt": r["input_prompt"], "output_response": r["output_response"],
             "scope": r["scope"],
             "tools_used": json.loads(r["tools_used"]) if r["tools_used"] else [],
             "success_rating": r["success_rating"], "created_at": r["created_at"]}
            for r in rows
        ]

    def update_pattern_rating(self, pattern_id: int, rating: float):
        self._conn.execute(
            "UPDATE learned_patterns SET success_rating=? WHERE id=?",
            (rating, pattern_id)
        )
        self._conn.commit()

    # ── Knowledge additions ────────────────────────────────────────

    def save_knowledge(self, content: str, source: str, added_by: str = None):
        self._conn.execute(
            "INSERT INTO knowledge_additions (source, content, added_by) VALUES (?, ?, ?)",
            (source, content, added_by)
        )
        self._conn.commit()

    def get_knowledge(self, limit: int = 100) -> list[dict]:
        rows = self._conn.execute(
            "SELECT * FROM knowledge_additions ORDER BY id DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [{"id": r["id"], "source": r["source"], "content": r["content"],
                 "added_by": r["added_by"], "created_at": r["created_at"]}
                for r in rows]

    # ── User stats ─────────────────────────────────────────────────

    def get_user_stats(self, user_id: str) -> dict:
        total = self._conn.execute(
            "SELECT COUNT(*) as cnt FROM conversations WHERE user_id=? AND role='user'",
            (user_id,)
        ).fetchone()["cnt"]

        scopes = self._conn.execute(
            "SELECT scope, COUNT(*) as cnt FROM conversations "
            "WHERE user_id=? AND scope IS NOT NULL GROUP BY scope ORDER BY cnt DESC",
            (user_id,)
        ).fetchall()

        tools = self._conn.execute(
            "SELECT tool_calls FROM conversations "
            "WHERE user_id=? AND tool_calls IS NOT NULL",
            (user_id,)
        ).fetchall()
        tool_counter = {}
        for row in tools:
            for t in json.loads(row["tool_calls"]):
                tool_counter[t] = tool_counter.get(t, 0) + 1
        top_tools = sorted(tool_counter.items(), key=lambda x: -x[1])[:10]

        return {
            "total": total,
            "top_scopes": [(r["scope"], r["cnt"]) for r in scopes],
            "top_tools": top_tools,
        }

    def close(self):
        self._conn.close()
