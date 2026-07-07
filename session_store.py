"""Persistent session storage for multi-user conversations and self-learning."""
import json
import sqlite3
import time
import re
from pathlib import Path
from typing import Optional


class SessionStore:
    def __init__(self, base_dir: str | Path):
        path = Path(base_dir)
        # If a single .db file path was passed, use its parent dir or "sessions" subdirectory
        if path.suffix == ".db":
            self.base_dir = path.parent / "sessions"
        else:
            self.base_dir = path
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _get_conn(self, user_id: str):
        # Sanitize user_id for safe directory/file names
        safe_user_id = re.sub(r'[^\w\-]', '_', user_id or "anonymous")
        user_dir = self.base_dir / safe_user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        db_path = user_dir / "conversation.db"
        
        conn = sqlite3.connect(str(db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        self._init_tables(conn)
        return conn

    def _init_tables(self, conn):
        conn.executescript("""
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
        conn.commit()

    def _get_all_db_paths(self) -> list[Path]:
        return list(self.base_dir.glob("**/conversation.db"))

    # ── Conversations ──────────────────────────────────────────────

    def save_message(self, user_id: str, session_id: str, role: str,
                     content: str, scope: str = None, tool_calls: list = None):
        conn = self._get_conn(user_id)
        try:
            conn.execute(
                "INSERT INTO conversations (user_id, session_id, role, content, scope, tool_calls) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (user_id, session_id, role, content, scope,
                 json.dumps(tool_calls) if tool_calls else None)
            )
            conn.commit()
        finally:
            conn.close()

    def get_history(self, user_id: str, session_id: str, limit: int = 20) -> list[dict]:
        conn = self._get_conn(user_id)
        try:
            rows = conn.execute(
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
        finally:
            conn.close()

    def clear_session(self, user_id: str, session_id: str):
        conn = self._get_conn(user_id)
        try:
            conn.execute(
                "DELETE FROM conversations WHERE user_id=? AND session_id=?",
                (user_id, session_id)
            )
            conn.commit()
        finally:
            conn.close()

    # ── Learned patterns ───────────────────────────────────────────

    def save_pattern(self, user_id: str, pattern_type: str, input_prompt: str,
                     output_response: str, scope: str = None,
                     tools_used: list = None, success_rating: float = 1.0):
        conn = self._get_conn(user_id)
        try:
            conn.execute(
                "INSERT INTO learned_patterns "
                "(user_id, pattern_type, input_prompt, output_response, scope, tools_used, success_rating) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user_id, pattern_type, input_prompt, output_response, scope,
                 json.dumps(tools_used) if tools_used else None, success_rating)
            )
            conn.commit()
        finally:
            conn.close()

    def get_patterns(self, user_id: str = None, pattern_type: str = None,
                     scope: str = None, limit: int = 50) -> list[dict]:
        if user_id:
            safe_user_id = re.sub(r'[^\w\-]', '_', user_id)
            db_paths = [self.base_dir / safe_user_id / "conversation.db"]
        else:
            db_paths = self._get_all_db_paths()

        all_patterns = []
        for path in db_paths:
            if not path.exists():
                continue
            conn = sqlite3.connect(str(path))
            conn.row_factory = sqlite3.Row
            try:
                self._init_tables(conn)
                query = "SELECT * FROM learned_patterns WHERE 1=1"
                params = []
                if pattern_type:
                    query += " AND pattern_type=?"
                    params.append(pattern_type)
                if scope:
                    query += " AND scope=?"
                    params.append(scope)
                query += " ORDER BY id DESC LIMIT ?"
                params.append(limit)

                rows = conn.execute(query, params).fetchall()
                for r in rows:
                    all_patterns.append({
                        "id": r["id"],
                        "user_id": r["user_id"],
                        "pattern_type": r["pattern_type"],
                        "input_prompt": r["input_prompt"],
                        "output_response": r["output_response"],
                        "scope": r["scope"],
                        "tools_used": json.loads(r["tools_used"]) if r["tools_used"] else [],
                        "success_rating": r["success_rating"],
                        "created_at": r["created_at"]
                    })
            except Exception:
                pass
            finally:
                conn.close()

        # Sort all collected patterns by created_at desc
        all_patterns.sort(key=lambda x: x["created_at"], reverse=True)
        return all_patterns[:limit]

    def update_pattern_rating(self, pattern_id: int, rating: float):
        # Since pattern_id is unique per user database, but we don't know which user database contains it,
        # we update it in all user databases where it exists!
        db_paths = self._get_all_db_paths()
        for path in db_paths:
            if not path.exists():
                continue
            conn = sqlite3.connect(str(path))
            try:
                conn.execute(
                    "UPDATE learned_patterns SET success_rating=? WHERE id=?",
                    (rating, pattern_id)
                )
                conn.commit()
            except Exception:
                pass
            finally:
                conn.close()

    # ── Knowledge additions ────────────────────────────────────────

    def save_knowledge(self, content: str, source: str, added_by: str = None):
        conn = self._get_conn(added_by or "anonymous")
        try:
            conn.execute(
                "INSERT INTO knowledge_additions (source, content, added_by) VALUES (?, ?, ?)",
                (source, content, added_by)
            )
            conn.commit()
        finally:
            conn.close()

    def get_knowledge(self, limit: int = 100) -> list[dict]:
        db_paths = self._get_all_db_paths()
        all_knowledge = []
        for path in db_paths:
            if not path.exists():
                continue
            conn = sqlite3.connect(str(path))
            conn.row_factory = sqlite3.Row
            try:
                self._init_tables(conn)
                rows = conn.execute(
                    "SELECT * FROM knowledge_additions ORDER BY id DESC LIMIT ?",
                    (limit,)
                ).fetchall()
                for r in rows:
                    all_knowledge.append({
                        "id": r["id"],
                        "source": r["source"],
                        "content": r["content"],
                        "added_by": r["added_by"],
                        "created_at": r["created_at"]
                    })
            except Exception:
                pass
            finally:
                conn.close()
        all_knowledge.sort(key=lambda x: x["created_at"], reverse=True)
        return all_knowledge[:limit]

    # ── User stats ─────────────────────────────────────────────────

    def get_user_stats(self, user_id: str) -> dict:
        conn = self._get_conn(user_id)
        try:
            total = conn.execute(
                "SELECT COUNT(*) as cnt FROM conversations WHERE user_id=? AND role='user'",
                (user_id,)
            ).fetchone()["cnt"]

            scopes = conn.execute(
                "SELECT scope, COUNT(*) as cnt FROM conversations "
                "WHERE user_id=? AND scope IS NOT NULL GROUP BY scope ORDER BY cnt DESC",
                (user_id,)
            ).fetchall()

            tools = conn.execute(
                "SELECT tool_calls FROM conversations "
                "WHERE user_id=? AND tool_calls IS NOT NULL",
                (user_id,)
            ).fetchall()
            tool_counter = {}
            for row in tools:
                if row["tool_calls"]:
                    for t in json.loads(row["tool_calls"]):
                        tool_counter[t] = tool_counter.get(t, 0) + 1
            top_tools = sorted(tool_counter.items(), key=lambda x: -x[1])[:10]

            return {
                "total": total,
                "top_scopes": [(r["scope"], r["cnt"]) for r in scopes],
                "top_tools": top_tools,
            }
        finally:
            conn.close()

    def close(self):
        pass
