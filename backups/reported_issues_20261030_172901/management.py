"""Admin management APIs for memberships and event campaigns."""
import json,re,uuid
from datetime import date,datetime,timedelta,timezone
from flask import Blueprint,jsonify,request
from db import get_connection
from middleware.auth import require_admin
from routes.memberships import ensure_tables as ensure_memberships
from routes.campaigns import ensure_campaign_table,_dates
from services.festival_service import ensure_festival_tables
from services.object_storage import StorageNotConfigured,upload,public_url,private_url

bp=Blueprint("management",__name__)

def fail(msg,status=500):return jsonify(success=False,error=msg),status
def rows(c,sql,args=()):return c.execute(sql,args).rows
def slugify(value):
    value=re.sub(r"[^a-z0-9]+","-",str(value or "").lower()).strip("-")[:80]
    return value or uuid.uuid4().hex[:12]

@bp.get("/membership-plans")
@require_admin
def get_plans():
    try:
        with get_connection() as c:ensure_memberships(c);data=c.execute("SELECT plan_key,name,price_paise,duration_days,benefits_json,is_active,updated_at FROM membership_plans ORDER BY plan_key").rows
        result=[]
        for r in data:
            try:b=json.loads(r[4] or "[]")
            except ValueError:b=[]
            result.append({"plan_key":r[0],"name":r[1],"price_paise":r[2],"duration_days":r[3],"benefits":b,"is_active":bool(r[5]),"updated_at":r[6]})
        return jsonify(success=True,result=result)
    except Exception:return fail("Could not load membership plans",503)

@bp.put("/membership-plans/<plan_key>")
@require_admin
def save_plan(plan_key):
    if plan_key not in {"basic","plus","premium"}:return fail("Unknown membership plan",404)
    expected_name={"basic":"Basic","plus":"Plus","premium":"Premium"}[plan_key]
    data=request.get_json(silent=True) or {};name=str(data.get("name",expected_name)).strip();benefits=data.get("benefits",[])
    if name!=expected_name or not isinstance(benefits,list) or len(benefits)>30 or any(not isinstance(x,str) or len(x)>240 for x in benefits):return fail("Keep the agreed plan name and provide a list of benefits",400)
    price=data.get("price_paise");duration=data.get("duration_days")
    try:
        if plan_key=="basic":price=0;duration=None
        else:
            price=int(price);duration=int(duration)
            if price<=0 or price>100000000 or duration<1 or duration>3650:raise ValueError
    except (TypeError,ValueError):return fail("Paid plans need a configured price in paise and duration in days",400)
    try:
        with get_connection() as c:
            ensure_memberships(c)
            c.execute("UPDATE membership_plans SET name=?,price_paise=?,duration_days=?,benefits_json=?,is_active=?,updated_at=CURRENT_TIMESTAMP WHERE plan_key=?",
                (name,price,duration,json.dumps(benefits,ensure_ascii=False),int(bool(data.get("is_active",True))),plan_key))
            result=c.execute("SELECT plan_key,name,price_paise,duration_days,benefits_json,is_active,updated_at FROM membership_plans WHERE plan_key=?",(plan_key,)).rows[0]
        return jsonify(success=True,result={"plan_key":result[0],"name":result[1],"price_paise":result[2],"duration_days":result[3],"benefits":json.loads(result[4]),"is_active":bool(result[5]),"updated_at":result[6]})
    except Exception:return fail("Could not save membership plan",503)

@bp.get("/membership-applications")
@require_admin
def list_applications():
    query=str(request.args.get("q","")).strip()
    try:
        with get_connection() as c:
            ensure_memberships(c)
            sql="""SELECT a.membership_id,a.customer_id,u.display_name,u.email,a.plan_key,p.name,a.amount_paise,a.duration_days,
                a.transaction_reference,a.status,a.applied_at,a.reviewed_by,a.reviewed_at,a.activated_at,a.expires_at,a.rejection_reason,
                CASE WHEN a.screenshot_key IS NULL THEN 0 ELSE 1 END
                FROM membership_applications a JOIN users u ON u.id=a.customer_id JOIN membership_plans p ON p.plan_key=a.plan_key"""
            data=c.execute(sql+ (" WHERE a.membership_id=? OR a.customer_id=?" if query else "") + " ORDER BY a.applied_at DESC LIMIT 200",(query,query) if query else ()).rows
        keys=("membership_id","customer_id","display_name","email","plan_key","plan_name","amount_paise","duration_days","transaction_reference","status","applied_at","reviewed_by","reviewed_at","activated_at","expires_at","rejection_reason","has_screenshot")
        return jsonify(success=True,result=[dict(zip(keys,r)) for r in data])
    except Exception:return fail("Could not load membership applications",503)

@bp.get("/membership-applications/<membership_id>/screenshot")
@require_admin
def application_screenshot(membership_id):
    try:
        with get_connection() as c:ensure_memberships(c);r=c.execute("SELECT screenshot_key FROM membership_applications WHERE membership_id=?",(membership_id,)).rows
        if not r or not r[0][0]:return fail("Receipt not found",404)
        return jsonify(success=True,result={"url":private_url(r[0][0],expires=300),"expires_in":300})
    except StorageNotConfigured as exc:return fail(str(exc),503)
    except Exception:return fail("Could not load payment receipt",503)

@bp.get("/membership-applications/<membership_id>/history")
@require_admin
def application_history(membership_id):
    try:
        with get_connection() as c:
            ensure_memberships(c)
            data=c.execute("SELECT actor_id,action,note,created_at FROM membership_events WHERE membership_id=? ORDER BY created_at,id",(membership_id,)).rows
        return jsonify(success=True,result=[dict(zip(("actor_id","action","note","created_at"),r)) for r in data])
    except Exception:return fail("Could not load membership history",503)

def _review_application(membership_id,action,note=""):
    admin=request.auth["sub"];now=datetime.now(timezone.utc)
    with get_connection() as c:
        ensure_memberships(c)
        app=c.execute("SELECT customer_id,plan_key,duration_days,status FROM membership_applications WHERE membership_id=?",(membership_id,)).rows
        if not app:return fail("Membership application not found",404)
        customer,plan,duration,status=app[0]
        if status!="pending":return fail("Only pending applications can be reviewed",409)
        if action=="approve":
            if plan!="basic" and not duration:return fail("Configure this plan duration before approval",409)
            from routes.memberships import _expire_customer
            _expire_customer(c,customer)
            latest=c.execute("SELECT expires_at FROM membership_applications WHERE customer_id=? AND status='approved' AND expires_at IS NOT NULL ORDER BY expires_at DESC LIMIT 1",(customer,)).rows
            base=now
            if latest and latest[0][0]:
                try:old=datetime.fromisoformat(latest[0][0].replace("Z","+00:00"))
                except ValueError:old=now
                if old>now:base=old
            expiry=(base+timedelta(days=int(duration))).isoformat(timespec="seconds").replace("+00:00","Z") if duration else None
            start=base.isoformat(timespec="seconds").replace("+00:00","Z")
            res=c.execute("UPDATE membership_applications SET status='approved',reviewed_by=?,reviewed_at=CURRENT_TIMESTAMP,activated_at=?,expires_at=? WHERE membership_id=? AND status='pending'",(admin,start,expiry,membership_id))
            if not res.rows_affected:return fail("Application was already reviewed",409)
            c.execute("INSERT INTO membership_events(id,membership_id,actor_id,action,note) VALUES(?,?,?,'approved',?)",(str(uuid.uuid4()),membership_id,admin,note or "Payment confirmed by admin"))
        else:
            if not note.strip():return fail("Provide a reason for rejection",400)
            res=c.execute("UPDATE membership_applications SET status='rejected',reviewed_by=?,reviewed_at=CURRENT_TIMESTAMP,rejection_reason=? WHERE membership_id=? AND status='pending'",(admin,note[:500],membership_id))
            if not res.rows_affected:return fail("Application was already reviewed",409)
            c.execute("INSERT INTO membership_events(id,membership_id,actor_id,action,note) VALUES(?,?,?,'rejected',?)",(str(uuid.uuid4()),membership_id,admin,note[:500]))
    return jsonify(success=True,result={"membership_id":membership_id,"status":"approved" if action=="approve" else "rejected"})

@bp.post("/membership-applications/<membership_id>/approve")
@require_admin
def approve_application(membership_id):
    data=request.get_json(silent=True) or {};return _review_application(membership_id,"approve",str(data.get("note", "")))

@bp.post("/membership-applications/<membership_id>/reject")
@require_admin
def reject_application(membership_id):
    data=request.get_json(silent=True) or {};return _review_application(membership_id,"reject",str(data.get("reason", "")))

def _campaigns(c):
    ensure_campaign_table(c)
    r=c.execute("SELECT slug,name,campaign_title,banner_image_url,theme_color,start_date,end_date,enabled,archived,recurring_yearly,created_at,updated_at FROM event_campaigns ORDER BY created_at DESC").rows
    keys=("slug","name","campaign_title","banner_image_url","theme_color","start_date","end_date","enabled","archived","recurring_yearly","created_at","updated_at")
    return [dict(zip(keys,x))|{"enabled":bool(x[7]),"archived":bool(x[8]),"recurring_yearly":bool(x[9])} for x in r]

def _valid_campaign(data):
    name=str(data.get("name","")).strip();title=str(data.get("campaign_title","")).strip();color=str(data.get("theme_color","#4729a8"))
    start=str(data.get("start_date",""));end=str(data.get("end_date",""))
    if not name or len(name)>100 or not title or len(title)>160 or not re.fullmatch(r"#[0-9a-fA-F]{6}",color):raise ValueError("Enter a name, title and six-digit hex theme color")
    s=date.fromisoformat(start);e=date.fromisoformat(end)
    if e<s:raise ValueError("End date must be on or after the start date")
    return name,title,color,s,e

def _check_overlap(c,slug,s,e,recurring,enabled):
    if not enabled:return
    today=date.today()
    for old in _campaigns(c):
        if old["slug"]==slug or old["archived"] or not old["enabled"]:continue
        os_,oe=_dates(old,today)
        if s<=oe and os_<=e:raise ValueError("Active campaign dates overlap with "+old["name"])
    ensure_festival_tables(c)
    scheduler=c.execute("SELECT enabled FROM festival_scheduler_settings WHERE id=1").rows
    if scheduler and scheduler[0][0]:
        for row in c.execute("SELECT slug,name,reference_sale_date,campaign_end_date FROM festival_campaigns WHERE enabled=1").rows:
            fs=date.fromisoformat(row[2])-timedelta(days=1) if row[2] else None;fe=date.fromisoformat(row[3]) if row[3] else None
            if fs and fe and s<=fe and fs<=e:raise ValueError("Dates overlap with the existing "+row[1]+" festival sale")

@bp.get("/campaigns")
@require_admin
def list_campaigns():
    try:
        with get_connection() as c:data=_campaigns(c)
        return jsonify(success=True,result=data)
    except Exception:return fail("Could not load campaigns",503)

@bp.post("/campaigns")
@require_admin
def create_campaign():
    data=request.get_json(silent=True) or {}
    try:name,title,color,s,e=_valid_campaign(data)
    except (ValueError,TypeError) as exc:return fail(str(exc),400)
    slug=slugify(data.get("slug") or name);enabled=bool(data.get("enabled",False));recurring=bool(data.get("recurring_yearly",False))
    try:
        with get_connection() as c:
            ensure_campaign_table(c);_check_overlap(c,slug,s,e,recurring,enabled)
            c.execute("INSERT INTO event_campaigns(slug,name,campaign_title,theme_color,start_date,end_date,enabled,recurring_yearly) VALUES(?,?,?,?,?,?,?,?)",(slug,name,title,color,s.isoformat(),e.isoformat(),int(enabled),int(recurring)))
        return jsonify(success=True,result={"slug":slug,"name":name,"campaign_title":title,"start_date":s.isoformat(),"end_date":e.isoformat(),"enabled":enabled,"recurring_yearly":recurring}),201
    except ValueError as exc:return fail(str(exc),409)
    except Exception as exc:
        if "UNIQUE" in str(exc).upper():return fail("A campaign with this slug already exists",409)
        return fail("Could not create campaign",503)

@bp.put("/campaigns/<slug>")
@require_admin
def update_campaign(slug):
    data=request.get_json(silent=True) or {}
    try:name,title,color,s,e=_valid_campaign(data)
    except (ValueError,TypeError) as exc:return fail(str(exc),400)
    enabled=bool(data.get("enabled",False));recurring=bool(data.get("recurring_yearly",False))
    try:
        with get_connection() as c:
            ensure_campaign_table(c)
            old=c.execute("SELECT banner_image_url,archived FROM event_campaigns WHERE slug=?",(slug,)).rows
            if not old:return fail("Campaign not found",404)
            if old[0][1]:return fail("Archived campaigns are read-only",409)
            _check_overlap(c,slug,s,e,recurring,enabled)
            c.execute("UPDATE event_campaigns SET name=?,campaign_title=?,theme_color=?,start_date=?,end_date=?,enabled=?,recurring_yearly=?,updated_at=CURRENT_TIMESTAMP WHERE slug=?",(name,title,color,s.isoformat(),e.isoformat(),int(enabled),int(recurring),slug))
        return jsonify(success=True,result={"slug":slug,"name":name,"campaign_title":title,"banner_image_url":old[0][0],"theme_color":color,"start_date":s.isoformat(),"end_date":e.isoformat(),"enabled":enabled,"archived":False,"recurring_yearly":recurring})
    except ValueError as exc:return fail(str(exc),409)
    except Exception:return fail("Could not update campaign",503)

@bp.post("/campaigns/<slug>/banner")
@require_admin
def upload_campaign_banner(slug):
    image=request.files.get("image")
    if not image:return fail("Choose a banner image",400)
    try:
        with get_connection() as c:
            ensure_campaign_table(c)
            if not c.execute("SELECT 1 FROM event_campaigns WHERE slug=? AND archived=0",(slug,)).rows:return fail("Campaign not found",404)
        if not __import__("os").getenv("OBJECT_STORAGE_PUBLIC_BASE_URL","").strip():
            raise StorageNotConfigured("Set OBJECT_STORAGE_PUBLIC_BASE_URL to enable public campaign banners")
        key=upload(image,prefix="campaign-banners",private=False,max_bytes=5*1024*1024);url=public_url(key)
        with get_connection() as c:
            ensure_campaign_table(c);res=c.execute("UPDATE event_campaigns SET banner_image_url=?,updated_at=CURRENT_TIMESTAMP WHERE slug=? AND archived=0",(url,slug))
        if not res.rows_affected:return fail("Campaign not found",404)
        return jsonify(success=True,result={"banner_image_url":url})
    except ValueError as exc:return fail(str(exc),400)
    except StorageNotConfigured as exc:return fail(str(exc),503)
    except Exception:return fail("Could not upload banner image",503)

@bp.post("/campaigns/<slug>/archive")
@require_admin
def archive_campaign(slug):
    try:
        with get_connection() as c:ensure_campaign_table(c);res=c.execute("UPDATE event_campaigns SET archived=1,enabled=0,updated_at=CURRENT_TIMESTAMP WHERE slug=? AND archived=0",(slug,))
        return (jsonify(success=True),200) if res.rows_affected else fail("Campaign not found",404)
    except Exception:return fail("Could not archive campaign",503)
