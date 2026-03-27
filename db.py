import sqlite3
from config import DB_PATH


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS seen (
            id TEXT PRIMARY KEY, source TEXT NOT NULL,
            title TEXT, link TEXT,
            posted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS queue (
            id TEXT PRIMARY KEY, source TEXT NOT NULL,
            title TEXT, link TEXT, description TEXT,
            image TEXT, color INTEGER, published TEXT,
            queued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")
    conn.commit()
    conn.close()


def is_seen(post_id):
    conn = sqlite3.connect(DB_PATH)
    r = conn.execute("SELECT 1 FROM seen WHERE id=?", (post_id,)).fetchone()
    conn.close()
    return r is not None


def mark_seen(post_id, source, title, link):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR IGNORE INTO seen (id,source,title,link) VALUES (?,?,?,?)",
                 (post_id, source, title, link))
    conn.commit()
    conn.close()


def count_total_seen():
    conn = sqlite3.connect(DB_PATH)
    n = conn.execute("SELECT COUNT(*) FROM seen").fetchone()[0]
    conn.close()
    return n


def enqueue(post):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""INSERT OR IGNORE INTO queue
        (id,source,title,link,description,image,color,published)
        VALUES (?,?,?,?,?,?,?,?)""",
        (post["id"], post["source"], post["title"], post["link"],
         post.get("description",""), post.get("image",""),
         post.get("color",0), post.get("published","")))
    conn.commit()
    conn.close()


def dequeue():
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("""SELECT id,source,title,link,description,image,color,published
        FROM queue ORDER BY queued_at ASC LIMIT 1""").fetchone()
    if row:
        conn.execute("DELETE FROM queue WHERE id=?", (row[0],))
        conn.commit()
    conn.close()
    if not row:
        return None
    return {"id":row[0],"source":row[1],"title":row[2],"link":row[3],
            "description":row[4],"image":row[5],"color":row[6],"published":row[7]}


def count_queue():
    conn = sqlite3.connect(DB_PATH)
    n = conn.execute("SELECT COUNT(*) FROM queue").fetchone()[0]
    conn.close()
    return n


def is_in_queue(post_id):
    conn = sqlite3.connect(DB_PATH)
    r = conn.execute("SELECT 1 FROM queue WHERE id=?", (post_id,)).fetchone()
    conn.close()
    return r is not None
