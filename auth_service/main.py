from fastapi import FastAPI, HTTPException, Depends, Query, BackgroundTasks
from fastapi.security import HTTPBearer
import httpx
from typing import List, Optional
import os
from datetime import datetime, date, time, timedelta
import json
import logging
from sqlalchemy import create_engine, Column, String, DateTime, Boolean, Text, Integer, Date, Time, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from sqlalchemy.dialects.postgresql import UUID
import uuid
from pydantic import BaseModel, validator
from enum import Enum
import asyncio

# Configuración
app = FastAPI(title="Appointments Service", version="1.0.0")
security = HTTPBearer()

# Configuración de base de datos
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Enums
class AppointmentStatus(str, Enum):
    scheduled = "scheduled"
    confirmed = "confirmed"
    in_progress = "in_progress"
    completed = "completed"
    cancelled = "cancelled"
    no_show = "no_show"
    rescheduled = "rescheduled"

class Priority(str, Enum):
    low = "low"
    normal = "normal"
    high = "high"
    emergency = "emergency"

# Modelos de base de datos
class Appointment(Base):
    __tablename__ = "appointments"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    client_id = Column(UUID(as_uuid=True), nullable=False)
    pet_id = Column(UUID(as_uuid=True), nullable=False)
    veterinarian_id = Column(UUID(as_uuid=True), nullable=False)
    service_id = Column(UUID(as_uuid=True), nullable=False)
    
    appointment_number = Column(String(20), unique=True)
    scheduled_date = Column(Date, nullable=False)
    scheduled_time = Column(Time, nullable=False)
    estimated_end_time = Column(Time)
    actual_start_time = Column(DateTime)
    actual_end_time = Column(DateTime)
    
    status = Column(String(20), default=AppointmentStatus.scheduled)
    priority = Column(String(20), default=Priority.normal)
    
    reason = Column(Text, nullable=False)
    symptoms = Column(Text)
    observations = Column(Text)
    
    reminder_sent = Column(Boolean, default=False)
    reminder_sent_at = Column(DateTime)
    confirmation_required = Column(Boolean, default=True)
    confirmed_at = Column(DateTime)
    
    follow_up_required = Column(Boolean, default=False)
    follow_up_date = Column(Date)
    follow_up_notes = Column(Text)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    # Relaciones
    history = relationship("AppointmentHistory", back_populates="appointment")

class AppointmentSlot(Base):
    __tablename__ = "appointment_slots"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    veterinarian_id = Column(UUID(as_uuid=True), nullable=False)
    date = Column(Date, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    is_available = Column(Boolean, default=True)
    max_appointments = Column(Integer, default=1)
    current_appointments = Column(Integer, default=0)
    notes = Column(String(200))
    
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)

class AppointmentHistory(Base):
    __tablename__ = "appointment_history"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    appointment_id = Column(UUID(as_uuid=True), ForeignKey('appointments.id'), nullable=False)
    changed_by_user_id = Column(UUID(as_uuid=True), nullable=False)
    change_type = Column(String(20), nullable=False)
    old_values = Column(Text)  # JSON string
    new_values = Column(Text)  # JSON string
    reason = Column(Text)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relaciones
    appointment = relationship("Appointment", back_populates="history")

# Crear tablas
Base.metadata.create_all(bind=engine)

# Dependency para obtener sesión de DB
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Modelos Pydantic
class AppointmentCreate(BaseModel):
    client_id: str
    pet_id: str
    veterinarian_id: str
    service_id: str
    scheduled_date: date
    scheduled_time: time
    reason: str
    symptoms: Optional[str] = None
    priority: Priority = Priority.normal
    confirmation_required: bool = True
    
    @validator('scheduled_date')
    def validate_date(cls, v):
        if v < date.today():
            raise ValueError('No se pueden agendar citas en fechas pasadas')
        return v

class AppointmentUpdate(BaseModel):
    scheduled_date: Optional[date] = None
    scheduled_time: Optional[time] = None
    veterinarian_id: Optional[str] = None
    service_id: Optional[str] = None
    reason: Optional[str] = None
    symptoms: Optional[str] = None
    observations: Optional[str] = None
    status: Optional[AppointmentStatus] = None
    priority: Optional[Priority] = None
    follow_up_required: Optional[bool] = None
    follow_up_date: Optional[date] = None
    follow_up_notes: Optional[str] = None

class AppointmentResponse(BaseModel):
    id: str
    appointment_number: str
    client_id: str
    pet_id: str
    veterinarian_id: str
    service_id: str
    scheduled_date: date
    scheduled_time: time
    estimated_end_time: Optional[time]
    status: str
    priority: str
    reason: str
    symptoms: Optional[str]
    observations: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True

class AvailabilityRequest(BaseModel):
    veterinarian_id: str
    date: date
    duration_minutes: int = 30

class SlotCreate(BaseModel):
    veterinarian_id: str
    date: date
    start_time: time
    end_time: time
    max_appointments: int = 1
    notes: Optional[str] = None

# Verificación de autenticación
async def verify_token(token: str):
    """Verificar token con el servicio de autenticación"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{os.getenv('AUTH_SERVICE_URL')}/verify-token",
                headers={"Authorization": f"Bearer {token}"}
            )
            if response.status_code == 200:
                return response.json()
    except Exception as e:
        logger.error(f"Error verificando token: {e}")
    return None

async def get_current_user(token: str = Depends(security)):
    user = await verify_token(token.credentials)
    if not user:
        raise HTTPException(status_code=401, detail="Token inválido")
    return user

# Funciones auxiliares
async def get_client_info(client_id: str, token: str):
    """Obtener información del cliente"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{os.getenv('CLIENTS_SERVICE_URL')}/clients/{client_id}",
                headers={"Authorization": f"Bearer {token}"}
            )
            if response.status_code == 200:
                return response.json()
    except Exception as e:
        logger.error(f"Error obteniendo cliente: {e}")
    return None

async def get_pet_info(pet_id: str, token: str):
    """Obtener información de la mascota"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{os.getenv('CLIENTS_SERVICE_URL')}/pets/{pet_id}",
                headers={"Authorization": f"Bearer {token}"}
            )
            if response.status_code == 200:
                return response.json()
    except Exception as e:
        logger.error(f"Error obteniendo mascota: {e}")
    return None

async def get_veterinarian_info(vet_id: str, token: str):
    """Obtener información del veterinario"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{os.getenv('EMPLOYEES_SERVICE_URL')}/employees/{vet_id}",
                headers={"Authorization": f"Bearer {token}"}
            )
            if response.status_code == 200:
                return response.json()
    except Exception as e:
        logger.error(f"Error obteniendo veterinario: {e}")
    return None

def generate_appointment_number(date_obj: date, db: Session):
    """Generar número de cita único"""
    year = date_obj.year
    # Buscar última cita del año
    last_appointment = db.query(Appointment).filter(
        Appointment.scheduled_date.between(
            date(year, 1, 1),
            date(year, 12, 31)
        )
    ).order_by(Appointment.appointment_number.desc()).first()
    
    if last_appointment and last_appointment.appointment_number:
        last_number = int(last_appointment.appointment_number[-6:])
        new_number = last_number + 1
    else:
        new_number = 1
    
    return f"{year}{new_number:06d}"

async def check_availability(
    veterinarian_id: str, 
    scheduled_date: date, 
    scheduled_time: time,
    duration_minutes: int,
    db: Session,
    exclude_appointment_id: str = None
):
    """Verificar disponibilidad del veterinario"""
    # Convertir time a datetime para cálculos
    start_datetime = datetime.combine(scheduled_date, scheduled_time)
    end_datetime = start_datetime + timedelta(minutes=duration_minutes)
    
    # Buscar citas del veterinario que se superpongan
    query = db.query(Appointment).filter(
        Appointment.veterinarian_id == veterinarian_id,
        Appointment.scheduled_date == scheduled_date,
        Appointment.status.in_([
            AppointmentStatus.scheduled,
            AppointmentStatus.confirmed,
            AppointmentStatus.in_progress
        ])
    )
    
    if exclude_appointment_id:
        query = query.filter(Appointment.id != exclude_appointment_id)
    
    existing_appointments = query.all()
    
    for apt in existing_appointments:
        existing_start = datetime.combine(scheduled_date, apt.scheduled_time)
        # Asumir duración de 30 minutos si no hay estimated_end_time
        if apt.estimated_end_time:
            existing_end = datetime.combine(scheduled_date, apt.estimated_end_time)
        else:
            existing_end = existing_start + timedelta(minutes=30)
        
        # Verificar superposición
        if not (end_datetime <= existing_start or start_datetime >= existing_end):
            return False
    
    return True

async def send_notification(notification_data: dict, token: str):
    """Enviar notificación al servicio de notificaciones"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{os.getenv('NOTIFICATIONS_SERVICE_URL')}/send",
                json=notification_data,
                headers={"Authorization": f"Bearer {token}"}
            )
            if response.status_code == 200:
                return response.json()
    except Exception as e:
        logger.error(f"Error enviando notificación: {e}")
    return None

# Endpoints
@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "appointments"}

@app.post("/appointments", response_model=AppointmentResponse)
async def create_appointment(
    appointment: AppointmentCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Crear nueva cita"""
    # Verificar disponibilidad
    is_available = await check_availability(
        appointment.veterinarian_id,
        appointment.scheduled_date,
        appointment.scheduled_time,
        30,  # Duración por defecto
        db
    )
    
    if not is_available:
        raise HTTPException(
            status_code=409,
            detail="El veterinario no está disponible en esa fecha y hora"
        )
    
    # Generar número de cita
    appointment_number = generate_appointment_number(appointment.scheduled_date, db)
    
    # Crear cita
    db_appointment = Appointment(
        client_id=appointment.client_id,
        pet_id=appointment.pet_id,
        veterinarian_id=appointment.veterinarian_id,
        service_id=appointment.service_id,
        appointment_number=appointment_number,
        scheduled_date=appointment.scheduled_date,
        scheduled_time=appointment.scheduled_time,
        reason=appointment.reason,
        symptoms=appointment.symptoms,
        priority=appointment.priority,
        confirmation_required=appointment.confirmation_required
    )
    
    db.add(db_appointment)
    db.commit()
    db.refresh(db_appointment)
    
    # Registrar en historial
    history = AppointmentHistory(
        appointment_id=db_appointment.id,
        changed_by_user_id=current_user["id"],
        change_type="created",
        new_values=json.dumps({
            "scheduled_date": str(appointment.scheduled_date),
            "scheduled_time": str(appointment.scheduled_time),
            "veterinarian_id": appointment.veterinarian_id,
            "reason": appointment.reason
        })
    )
    db.add(history)
    db.commit()
    
    # Enviar notificación de confirmación
    background_tasks.add_task(
        send_appointment_notification,
        db_appointment.id,
        "appointment_confirmation",
        f"Bearer {current_user['token']}"
    )
    
    return AppointmentResponse.from_orm(db_appointment)

@app.get("/appointments", response_model=List[AppointmentResponse])
async def get_appointments(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
    client_id: Optional[str] = None,
    veterinarian_id: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    status: Optional[AppointmentStatus] = None,
    limit: int = Query(50, le=100)
):
    """Obtener lista de citas con filtros"""
    query = db.query(Appointment).filter(Appointment.is_active == True)
    
    if client_id:
        query = query.filter(Appointment.client_id == client_id)
    
    if veterinarian_id:
        query = query.filter(Appointment.veterinarian_id == veterinarian_id)
    
    if date_from:
        query = query.filter(Appointment.scheduled_date >= date_from)
    
    if date_to:
        query = query.filter(Appointment.scheduled_date <= date_to)
    
    if status:
        query = query.filter(Appointment.status == status)
    
    appointments = query.order_by(
        Appointment.scheduled_date.desc(),
        Appointment.scheduled_time.desc()
    ).limit(limit).all()
    
    return [AppointmentResponse.from_orm(apt) for apt in appointments]

@app.get("/appointments/{appointment_id}", response_model=AppointmentResponse)
async def get_appointment(
    appointment_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Obtener cita específica"""
    appointment = db.query(Appointment).filter(
        Appointment.id == appointment_id,
        Appointment.is_active == True
    ).first()
    
    if not appointment:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    
    return AppointmentResponse.from_orm(appointment)

@app.put("/appointments/{appointment_id}", response_model=AppointmentResponse)
async def update_appointment(
    appointment_id: str,
    appointment_update: AppointmentUpdate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Actualizar cita"""
    db_appointment = db.query(Appointment).filter(
        Appointment.id == appointment_id,
        Appointment.is_active == True
    ).first()
    
    if not db_appointment:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    
    # Guardar valores anteriores para historial
    old_values = {
        "scheduled_date": str(db_appointment.scheduled_date),
        "scheduled_time": str(db_appointment.scheduled_time),
        "veterinarian_id": str(db_appointment.veterinarian_id),
        "status": db_appointment.status,
        "reason": db_appointment.reason
    }
    
    # Verificar disponibilidad si se cambia fecha/hora/veterinario
    if any([appointment_update.scheduled_date, 
            appointment_update.scheduled_time,
            appointment_update.veterinarian_id]):
        
        new_date = appointment_update.scheduled_date or db_appointment.scheduled_date
        new_time = appointment_update.scheduled_time or db_appointment.scheduled_time
        new_vet = appointment_update.veterinarian_id or db_appointment.veterinarian_id
        
        is_available = await check_availability(
            new_vet,
            new_date,
            new_time,
            30,
            db,
            exclude_appointment_id=appointment_id
        )
        
        if not is_available:
            raise HTTPException(
                status_code=409,
                detail="El veterinario no está disponible en esa fecha y hora"
            )
    
    # Actualizar campos
    update_data = appointment_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_appointment, field, value)
    
    db_appointment.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(db_appointment)
    
    # Registrar en historial
    new_values = {k: str(v) for k, v in update_data.items() if v is not None}
    history = AppointmentHistory(
        appointment_id=db_appointment.id,
        changed_by_user_id=current_user["id"],
        change_type="updated",
        old_values=json.dumps(old_values),
        new_values=json.dumps(new_values)
    )
    db.add(history)
    db.commit()
    
    # Enviar notificación si cambió fecha/hora
    if appointment_update.scheduled_date or appointment_update.scheduled_time:
        background_tasks.add_task(
            send_appointment_notification,
            db_appointment.id,
            "appointment_rescheduled",
            f"Bearer {current_user['token']}"
        )
    
    return AppointmentResponse.from_orm(db_appointment)

@app.delete("/appointments/{appointment_id}")
async def cancel_appointment(
    appointment_id: str,
    reason: str = "Cancelada por usuario",
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Cancelar cita"""
    db_appointment = db.query(Appointment).filter(
        Appointment.id == appointment_id,
        Appointment.is_active == True
    ).first()
    
    if not db_appointment:
        raise HTTPException(status_code=404, detail="Cita no encontrada")
    
    # Actualizar estado
    old_status = db_appointment.status
    db_appointment.status = AppointmentStatus.cancelled
    db_appointment.updated_at = datetime.utcnow()
    db.commit()
    
    # Registrar en historial
    history = AppointmentHistory(
        appointment_id=db_appointment.id,
        changed_by_user_id=current_user["id"],
        change_type="cancelled",
        old_values=json.dumps({"status": old_status}),
        new_values=json.dumps({"status": "cancelled"}),
        reason=reason
    )
    db.add(history)
    db.commit()
    
    # Enviar notificación de cancelación
    background_tasks.add_task(
        send_appointment_notification,
        db_appointment.id,
        "appointment_cancellation",
        f"Bearer {current_user['token']}"
    )
    
    return {"message": "Cita cancelada exitosamente"}

@app.get("/availability")
async def check_availability_endpoint(
    request: AvailabilityRequest = Depends(),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Verificar disponibilidad del veterinario"""
    # Obtener horarios del veterinario
    slots = db.query(AppointmentSlot).filter(
        AppointmentSlot.veterinarian_id == request.veterinarian_id,
        AppointmentSlot.date == request.date,
        AppointmentSlot.is_available == True
    ).all()
    
    available_times = []
    
    for slot in slots:
        # Generar intervalos de tiempo disponibles
        start_time = slot.start_time
        end_time = slot.end_time
        
        current_time = datetime.combine(request.date, start_time)
        slot_end = datetime.combine(request.date, end_time)
        
        while current_time + timedelta(minutes=request.duration_minutes) <= slot_end:
            # Verificar si este tiempo específico está disponible
            is_available = await check_availability(
                request.veterinarian_id,
                request.date,
                current_time.time(),
                request.duration_minutes,
                db
            )
            
            if is_available:
                available_times.append({
                    "time": current_time.time().strftime("%H:%M"),
                    "datetime": current_time.isoformat()
                })
            
            current_time += timedelta(minutes=15)  # Intervalos de 15 minutos
    
    return {
        "date": request.date,
        "veterinarian_id": request.veterinarian_id,
        "available_times": available_times
    }

@app.post("/slots")
async def create_availability_slot(
    slot: SlotCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Crear nuevo horario disponible para veterinario"""
    # Verificar que no existe slot superpuesto
    existing = db.query(AppointmentSlot).filter(
        AppointmentSlot.veterinarian_id == slot.veterinarian_id,
        AppointmentSlot.date == slot.date,
        AppointmentSlot.is_active == True
    ).all()
    
    for existing_slot in existing:
        if not (slot.end_time <= existing_slot.start_time or 
                slot.start_time >= existing_slot.end_time):
            raise HTTPException(
                status_code=409,
                detail="Ya existe un horario que se superpone con este período"
            )
    
    db_slot = AppointmentSlot(
        veterinarian_id=slot.veterinarian_id,
        date=slot.date,
        start_time=slot.start_time,
        end_time=slot.end_time,
        max_appointments=slot.max_appointments,
        notes=slot.notes
    )
    
    db.add(db_slot)
    db.commit()
    db.refresh(db_slot)
    
    return db_slot

@app.get("/today")
async def get_todays_appointments(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Obtener citas de hoy para el dashboard"""
    today = date.today()
    
    appointments = db.query(Appointment).filter(
        Appointment.scheduled_date == today,
        Appointment.status.in_([
            AppointmentStatus.scheduled,
            AppointmentStatus.confirmed,
            AppointmentStatus.in_progress
        ]),
        Appointment.is_active == True
    ).order_by(Appointment.scheduled_time).all()
    
    total_count = len(appointments)
    confirmed_count = len([a for a in appointments if a.status == AppointmentStatus.confirmed])
    pending_count = len([a for a in appointments if a.status == AppointmentStatus.scheduled])
    
    return {
        "date": today,
        "total_appointments": total_count,
        "confirmed": confirmed_count,
        "pending_confirmation": pending_count,
        "appointments": [AppointmentResponse.from_orm(apt) for apt in appointments[:10]]
    }

# Función auxiliar para notificaciones
async def send_appointment_notification(appointment_id: str, template_type: str, token: str):
    """Enviar notificación de cita"""
    try:
        db = SessionLocal()
        appointment = db.query(Appointment).filter(Appointment.id == appointment_id).first()
        if not appointment:
            return
        
        # Obtener información del cliente y mascota
        client_info = await get_client_info(str(appointment.client_id), token)
        pet_info = await get_pet_info(str(appointment.pet_id), token)
        
        if client_info and pet_info:
            notification_data = {
                "template_type": template_type,
                "recipient_type": "client",
                "recipient_id": str(appointment.client_id),
                "recipient_email": client_info.get("email"),
                "recipient_phone": client_info.get("whatsapp") or client_info.get("phone"),
                "variables": {
                    "client_name": client_info.get("full_name"),
                    "pet_name": pet_info.get("name"),
                    "appointment_date": str(appointment.scheduled_date),
                    "appointment_time": str(appointment.scheduled_time),
                    "appointment_number": appointment.appointment_number,
                    "reason": appointment.reason
                },
                "channel": "whatsapp",
                "related_model": "appointment",
                "related_id": str(appointment.id)
            }
            
            await send_notification(notification_data, token)
    except Exception as e:
        logger.error(f"Error enviando notificación de cita: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8003)