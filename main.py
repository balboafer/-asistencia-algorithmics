from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client
from pydantic import BaseModel
from typing import Optional
from datetime import date, timedelta
import os
import smtplib
import httpx
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Notification credentials
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_FROM = os.environ.get("TWILIO_WHATSAPP_FROM", "")
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")


# ---------- Models ----------

class Grupo(BaseModel):
    nombre: str
    hora_inicio: str
    hora_fin: str

class Alumno(BaseModel):
    nombre: str
    edad: Optional[int] = None
    grupo_id: int
    telefono_padre: Optional[str] = None
    email_padre: Optional[str] = None
    telegram_chat_id: Optional[str] = None

class AlumnoUpdate(BaseModel):
    nombre: Optional[str] = None
    edad: Optional[int] = None
    grupo_id: Optional[int] = None
    telefono_padre: Optional[str] = None
    email_padre: Optional[str] = None
    telegram_chat_id: Optional[str] = None

class Asistencia(BaseModel):
    alumno_id: int
    presente: bool
    fecha: str


# ---------- Notification helpers ----------

def send_telegram(chat_id: str, message: str):
    if not TELEGRAM_BOT_TOKEN or not chat_id:
        return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        httpx.post(url, json={"chat_id": chat_id, "text": message}, timeout=5)
    except Exception as e:
        print(f"Telegram error: {e}")

def send_whatsapp(to_number: str, message: str):
    if not TWILIO_ACCOUNT_SID or not TWILIO_AUTH_TOKEN or not TWILIO_WHATSAPP_FROM or not to_number:
        return
    try:
        url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"
        httpx.post(
            url,
            auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
            data={
                "From": f"whatsapp:{TWILIO_WHATSAPP_FROM}",
                "To": f"whatsapp:{to_number}",
                "Body": message,
            },
            timeout=5,
        )
    except Exception as e:
        print(f"WhatsApp error: {e}")

def send_email(to_email: str, subject: str, body: str):
    if not SMTP_USER or not SMTP_PASSWORD or not to_email:
        return
    try:
        msg = MIMEMultipart()
        msg["From"] = SMTP_USER
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, to_email, msg.as_string())
    except Exception as e:
        print(f"Email error: {e}")

def notify_ausencia(alumno: dict, fecha: str):
    nombre = alumno.get("nombre", "Tu hijo/a")
    mensaje = f"Hola! Te informamos que {nombre} no asistio a su clase de Algorithmics el dia {fecha}. Cualquier duda contactanos."
    subject = f"Falta de {nombre} - Algorithmics"

    telefono = alumno.get("telefono_padre")
    email = alumno.get("email_padre")
    telegram = alumno.get("telegram_chat_id")

    if telefono:
        send_whatsapp(telefono, mensaje)
    if email:
        send_email(email, subject, mensaje)
    if telegram:
        send_telegram(telegram, mensaje)


# ---------- Endpoints ----------

@app.get("/")
def root():
    return {"status": "ok", "service": "Algorithmics Asistencia API"}

@app.get("/health")
def health():
    return {"status": "healthy"}

# Grupos
@app.post("/grupos")
def crear_grupo(g: Grupo):
    try:
        resp = supabase.table("grupos").insert({
            "nombre": g.nombre,
            "hora_inicio": g.hora_inicio,
            "hora_fin": g.hora_fin
        }).execute()
        return resp.data[0]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/grupos")
def listar_grupos():
    try:
        resp = supabase.table("grupos").select("*").order("nombre").execute()
        return resp.data
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/grupos/{grupo_id}")
def obtener_grupo(grupo_id: int):
    try:
        resp = supabase.table("grupos").select("*").eq("id", grupo_id).execute()
        if not resp.data:
            raise HTTPException(status_code=404, detail="Grupo no encontrado")
        return resp.data[0]
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.delete("/grupos/{grupo_id}")
def eliminar_grupo(grupo_id: int):
    try:
        supabase.table("grupos").delete().eq("id", grupo_id).execute()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# Alumnos
@app.post("/alumnos")
def crear_alumno(a: Alumno):
    try:
        resp = supabase.table("alumnos").insert({
            "nombre": a.nombre,
            "edad": a.edad,
            "grupo_id": a.grupo_id,
            "telefono_padre": a.telefono_padre,
            "email_padre": a.email_padre,
            "telegram_chat_id": a.telegram_chat_id,
        }).execute()
        return resp.data[0]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/alumnos")
def listar_alumnos():
    try:
        resp = supabase.table("alumnos").select("*").order("nombre").execute()
        return resp.data
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/alumnos/grupo/{grupo_id}")
def alumnos_por_grupo(grupo_id: int):
    try:
        resp = supabase.table("alumnos").select("*").eq("grupo_id", grupo_id).order("nombre").execute()
        return resp.data
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.delete("/alumnos/{alumno_id}")
def eliminar_alumno(alumno_id: int):
    try:
        supabase.table("alumnos").delete().eq("id", alumno_id).execute()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.put("/alumnos/{alumno_id}")
def actualizar_alumno(alumno_id: int, a: AlumnoUpdate):
    try:
        data = {k: v for k, v in a.dict().items() if v is not None}
        resp = supabase.table("alumnos").update(data).eq("id", alumno_id).execute()
        return resp.data[0]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# Asistencia
@app.post("/asistencia")
def registrar_asistencia(a: Asistencia):
    try:
        resp = supabase.table("asistencia").upsert({
            "alumno_id": a.alumno_id,
            "presente": a.presente,
            "fecha": a.fecha,
        }, on_conflict="alumno_id,fecha").execute()

        # Notify if absent
        if not a.presente:
            alumno_resp = supabase.table("alumnos").select(
                "nombre, telefono_padre, email_padre, telegram_chat_id"
            ).eq("id", a.alumno_id).execute()
            if alumno_resp.data:
                notify_ausencia(alumno_resp.data[0], a.fecha)

        return resp.data[0]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/asistencia/grupo/{grupo_id}/fecha/{fecha}")
def asistencia_grupo_fecha(grupo_id: int, fecha: str):
    try:
        alumnos_resp = supabase.table("alumnos").select("id").eq("grupo_id", grupo_id).execute()
        ids = [a["id"] for a in alumnos_resp.data]
        if not ids:
            return []
        resp = supabase.table("asistencia").select("*").in_("alumno_id", ids).eq("fecha", fecha).execute()
        return resp.data
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/ausentes/grupo/{grupo_id}/fecha/{fecha}")
def ausentes_grupo_fecha(grupo_id: int, fecha: str):
    try:
        alumnos_resp = supabase.table("alumnos").select("id, nombre").eq("grupo_id", grupo_id).execute()
        ids = [a["id"] for a in alumnos_resp.data]
        if not ids:
            return []
        asist_resp = supabase.table("asistencia").select("alumno_id").in_("alumno_id", ids).eq("fecha", fecha).eq("presente", False).execute()
        ausentes_ids = {r["alumno_id"] for r in asist_resp.data}
        return [a for a in alumnos_resp.data if a["id"] in ausentes_ids]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/historial/{alumno_id}")
def historial_alumno(alumno_id: int, dias: int = 30):
    try:
        fecha_limite = (date.today() - timedelta(days=dias)).isoformat()
        resp = supabase.table("asistencia").select("*").eq("alumno_id", alumno_id).gte("fecha", fecha_limite).order("fecha", desc=True).execute()
        return resp.data
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/asistencia/historial/grupo/{grupo_id}")
def historial_grupo(grupo_id: int, dias: int = 30):
    try:
        fecha_limite = (date.today() - timedelta(days=dias)).isoformat()
        alumnos_resp = supabase.table("alumnos").select("id, nombre").eq("grupo_id", grupo_id).execute()
        alumnos = {a["id"]: a["nombre"] for a in alumnos_resp.data}
        if not alumnos:
            return []
        asist_resp = supabase.table("asistencia").select(
            "alumno_id, presente, fecha"
        ).in_("alumno_id", list(alumnos.keys())).gte("fecha", fecha_limite).order("fecha", desc=True).execute()
        by_date = {}
        for r in asist_resp.data:
            d = r["fecha"]
            if d not in by_date:
                by_date[d] = {"presentes": [], "ausentes": []}
            nombre = alumnos.get(r["alumno_id"], "?")
            if r["presente"]:
                by_date[d]["presentes"].append(nombre)
            else:
                by_date[d]["ausentes"].append(nombre)
        result = [{"fecha": k, **v} for k, v in sorted(by_date.items(), reverse=True)]
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/alertas/ausentes")
def alertar_ausentes(data: dict):
    try:
        grupo_id = data.get("grupo_id")
        fecha = data.get("fecha")
        if not grupo_id or not fecha:
            raise HTTPException(status_code=400, detail="grupo_id y fecha requeridos")
        alumnos_resp = supabase.table("alumnos").select(
            "id, nombre, telefono_padre, email_padre, telegram_chat_id"
        ).eq("grupo_id", grupo_id).execute()
        alumnos = {a["id"]: a for a in alumnos_resp.data}
        asist_resp = supabase.table("asistencia").select("alumno_id, presente").in_(
            "alumno_id", list(alumnos.keys())
        ).eq("fecha", fecha).execute()
        for r in asist_resp.data:
            if not r["presente"]:
                notify_ausencia(alumnos[r["alumno_id"]], fecha)
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
