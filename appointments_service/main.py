from fastapi import FastAPI, HTTPException, Depends, BackgroundTasks
from fastapi.security import HTTPBearer
import httpx
import asyncio
from typing import List, Optional
import os
from datetime import datetime, timedelta
import json
import logging
from sqlalchemy import create_engine, Column, String, DateTime, Boolean, Text, Integer, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.dialects.postgresql import UUID
import uuid
from pydantic import BaseModel
import aioredis
from celery import Celery
import smtplib
from email.mime.text import MimeText
from email.mime.multipart import MimeMultipart
from jinja2 import Template
import requests

# Configuración
app = FastAPI(title="Notifications Service", version="1.0.0")
security = HTTPBearer()

# Configuración de base de datos
DATABASE_URL = os.getenv("DATABASE_URL")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Configuración de Celery para tareas asíncronas
celery = Celery(
    'notifications',
    broker=os.getenv('RABBITMQ_URL'),
    backend='redis://redis:6379/0'
)

# Configuración de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Modelos de base de datos
class NotificationTemplate(Base):
    __tablename__ = "notification_templates"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(200), nullable=False)
    template_type = Column(String(50), nullable=False)
    channel = Column(String(20), nullable=False)
    subject = Column(String(200))
    message_template = Column(Text, nullable=False)
    whatsapp_template_name = Column(String(100))
    available_variables = Column(JSON, default=[])
    is_active = Column(Boolean, default=True)
    send_immediately = Column(Boolean, default=False)
    send_delay_minutes = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class Notification(Base):
    __tablename__ = "notifications"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id = Column(UUID(as_uuid=True), nullable=False)
    recipient_type = Column(String(20), nullable=False)
    recipient_id = Column(UUID(as_uuid=True), nullable=False)
    recipient_email = Column(String(255))
    recipient_phone = Column(String(15))
    subject = Column(String(200))
    message = Column(Text, nullable=False)
    status = Column(String(20), default='pending')
    scheduled_at = Column(DateTime, nullable=False)
    sent_at = Column(DateTime)
    delivered_at = Column(DateTime)
    read_at = Column(DateTime)
    attempt_count = Column(Integer, default=0)
    last_error = Column(Text)
    external_id = Column(String(100))
    related_model = Column(String(50))
    related_id = Column(UUID(as_uuid=True))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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
class NotificationRequest(BaseModel):
    template_type: str
    recipient_type: str
    recipient_id: str
    recipient_email: Optional[str] = None
    recipient_phone: Optional[str] = None
    variables: dict = {}
    scheduled_at: Optional[datetime] = None
    channel: str = 'email'
    related_model: Optional[str] = None
    related_id: Optional[str] = None

class TemplateRequest(BaseModel):
    name: str
    template_type: str
    channel: str
    subject: Optional[str] = None
    message_template: str
    whatsapp_template_name: Optional[str] = None
    available_variables: List[str] = []
    send_immediately: bool = False
    send_delay_minutes: int = 0

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

# Servicios de envío
class WhatsAppService:
    def __init__(self):
        self.token = os.getenv('WHATSAPP_TOKEN')
        self.phone_id = os.getenv('WHATSAPP_PHONE_ID')
        self.base_url = f"https://graph.facebook.com/v18.0/{self.phone_id}/messages"
    
    async def send_template_message(self, phone: str, template_name: str, parameters: List[str]):
        """Enviar mensaje usando plantilla aprobada de WhatsApp"""
        headers = {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json'
        }
        
        # Formatear teléfono (quitar espacios, guiones, etc.)
        phone = phone.replace('+', '').replace(' ', '').replace('-', '')
        if not phone.startswith('57'):  # Código de Colombia
            phone = '57' + phone
        
        payload = {
            "messaging_product": "whatsapp",
            "to": phone,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": "es"},
                "components": [
                    {
                        "type": "body",
                        "parameters": [{"type": "text", "text": param} for param in parameters]
                    }
                ]
            }
        }
        
        try:
            response = requests.post(self.base_url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error enviando WhatsApp: {e}")
            raise
    
    async def send_text_message(self, phone: str, message: str):
        """Enviar mensaje de texto simple (solo para pruebas en sandbox)"""
        headers = {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json'
        }
        
        phone = phone.replace('+', '').replace(' ', '').replace('-', '')
        if not phone.startswith('57'):
            phone = '57' + phone
        
        payload = {
            "messaging_product": "whatsapp",
            "to": phone,
            "type": "text",
            "text": {"body": message}
        }
        
        try:
            response = requests.post(self.base_url, headers=headers, json=payload)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Error enviando WhatsApp: {e}")
            raise

class EmailService:
    def __init__(self):
        self.smtp_host = os.getenv('SMTP_HOST', 'localhost')
        self.smtp_port = int(os.getenv('SMTP_PORT', 587))
        self.smtp_user = os.getenv('SMTP_USER')
        self.smtp_password = os.getenv('SMTP_PASSWORD')
        self.sendgrid_key = os.getenv('SENDGRID_API_KEY')
    
    async def send_email(self, to_email: str, subject: str, message: str, is_html: bool = False):
        """Enviar email usando SMTP o SendGrid"""
        if self.sendgrid_key:
            return await self._send_with_sendgrid(to_email, subject, message, is_html)
        else:
            return await self._send_with_smtp(to_email, subject, message, is_html)
    
    async def _send_with_smtp(self, to_email: str, subject: str, message: str, is_html: bool = False):
        """Enviar email usando SMTP"""
        try:
            msg = MimeMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.smtp_user
            msg['To'] = to_email
            
            if is_html:
                msg.attach(MimeText(message, 'html'))
            else:
                msg.attach(MimeText(message, 'plain'))
            
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_password)
                server.send_message(msg)
            
            return {"status": "sent", "message_id": None}
        except Exception as e:
            logger.error(f"Error enviando email SMTP: {e}")
            raise
    
    async def _send_with_sendgrid(self, to_email: str, subject: str, message: str, is_html: bool = False):
        """Enviar email usando SendGrid"""
        # Implementar SendGrid aquí si es necesario
        pass

# Instanciar servicios
whatsapp_service = WhatsAppService()
email_service = EmailService()

# Tareas Celery
@celery.task
def send_notification_task(notification_id: str):
    """Tarea asíncrona para enviar notificación"""
    db = SessionLocal()
    try:
        notification = db.query(Notification).filter(Notification.id == notification_id).first()
        if not notification:
            logger.error(f"Notificación {notification_id} no encontrada")
            return
        
        template = db.query(NotificationTemplate).filter(
            NotificationTemplate.id == notification.template_id
        ).first()
        
        if not template:
            logger.error(f"Template {notification.template_id} no encontrado")
            return
        
        try:
            if template.channel == 'whatsapp':
                # Enviar por WhatsApp
                if template.whatsapp_template_name:
                    # Usar plantilla aprobada
                    # Extraer parámetros del mensaje
                    parameters = []  # Aquí deberías extraer los parámetros del mensaje
                    result = asyncio.run(
                        whatsapp_service.send_template_message(
                            notification.recipient_phone,
                            template.whatsapp_template_name,
                            parameters
                        )
                    )
                else:
                    # Mensaje de texto simple
                    result = asyncio.run(
                        whatsapp_service.send_text_message(
                            notification.recipient_phone,
                            notification.message
                        )
                    )
                
                notification.external_id = result.get('messages', [{}])[0].get('id')
                
            elif template.channel == 'email':
                # Enviar por email
                result = asyncio.run(
                    email_service.send_email(
                        notification.recipient_email,
                        notification.subject,
                        notification.message,
                        is_html=True
                    )
                )
                notification.external_id = result.get('message_id')
            
            # Actualizar estado
            notification.status = 'sent'
            notification.sent_at = datetime.utcnow()
            notification.attempt_count += 1
            
        except Exception as e:
            notification.status = 'failed'
            notification.last_error = str(e)
            notification.attempt_count += 1
            logger.error(f"Error enviando notificación {notification_id}: {e}")
        
        db.commit()
        
    finally:
        db.close()

# Endpoints
@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "notifications"}

@app.post("/send")
async def send_notification(
    request: NotificationRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user = Depends(get_current_user)
):
    """Enviar una notificación"""
    # Buscar template
    template = db.query(NotificationTemplate).filter(
        NotificationTemplate.template_type == request.template_type,
        NotificationTemplate.channel == request.channel,
        NotificationTemplate.is_active == True
    ).first()
    
    if not template:
        raise HTTPException(status_code=404, detail="Template no encontrado")
    
    # Renderizar mensaje con variables
    template_engine = Template(template.message_template)
    message = template_engine.render(**request.variables)
    
    subject = ""
    if template.subject:
        subject_template = Template(template.subject)
        subject = subject_template.render(**request.variables)
    
    # Determinar cuándo enviar
    scheduled_at = request.scheduled_at or datetime.utcnow()
    if template.send_delay_minutes > 0:
        scheduled_at += timedelta(minutes=template.send_delay_minutes)
    
    # Crear notificación
    notification = Notification(
        template_id=template.id,
        recipient_type=request.recipient_type,
        recipient_id=request.recipient_id,
        recipient_email=request.recipient_email,
        recipient_phone=request.recipient_phone,
        subject=subject,
        message=message,
        scheduled_at=scheduled_at,
        related_model=request.related_model,
        related_id=request.related_id
    )
    
    db.add(notification)
    db.commit()
    db.refresh(notification)
    
    # Programar envío
    if template.send_immediately:
        background_tasks.add_task(send_notification_task, str(notification.id))
    else:
        # Programar con Celery
        send_notification_task.apply_async(
            args=[str(notification.id)],
            eta=scheduled_at
        )
    
    return {"id": notification.id, "status": "scheduled"}

@app.get("/templates")
async def get_templates(
    db: Session = Depends(get_db),
    user = Depends(get_current_user)
):
    """Obtener todas las plantillas"""
    templates = db.query(NotificationTemplate).filter(
        NotificationTemplate.is_active == True
    ).all()
    return templates

@app.post("/templates")
async def create_template(
    request: TemplateRequest,
    db: Session = Depends(get_db),
    user = Depends(get_current_user)
):
    """Crear nueva plantilla"""
    template = NotificationTemplate(
        name=request.name,
        template_type=request.template_type,
        channel=request.channel,
        subject=request.subject,
        message_template=request.message_template,
        whatsapp_template_name=request.whatsapp_template_name,
        available_variables=request.available_variables,
        send_immediately=request.send_immediately,
        send_delay_minutes=request.send_delay_minutes
    )
    
    db.add(template)
    db.commit()
    db.refresh(template)
    
    return template

@app.get("/notifications")
async def get_notifications(
    db: Session = Depends(get_db),
    user = Depends(get_current_user),
    status: Optional[str] = None,
    limit: int = 50
):
    """Obtener notificaciones"""
    query = db.query(Notification)
    
    if status:
        query = query.filter(Notification.status == status)
    
    notifications = query.order_by(Notification.created_at.desc()).limit(limit).all()
    return notifications

@app.get("/pending")
async def get_pending_notifications(
    db: Session = Depends(get_db),
    user = Depends(get_current_user)
):
    """Obtener notificaciones pendientes para el dashboard"""
    count = db.query(Notification).filter(
        Notification.status == 'pending'
    ).count()
    
    recent = db.query(Notification).filter(
        Notification.status == 'pending'
    ).order_by(Notification.scheduled_at).limit(5).all()
    
    return {
        "count": count,
        "recent": recent
    }

# Endpoint para webhooks de WhatsApp
@app.post("/webhook/whatsapp")
async def whatsapp_webhook(request: dict, db: Session = Depends(get_db)):
    """Webhook para recibir actualizaciones de estado de WhatsApp"""
    # Procesar webhook de WhatsApp para actualizar estados de entrega
    try:
        for entry in request.get('entry', []):
            for change in entry.get('changes', []):
                if change.get('field') == 'messages':
                    value = change.get('value', {})
                    statuses = value.get('statuses', [])
                    
                    for status in statuses:
                        message_id = status.get('id')
                        status_value = status.get('status')
                        timestamp = status.get('timestamp')
                        
                        # Actualizar notificación
                        notification = db.query(Notification).filter(
                            Notification.external_id == message_id
                        ).first()
                        
                        if notification:
                            if status_value == 'delivered':
                                notification.status = 'delivered'
                                notification.delivered_at = datetime.fromtimestamp(int(timestamp))
                            elif status_value == 'read':
                                notification.status = 'read' 
                                notification.read_at = datetime.fromtimestamp(int(timestamp))
                            elif status_value == 'failed':
                                notification.status = 'failed'
                            
                            db.commit()
        
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Error procesando webhook WhatsApp: {e}")
        raise HTTPException(status_code=500, detail="Error procesando webhook")

# Tareas programadas para recordatorios automáticos
@celery.task
def send_appointment_reminders():
    """Enviar recordatorios de citas programadas para mañana"""
    # Esta tarea se ejecutaría diariamente
    # Consultaría el servicio de citas para obtener las citas de mañana
    # y enviaría recordatorios automáticamente
    pass

# Configurar tareas programadas
celery.conf.beat_schedule = {
    'send-appointment-reminders': {
        'task': 'notifications_service.main.send_appointment_reminders',
        'schedule': 60.0 * 60 * 24,  # Diariamente
    },
}
celery.conf.timezone = 'America/Bogota'

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8006)