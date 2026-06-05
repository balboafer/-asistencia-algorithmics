from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, date, timedelta
from supabase import create_client, Client
import os
from typing import List, Optional
import asyncio

# Configuración
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

app = FastAPI(title="Asistencia Algorithmics API")

# CORS para React en Vercel
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============= MODELOS =============

class Grupo(BaseModel):
    nombre: str
    hora_inicio: str  # HH:MM
    hora_fin: str     # HH:MM

class Alumno(BaseModel):
    nombre: str
    edad: int
    grupo_id: int
    telefono_padre: str

class MarcarAsistencia(BaseModel):
    alumno_id: int
    grupo_id: int
    presente: bool

class AlertaAusentes(BaseModel):
    grupo_id: int
    fecha: str  # YYYY-MM-DD

# ============= RUTAS =============

@app.get("/")
def root():
    return {"status": "ok", "version": "1.0"}

# --- GRUPOS ---

@app.post("/grupos")
def crear_grupo(grupo: Grupo):
    """Crear un nuevo grupo"""
    try:
        response = supabase.table("grupos").insert({
            "nombre": grupo.nombre,
            "hora_inicio": grupo.hora_inicio,
            "hora_fin": grupo.hora_fin
        }).execute()
        return response.data[0] if response.data else {}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/grupos")
def listar_grupos():
    """Listar todos los grupos"""
    try:
        response = supabase.table("grupos").select("*").execute()
        return response.data
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/grupos/{grupo_id}")
def obtener_grupo(grupo_id: int):
    """Obtener un grupo específico"""
    try:
        response = supabase.table("grupos").select("*").eq("id", grupo_id).execute()
        if not response.data:
            raise HTTPException(status_code=404, detail="Grupo no encontrado")
        return response.data[0]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# --- ALUMNOS ---

@app.post("/alumnos")
def crear_alumno(alumno: Alumno):
    """Crear un nuevo alumno"""
    try:
        response = supabase.table("alumnos").insert({
            "nombre": alumno.nombre,
            "edad": alumno.edad,
            "grupo_id": alumno.grupo_id,
            "telefono_padre": alumno.telefono_padre
        }).execute()
        return response.data[0] if response.data else {}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/alumnos/grupo/{grupo_id}")
def listar_alumnos_grupo(grupo_id: int):
    """Listar alumnos de un grupo"""
    try:
        response = supabase.table("alumnos").select("*").eq("grupo_id", grupo_id).execute()
        return response.data
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/alumnos")
def listar_alumnos():
    """Listar todos los alumnos"""
    try:
        response = supabase.table("alumnos").select("*").execute()
        return response.data
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# --- ASISTENCIA ---

@app.post("/asistencia")
def marcar_asistencia(asistencia: MarcarAsistencia):
    """Marcar asistencia de un alumno"""
    try:
        # Verificar si ya existe registro para hoy
        hoy = date.today().isoformat()
        respuesta_existe = supabase.table("asistencia").select("id").eq(
            "alumno_id", asistencia.alumno_id
        ).eq("grupo_id", asistencia.grupo_id).eq("fecha", hoy).execute()
        
        if respuesta_existe.data:
            # Actualizar
            response = supabase.table("asistencia").update({
                "presente": asistencia.presente,
                "timestamp_marcada": datetime.now().isoformat()
            }).eq("alumno_id", asistencia.alumno_id).eq(
                "grupo_id", asistencia.grupo_id
            ).eq("fecha", hoy).execute()
        else:
            # Insertar nuevo
            response = supabase.table("asistencia").insert({
                "alumno_id": asistencia.alumno_id,
                "grupo_id": asistencia.grupo_id,
                "fecha": hoy,
                "presente": asistencia.presente,
                "timestamp_marcada": datetime.now().isoformat()
            }).execute()
        
        return response.data[0] if response.data else {}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/asistencia/grupo/{grupo_id}/fecha/{fecha}")
def obtener_asistencia_grupo_fecha(grupo_id: int, fecha: str):
    """Obtener asistencia de un grupo en una fecha específica (YYYY-MM-DD)"""
    try:
        # Obtener alumnos del grupo
        alumnos_response = supabase.table("alumnos").select("id, nombre").eq(
            "grupo_id", grupo_id
        ).execute()
        alumnos = {a["id"]: a["nombre"] for a in alumnos_response.data}
        
        # Obtener asistencias registradas
        asistencia_response = supabase.table("asistencia").select(
            "alumno_id, presente, timestamp_marcada"
        ).eq("grupo_id", grupo_id).eq("fecha", fecha).execute()
        
        asistencias = {a["alumno_id"]: a for a in asistencia_response.data}
        
        # Construir resultado
        resultado = []
        for alumno_id, nombre in alumnos.items():
            if alumno_id in asistencias:
                registro = asistencias[alumno_id]
                resultado.append({
                    "alumno_id": alumno_id,
                    "nombre": nombre,
                    "presente": registro["presente"],
                    "timestamp_marcada": registro["timestamp_marcada"]
                })
            else:
                resultado.append({
                    "alumno_id": alumno_id,
                    "nombre": nombre,
                    "presente": None,
                    "timestamp_marcada": None
                })
        
        return resultado
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/ausentes/grupo/{grupo_id}/fecha/{fecha}")
def obtener_ausentes(grupo_id: int, fecha: str):
    """Obtener lista de AUSENTES (no registrados) de un grupo en una fecha"""
    try:
        asistencia_grupo = obtener_asistencia_grupo_fecha(grupo_id, fecha)
        
        # Filtrar solo los que NO han sido marcados (presente = None)
        ausentes = [
            a for a in asistencia_grupo 
            if a["presente"] is None or a["presente"] is False
        ]
        
        return {
            "grupo_id": grupo_id,
            "fecha": fecha,
            "total_alumnos": len(asistencia_grupo),
            "ausentes_count": len(ausentes),
            "ausentes": ausentes
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/historial/{alumno_id}")
def historial_asistencia(alumno_id: int, dias: int = 30):
    """Obtener historial de asistencia de un alumno (últimos N días)"""
    try:
        fecha_limite = (date.today() - timedelta(days=dias)).isoformat()
        response = supabase.table("asistencia").select(
            "fecha, presente, timestamp_marcada"
        ).eq("alumno_id", alumno_id).gte("fecha", fecha_limite).order(
            "fecha", desc=False
        ).execute()
        
        return {
            "alumno_id": alumno_id,
            "dias": dias,
            "registros": response.data
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/alertas/ausentes")
def generar_alerta_ausentes(alerta: AlertaAusentes, background_tasks: BackgroundTasks):
    """
    Generar alerta de ausentes para un grupo en una fecha.
    Aquí irá la integración con Twilio/WhatsApp luego.
    """
    try:
        ausentes_data = obtener_ausentes(alerta.grupo_id, alerta.fecha)
        
        # TODO: Enviar WhatsApp a Fernando + padres
        # background_tasks.add_task(enviar_whatsapp_ausentes, ausentes_data)
        
        return {
            "status": "alerta_generada",
            "data": ausentes_data,
            "timestamp": datetime.now().isoformat(),
            "nota": "Notificaciones WhatsApp pendientes de configurar con Twilio"
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

# Health check para Railway
@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
    }

    
    if __name__ == "__main__":
            import uvicorn
            port = int(os.getenv("PORT", 8000
            uvicorn.run(app, host="0.0.0.0", port=port)}
