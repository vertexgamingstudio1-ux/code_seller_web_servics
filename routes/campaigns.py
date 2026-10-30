from datetime import date, datetime
from flask import Blueprint, jsonify
from zoneinfo import ZoneInfo
from db import get_connection

bp=Blueprint("campaigns",__name__)

def ensure_campaign_table(c):
    c.execute("""CREATE TABLE IF NOT EXISTS event_campaigns (
        slug TEXT PRIMARY KEY,name TEXT NOT NULL,campaign_title TEXT NOT NULL,
        banner_image_url TEXT,theme_color TEXT NOT NULL DEFAULT '#4729a8',
        start_date TEXT NOT NULL,end_date TEXT NOT NULL,enabled INTEGER NOT NULL DEFAULT 0,
        archived INTEGER NOT NULL DEFAULT 0,recurring_yearly INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")

def _dates(campaign,today):
    start=date.fromisoformat(campaign["start_date"]);end=date.fromisoformat(campaign["end_date"])
    if campaign["recurring_yearly"]:
        try:start=start.replace(year=today.year);end=end.replace(year=today.year)
        except ValueError:
            start=start.replace(year=today.year,day=28);end=end.replace(year=today.year,day=28)
        if end<start:end=end.replace(year=end.year+1)
    return start,end

@bp.get("/active")
def active_campaign():
    try:
        today=datetime.now(ZoneInfo("Asia/Kolkata")).date()
        with get_connection() as c:
            ensure_campaign_table(c)
            rows=c.execute("SELECT slug,name,campaign_title,banner_image_url,theme_color,start_date,end_date,recurring_yearly FROM event_campaigns WHERE enabled=1 AND archived=0 ORDER BY created_at DESC").rows
        active=[]
        for r in rows:
            item=dict(zip(("slug","name","campaign_title","banner_image_url","theme_color","start_date","end_date","recurring_yearly"),r))
            item["recurring_yearly"]=bool(item["recurring_yearly"])
            start,end=_dates(item,today)
            if start<=today<=end:active.append(item)
        if len(active)>1:return jsonify(success=False,error="Multiple active campaign windows overlap; admin correction required"),503
        return jsonify(success=True,result=active[0] if active else None)
    except Exception:return jsonify(success=False,error="Could not load active campaign"),503
