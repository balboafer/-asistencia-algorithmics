from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client
from pydantic import BaseModel
from typing import Optional
from datetime import date, timedelta
import os
import smtplib
import httpx
import threading
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

class Alumno(BaseModel):
    nombre: str
    edad: int
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

class Grupo(BaseModel):
    nombre: str
    horario: Optional[str] = None

class Asistencia(BaseModel):
    alumno_id: int
    presente: bool
    fecha: Optional[str] = None


# ---------- Notification functions ----------

def send_telegram(chat_id: str, message: str):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        with httpx.Client(timeout=10) as client:
            resp = client.post(url, json={"chat_id": chat_id, "text": message})
        print(f"Telegram sent: {resp.status_code}")
    except Exception as e:
        print(f"Telegram error: {e}")

def send_whatsapp(to_number: str, message: str):
    try:
        url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"
        with httpx.Client(timeout=10) as client:
            resp = client.post(
                url,
                auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
                data={
                    "From": f"whatsapp:{TWILIO_WHATSAPP_FROM}",
                    "To": f"whatsapp:{to_number}",
                    "Body": message,
                }
            )
        print(f"WhatsApp sent: {resp.status_code} {resp.text[:200]}")
    except Exception as e:
        print(f"WhatsApp error: {e}")

def send_email(to_email: str, subject: str, body: str):
    try:
        msg = MIMEMultipart()
        msg["From"] = SMTP_USER
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as server:
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, to_email, msg.as_string())
        print(f"Email sent to {to_email}")
    except Exception as e:
        print(f"Email error: {e}")

def notify_ausencia(alumno: dict, fecha: str):
    nombre = alumno.get("nombre", "Tu hijo/a")
    mensaje = f"Hola! Te informamos que {nombre} no asistio a su clase de Algorithmics el dia {fecha}. Cualquier duda contactanos."
    subject = f"Falta de {nombre} - Algorithmics"

    telefono = alumno.get("telefono_padre")
    email = alumno.get("email_padre")
    telegram = alumno.get("telegram_chat_id")

    print(f"Notifying ausencia for {nombre}: tel={telefono}, email={email}, tg={telegram}")

    if telefono:
        send_whatsapp(telefono, mensaje)
    if email:
        send_email(email, subject, mensaje)
    if telegram:
        send_telegram(telegram, mensaje)

    print(f"Notifications done for {nombre}")


# ---------- Endpoints ----------

@app.get("/")
def root():
    return {"status": "ok", "service": "Algorithmics Asistencia API"}

@app.get("/grupos")
def get_grupos():
    try:
        resp = supabase.table("grupos").select("*").order("nombre").execute()
        return resp.data
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/grupos")
def crear_grupo(g: Grupo):
    try:
        resp = supabase.table("grupos").insert({"nombre": g.nombre, "horario": g.horario}).execute()
        return resp.data[0]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.delete("/grupos/{grupo_id}")
def eliminar_grupo(grupo_id: int):
    try:
        supabase.table("grupos").delete().eq("id", grupo_id).execute()
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/alumnos")
def get_alumnos():
    try:
        resp = supabase.table("alumnos").select("*").order("nombre").execute()
        return resp.data
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

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
def registrar_asistencia(a: Asistencia, background_tasks: BackgroundTasks):
    try:
        fecha = a.fecha or str(date.today())
        resp = supabase.table("asistencia").upsert({
            "alumno_id": a.alumno_id,
            "presente": a.presente,
            "fecha": fecha,
        }, on_conflict="alumno_id,fecha").execute()

        # Notify if absent â run in background so response is immediate
        if not a.presente:
            alumno_resp = supabase.table("alumnos").select(
                "nombre, telefono_padre, email_padre, telegram_chat_id"
            ).eq("id", a.alumno_id).execute()
            if alumno_resp.data:
                alumno = alumno_resp.data[0]
                background_tasks.add_task(notify_ausencia, alumno, fecha)

        return resp.data[0] if resp.data else {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/asistencia")
def get_asistencia(grupo_id: Optional[int] = None, fecha: Optional[str] = None):
    try:
        query = supabase.table("asistencia").select(
            "*, alumnos(nombre, grupo_id, grupos(nombre))"
        )
        if fecha:
            query = query.eq("fecha", fecha)
        if grupo_id:
            query = query.eq("alumnos.grupo_id", grupo_id)
        resp = query.order("fecha", desc=True).execute()
        return resp.data
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/asistencia/alumno/{alumno_id}")
def historial_alumno(alumno_id: int):
    try:
        resp = supabase.table("asistencia").select("*").eq("alumno_id", alumno_id).order("fecha", desc=True).execute()
        return resp.data
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/asistencia/resumen")
def resumen_asistencia(grupo_id: Optional[int] = None, dias: int = 30):
    try:
        desde = str(date.today() - timedelta(days=dias))
        query = supabase.table("asistencia").select(
            "*, alumnos(nombre, grupo_id)"
        ).gte("fecha", desde)
        resp = query.execute()
        return resp.data
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/test-notify")
def test_notify():
    results = {}
    # WhatsApp test
    try:
        url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"
        with httpx.Client(timeout=15) as client:
            resp = client.post(url, auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN),
                data={"From": f"whatsapp:{TWILIO_WHATSAPP_FROM}",
                      "To": "whatsapp:+525546559905",
                      "Body": "TEST Algorithmics notificacion"})
        results["whatsapp"] = f"{resp.status_code}: {resp.text[:400]}"
    except Exception as e:
        results["whatsapp"] = f"ERROR: {e}"
    # Email test
    try:
        msg = MIMEMultipart()
        msg["From"] = SMTP_USER
        msg["To"] = "balboaf@gmail.com"
        msg["Subject"] = "TEST Algorithmics"
        msg.attach(MIMEText("Prueba de notificacion del sistema de asistencias", "plain"))
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=15) as server:
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, "balboaf@gmail.com", msg.as_string())
        results["email"] = "OK"
    except Exception as e:
        results["email"] = f"ERROR: {e}"
    # Env check
    results["sid_len"] = len(TWILIO_ACCOUNT_SID)
    results["token_len"] = len(TWILIO_AUTH_TOKEN)
    results["smtp_user"] = SMTP_USER
    results["smtp_pass_len"] = len(SMTP_PASSWORD)
    results["from_number"] = TWILIO_WHATSAPP_FROM
    return results
