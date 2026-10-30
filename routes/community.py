"""Public Demands and Discussions with authenticated participation."""
import uuid

from flask import Blueprint, jsonify, request

from db import get_connection
from middleware.auth import require_admin, require_customer

bp = Blueprint("community", __name__)
KINDS = {"demands", "discussions"}
POST_LIMIT = 500
TEXT_LIMIT = 4000


def ensure_tables(client):
    client.execute("""CREATE TABLE IF NOT EXISTS community_posts (
        id TEXT PRIMARY KEY, kind TEXT NOT NULL CHECK(kind IN ('demands','discussions')),
        user_id TEXT NOT NULL, content TEXT NOT NULL, is_pinned INTEGER NOT NULL DEFAULT 0,
        is_hidden INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(user_id) REFERENCES users(id))""")
    client.execute("""CREATE TABLE IF NOT EXISTS community_replies (
        id TEXT PRIMARY KEY, post_id TEXT NOT NULL, user_id TEXT NOT NULL,
        content TEXT NOT NULL, is_hidden INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(post_id) REFERENCES community_posts(id),
        FOREIGN KEY(user_id) REFERENCES users(id))""")
    client.execute("""CREATE TABLE IF NOT EXISTS community_likes (
        user_id TEXT NOT NULL, target_type TEXT NOT NULL CHECK(target_type IN ('post','reply')),
        target_id TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(user_id,target_type,target_id))""")
    client.execute("CREATE INDEX IF NOT EXISTS community_posts_kind_created ON community_posts(kind,is_hidden,created_at)")
    client.execute("CREATE INDEX IF NOT EXISTS community_replies_post_created ON community_replies(post_id,is_hidden,created_at)")


def _valid_kind(kind):
    return kind in KINDS


def _auth_user():
    """Resolve a valid customer JWT to a currently active customer record."""
    import jwt
    from auth.jwt import verify_token
    from flask import g
    if hasattr(g, "community_user_id"):
        return g.community_user_id
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return None
    try:
        claims = verify_token(header[7:].strip())
        if claims.get("role") != "customer":
            return None
        user_id = claims.get("sub")
        with get_connection() as client:
            rows = client.execute("SELECT id FROM users WHERE id=? AND role='customer' AND is_active=1", (user_id,)).rows
        if rows:
            g.community_user_id = user_id
            return user_id
    except Exception:
        return None
    return None


@bp.get("/<kind>/posts")
def list_posts(kind):
    if not _valid_kind(kind):
        return jsonify(success=False, error="Unknown community section"), 404
    try:
        limit = min(max(int(request.args.get("limit", 30)), 1), 100)
        offset = max(int(request.args.get("offset", 0)), 0)
        sort = request.args.get("sort", "newest")
        ordering = "like_count DESC, p.created_at DESC" if sort == "popular" else "p.is_pinned DESC, p.created_at DESC"
        user_id = _auth_user()
        with get_connection() as client:
            ensure_tables(client)
            result = client.execute(f"""SELECT p.id,p.content,p.is_pinned,p.created_at,
                u.display_name AS author,
                (SELECT COUNT(*) FROM community_likes l WHERE l.target_type='post' AND l.target_id=p.id) AS like_count,
                (SELECT COUNT(*) FROM community_replies r WHERE r.post_id=p.id AND r.is_hidden=0) AS reply_count,
                CASE WHEN ? IS NULL THEN 0 ELSE EXISTS(SELECT 1 FROM community_likes l WHERE l.user_id=? AND l.target_type='post' AND l.target_id=p.id) END AS liked
                FROM community_posts p JOIN users u ON u.id=p.user_id
                WHERE p.kind=? AND p.is_hidden=0 ORDER BY {ordering} LIMIT ? OFFSET ?""",
                (user_id,user_id,kind,limit,offset))
            posts = []
            for r in result.rows:
                post = dict(zip(("id","content","pinned","created_at","author","like_count","reply_count","liked"),r))
                post["pinned"] = bool(post["pinned"]); post["liked"] = bool(post["liked"])
                replies = client.execute("""SELECT r.id,r.content,r.created_at,u.display_name,
                    (SELECT COUNT(*) FROM community_likes l WHERE l.target_type='reply' AND l.target_id=r.id),
                    CASE WHEN ? IS NULL THEN 0 ELSE EXISTS(SELECT 1 FROM community_likes l WHERE l.user_id=? AND l.target_type='reply' AND l.target_id=r.id) END
                    FROM community_replies r JOIN users u ON u.id=r.user_id
                    WHERE r.post_id=? AND r.is_hidden=0 ORDER BY r.created_at LIMIT 100""", (user_id,user_id,post["id"]))
                post["replies"] = [dict(zip(("id","content","created_at","author","like_count","liked"),x)) for x in replies.rows]
                for rep in post["replies"]: rep["liked"] = bool(rep["liked"])
                posts.append(post)
        return jsonify(success=True,result=posts,limit=limit,offset=offset)
    except (ValueError, TypeError):
        return jsonify(success=False,error="Invalid pagination"),400
    except Exception:
        return jsonify(success=False,error="Could not load community posts"),503


@bp.post("/<kind>/posts")
@require_customer
def create_post(kind):
    if not _valid_kind(kind): return jsonify(success=False,error="Unknown community section"),404
    data=request.get_json(silent=True) or {}; content=str(data.get("content","")).strip()
    if not content or len(content)>TEXT_LIMIT: return jsonify(success=False,error=f"Post must contain 1 to {TEXT_LIMIT} characters"),400
    user=request.auth.get("sub")
    try:
        post_id=str(uuid.uuid4())
        with get_connection() as client:
            ensure_tables(client)
            recent=client.execute("SELECT COUNT(*) FROM community_posts WHERE user_id=? AND created_at>=datetime('now','-1 minute')",(user,)).rows[0][0]
            if recent>=5:return jsonify(success=False,error="Please wait before posting again"),429
            client.execute("INSERT INTO community_posts(id,kind,user_id,content) VALUES(?,?,?,?)",(post_id,kind,user,content))
        return jsonify(success=True,result={"id":post_id,"content":content}),201
    except Exception:return jsonify(success=False,error="Could not create post"),503


@bp.post("/<kind>/posts/<post_id>/replies")
@require_customer
def create_reply(kind,post_id):
    if not _valid_kind(kind): return jsonify(success=False,error="Unknown community section"),404
    content=str((request.get_json(silent=True) or {}).get("content","")).strip(); user=request.auth.get("sub")
    if not content or len(content)>TEXT_LIMIT:return jsonify(success=False,error=f"Reply must contain 1 to {TEXT_LIMIT} characters"),400
    try:
        reply_id=str(uuid.uuid4())
        with get_connection() as client:
            ensure_tables(client)
            found=client.execute("SELECT id FROM community_posts WHERE id=? AND kind=? AND is_hidden=0",(post_id,kind)).rows
            if not found:return jsonify(success=False,error="Post not found"),404
            recent=client.execute("SELECT COUNT(*) FROM community_replies WHERE user_id=? AND created_at>=datetime('now','-1 minute')",(user,)).rows[0][0]
            if recent>=10:return jsonify(success=False,error="Please wait before replying again"),429
            client.execute("INSERT INTO community_replies(id,post_id,user_id,content) VALUES(?,?,?,?)",(reply_id,post_id,user,content))
            client.execute("UPDATE community_posts SET updated_at=CURRENT_TIMESTAMP WHERE id=?",(post_id,))
        return jsonify(success=True,result={"id":reply_id}),201
    except Exception:return jsonify(success=False,error="Could not create reply"),503


@bp.route("/<kind>/likes/<target_type>/<target_id>",methods=["POST","DELETE"])
@require_customer
def toggle_like(kind,target_type,target_id):
    if not _valid_kind(kind) or target_type not in ("post","reply"):
        return jsonify(success=False,error="Invalid like target"),400
    user=request.auth.get("sub")
    try:
        with get_connection() as client:
            ensure_tables(client)
            if target_type=="post":
                found=client.execute("SELECT id FROM community_posts WHERE id=? AND kind=? AND is_hidden=0",(target_id,kind)).rows
            else:
                found=client.execute("""SELECT r.id FROM community_replies r JOIN community_posts p ON p.id=r.post_id
                    WHERE r.id=? AND p.kind=? AND r.is_hidden=0 AND p.is_hidden=0""",(target_id,kind)).rows
            if not found:return jsonify(success=False,error="Content not found"),404
            if request.method=="POST":
                client.execute("INSERT OR IGNORE INTO community_likes(user_id,target_type,target_id) VALUES(?,?,?)",(user,target_type,target_id))
            else:client.execute("DELETE FROM community_likes WHERE user_id=? AND target_type=? AND target_id=?",(user,target_type,target_id))
            count=client.execute("SELECT COUNT(*) FROM community_likes WHERE target_type=? AND target_id=?",(target_type,target_id)).rows[0][0]
        return jsonify(success=True,result={"liked":request.method=="POST","like_count":count})
    except Exception:return jsonify(success=False,error="Could not update like"),503


@bp.delete("/<kind>/posts/<post_id>")
@require_customer
def delete_own_post(kind,post_id):
    if not _valid_kind(kind): return jsonify(success=False,error="Unknown community section"),404
    try:
        with get_connection() as client:
            ensure_tables(client)
            result=client.execute("UPDATE community_posts SET is_hidden=1,updated_at=CURRENT_TIMESTAMP WHERE id=? AND kind=? AND user_id=? AND is_hidden=0",(post_id,kind,request.auth.get("sub")))
        return (jsonify(success=True),200) if result.rows_affected else (jsonify(success=False,error="Post not found"),404)
    except Exception:return jsonify(success=False,error="Could not delete post"),503


@bp.delete("/<kind>/replies/<reply_id>")
@require_customer
def delete_own_reply(kind,reply_id):
    if not _valid_kind(kind): return jsonify(success=False,error="Unknown community section"),404
    try:
        with get_connection() as client:
            ensure_tables(client)
            result=client.execute("""UPDATE community_replies SET is_hidden=1 WHERE id=? AND user_id=? AND is_hidden=0
                AND post_id IN (SELECT id FROM community_posts WHERE kind=?)""",(reply_id,request.auth.get("sub"),kind))
        return (jsonify(success=True),200) if result.rows_affected else (jsonify(success=False,error="Reply not found"),404)
    except Exception:return jsonify(success=False,error="Could not delete reply"),503


@bp.patch("/admin/<kind>/<content_type>/<content_id>")
@require_admin
def moderate(kind,content_type,content_id):
    if not _valid_kind(kind) or content_type not in ("post","reply"):
        return jsonify(success=False,error="Invalid moderation target"),400
    data=request.get_json(silent=True) or {}; table="community_posts" if content_type=="post" else "community_replies"
    fields=[]; values=[]
    if "hidden" in data: fields.append("is_hidden=?"); values.append(int(bool(data["hidden"])))
    if content_type=="post" and "pinned" in data: fields.append("is_pinned=?"); values.append(int(bool(data["pinned"])))
    if not fields:return jsonify(success=False,error="No moderation changes supplied"),400
    try:
        with get_connection() as client:
            ensure_tables(client)
            where="id=?"; values.append(content_id)
            if content_type=="post":where+=" AND kind=?"; values.append(kind)
            result=client.execute(f"UPDATE {table} SET {','.join(fields)} WHERE {where}",tuple(values))
        return (jsonify(success=True),200) if result.rows_affected else (jsonify(success=False,error="Content not found"),404)
    except Exception:return jsonify(success=False,error="Could not moderate content"),503
