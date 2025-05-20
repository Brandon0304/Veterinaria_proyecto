from fastapi import FastAPI, HTTPException, Depends, Query, UploadFile, File
from fastapi.security import HTTPBearer
import httpx
from typing import List, Optional
import os
from datetime import datetime, date
import json
import logging
from sqlalchemy import create_engine, Column, String, DateTime, Boolean, Text, Integer, Date, ForeignKey, Numeric
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from sqlalchemy.dialects.postgresql import UUID
import uuid
from pydantic import BaseModel, validator
from enum import Enum
from decimal import Decimal

# Configuración
app = FastAPI(title="Medical Records Service", version="1.0.0")
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
class VaccinationType(str, Enum):
    rabies = "rabies"
    distemper = "distemper"
    parvovirus = "parvovirus"
    adenovirus = "adenovirus"
    parainfluenza = "parainfluenza"
    bordetella = "bordetella"
    leptospirosis = "leptospirosis"
    lyme = "lyme"
    feline_viral_rhinotracheitis = "feline_viral_rhinotracheitis"
    calicivirus = "calicivirus"
    panleukopenia = "panleukopenia"
    feline_leukemia = "feline_leukemia"
    other = "other"

class SampleType(str, Enum):
    blood = "blood"
    urine = "urine"
    feces = "feces"
    saliva = "saliva"
    tissue = "tissue"
    swab = "swab"
    other = "other"

class SurgeryType(str, Enum):
    sterilization = "sterilization"
    dental = "dental"
    orthopedic = "orthopedic"
    soft_tissue = "soft_tissue"
    emergency = "emergency"
    oncologic = "oncologic"
    ophthalmic = "ophthalmic"
    other = "other"

# Modelos de base de datos
class MedicalRecord(Base):
    __tablename__ = "medical_records"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    pet_id = Column(UUID(as_uuid=True), unique=True, nullable=False)
    
    # Información general
    blood_type = Column(String(10))
    microchip_number = Column(String(50))
    insurance_policy = Column(String(100))
    
    # Antecedentes médicos
    medical_history = Column(Text)
    surgical_history = Column(Text)
    allergies = Column(Text)
    chronic_conditions = Column(Text)
    current_medications = Column(Text)
    behavioral_notes = Column(Text)
    
    # Información reproductiva
    is_sterilized = Column(Boolean, default=False)
    sterilization_date = Column(Date)
    sterilization_type = Column(String(50))
    last_heat_date = Column(Date)
    breeding_history = Column(Text)
    
    # Datos de emergencia
    emergency_contact = Column(Text)
    special_instructions = Column(Text)
    diet_instructions = Column(Text)
    exercise_restrictions = Column(Text)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relaciones
    consultations = relationship("Consultation", back_populates="medical_record")
    vaccinations = relationship("Vaccination", back_populates="medical_record")
    surgeries = relationship("Surgery", back_populates="medical_record")

class Consultation(Base):
    __tablename__ = "consultations"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    medical_record_id = Column(UUID(as_uuid=True), ForeignKey('medical_records.id'), nullable=False)
    appointment_id = Column(UUID(as_uuid=True), unique=True)  # Referencia a cita
    veterinarian_id = Column(UUID(as_uuid=True), nullable=False)
    
    # Información básica
    consultation_date = Column(DateTime, default=datetime.utcnow)
    consultation_type = Column(String(50), default='general')  # general, emergency, follow_up, etc.
    chief_complaint = Column(Text)  # Motivo principal de consulta
    
    # Signos vitales
    weight = Column(Numeric(5, 2))
    temperature = Column(Numeric(4, 1))
    heart_rate = Column(Integer)
    respiratory_rate = Column(Integer)
    blood_pressure_systolic = Column(Integer)
    blood_pressure_diastolic = Column(Integer)
    capillary_refill_time = Column(String(20))
    
    # Examen físico
    general_appearance = Column(Text)
    behavior_attitude = Column(Text)
    body_condition_score = Column(String(10))  # 1-9 scale
    hydration_status = Column(String(50))
    mucous_membranes = Column(Text)
    lymph_nodes = Column(Text)
    skin_coat = Column(Text)
    eyes = Column(Text)
    ears = Column(Text)
    oral_cavity = Column(Text)
    cardiovascular = Column(Text)
    respiratory = Column(Text)
    gastrointestinal = Column(Text)
    genitourinary = Column(Text)
    musculoskeletal = Column(Text)
    neurological = Column(Text)
    
    # Evaluación y plan
    assessment = Column(Text)
    diagnosis = Column(Text)
    differential_diagnosis = Column(Text)
    treatment_plan = Column(Text)
    prescribed_medications = Column(Text)
    recommendations = Column(Text)
    
    # Seguimiento
    next_visit_date = Column(Date)
    follow_up_instructions = Column(Text)
    notes = Column(Text)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relaciones
    medical_record = relationship("MedicalRecord", back_populates="consultations")
    prescriptions = relationship("Prescription", back_populates="consultation")
    lab_results = relationship("Laboratory", back_populates="consultation")

class Vaccination(Base):
    __tablename__ = "vaccinations"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    medical_record_id = Column(UUID(as_uuid=True), ForeignKey('medical_records.id'), nullable=False)
    veterinarian_id = Column(UUID(as_uuid=True), nullable=False)
    
    # Información de la vacuna
    vaccine_name = Column(String(200), nullable=False)
    vaccine_type = Column(String(50), nullable=False)
    vaccine_brand = Column(String(100))
    manufacturer = Column(String(100))
    batch_number = Column(String(50))
    expiration_date = Column(Date)
    
    # Fechas
    vaccination_date = Column(Date, nullable=False)
    next_due_date = Column(Date)
    
    # Administración
    site_of_injection = Column(String(100))
    route = Column(String(50))  # subcutaneous, intramuscular, etc.
    dose_volume = Column(String(20))
    
    # Reacciones y seguimiento
    immediate_reaction = Column(Text)
    delayed_reaction = Column(Text)
    reaction_severity = Column(String(20))  # mild, moderate, severe
    
    # Notas
    notes = Column(Text)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relaciones
    medical_record = relationship("MedicalRecord", back_populates="vaccinations")

class Laboratory(Base):
    __tablename__ = "laboratory_results"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    consultation_id = Column(UUID(as_uuid=True), ForeignKey('consultations.id'), nullable=False)
    
    # Información del examen
    test_category = Column(String(100))  # hematology, biochemistry, microbiology, etc.
    test_name = Column(String(200), nullable=False)
    sample_type = Column(String(50), nullable=False)
    sample_collection_date = Column(DateTime)
    results_date = Column(DateTime)
    
    # Laboratorio externo
    laboratory_name = Column(String(200))
    laboratory_reference = Column(String(100))
    
    # Resultados
    results_data = Column(Text)  # JSON con resultados detallados
    interpretation = Column(Text)
    veterinarian_comments = Column(Text)
    
    # Referencias normales
    reference_ranges = Column(Text)  # JSON con rangos de referencia
    abnormal_flags = Column(Text)  # JSON con marcadores de valores anormales
    
    # Archivos adjuntos
    report_file_urls = Column(Text)  # JSON con URLs de reportes
    image_urls = Column(Text)  # JSON con URLs de imágenes
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relaciones
    consultation = relationship("Consultation", back_populates="lab_results")

class Surgery(Base):
    __tablename__ = "surgeries"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    medical_record_id = Column(UUID(as_uuid=True), ForeignKey('medical_records.id'), nullable=False)
    veterinarian_id = Column(UUID(as_uuid=True), nullable=False)
    
    # Información básica
    surgery_type = Column(String(50), nullable=False)
    surgery_name = Column(String(200), nullable=False)
    indication = Column(Text)  # Indicación médica
    urgency_level = Column(String(20))  # elective, urgent, emergency
    
    # Fechas y tiempos
    surgery_date = Column(Date, nullable=False)
    start_time = Column(DateTime)
    end_time = Column(DateTime)
    duration_minutes = Column(Integer)
    
    # Equipo quirúrgico
    assistant_ids = Column(Text)  # JSON con IDs de asistentes
    anesthesiologist_id = Column(UUID(as_uuid=True))
    
    # Pre-operatorio
    preoperative_diagnosis = Column(Text)
    preoperative_assessment = Column(Text)
    risk_factors = Column(Text)
    consent_form_signed = Column(Boolean, default=False)
    
    # Anestesia
    anesthesia_protocol = Column(Text)
    anesthesia_medications = Column(Text)
    anesthesia_complications = Column(Text)
    
    # Procedimiento
    surgical_approach = Column(Text)
    procedure_description = Column(Text)
    findings = Column(Text)
    complications_during_surgery = Column(Text)
    specimens_collected = Column(Text)
    
    # Post-operatorio
    postoperative_diagnosis = Column(Text)
    immediate_recovery = Column(Text)
    pain_management = Column(Text)
    medications_prescribed = Column(Text)
    discharge_instructions = Column(Text)
    
    # Seguimiento
    follow_up_date = Column(Date)
    suture_removal_date = Column(Date)
    activity_restrictions = Column(Text)
    
    # Archivos
    surgical_report_url = Column(String(500))
    photos_urls = Column(Text)  # JSON con URLs de fotos
    videos_urls = Column(Text)  # JSON con URLs de videos
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relaciones
    medical_record = relationship("MedicalRecord", back_populates="surgeries")

class Prescription(Base):
    __tablename__ = "prescriptions"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    consultation_id = Column(UUID(as_uuid=True), ForeignKey('consultations.id'), nullable=False)
    
    # Información del medicamento
    medication_name = Column(String(200), nullable=False)
    generic_name = Column(String(200))
    active_ingredient = Column(String(200))
    concentration = Column(String(100))
    
    # Dosificación
    dosage = Column(String(100), nullable=False)
    frequency = Column(String(100), nullable=False)
    duration = Column(String(100), nullable=False)
    total_quantity = Column(String(50))
    
    # Instrucciones
    administration_instructions = Column(Text)
    special_instructions = Column(Text)
    food_interactions = Column(Text)
    
    # Dispensación
    refills_allowed = Column(Integer, default=0)
    refills_used = Column(Integer, default=0)
    dispensed_date = Column(DateTime)
    dispensed_by = Column(String(100))
    
    # Seguimiento
    effectiveness_notes = Column(Text)
    side_effects = Column(Text)
    compliance_notes = Column(Text)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relaciones
    consultation = relationship("Consultation", back_populates="prescriptions")

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
class MedicalRecordCreate(BaseModel):
    pet_id: str
    blood_type: Optional[str] = None
    microchip_number: Optional[str] = None
    insurance_policy: Optional[str] = None
    medical_history: Optional[str] = None
    surgical_history: Optional[str] = None
    allergies: Optional[str] = None
    chronic_conditions: Optional[str] = None
    current_medications: Optional[str] = None
    behavioral_notes: Optional[str] = None
    special_instructions: Optional[str] = None
    diet_instructions: Optional[str] = None
    exercise_restrictions: Optional[str] = None

class MedicalRecordUpdate(BaseModel):
    blood_type: Optional[str] = None
    microchip_number: Optional[str] = None
    insurance_policy: Optional[str] = None
    medical_history: Optional[str] = None
    surgical_history: Optional[str] = None
    allergies: Optional[str] = None
    chronic_conditions: Optional[str] = None
    current_medications: Optional[str] = None
    behavioral_notes: Optional[str] = None
    is_sterilized: Optional[bool] = None
    sterilization_date: Optional[date] = None
    sterilization_type: Optional[str] = None
    last_heat_date: Optional[date] = None
    breeding_history: Optional[str] = None
    emergency_contact: Optional[str] = None
    special_instructions: Optional[str] = None
    diet_instructions: Optional[str] = None
    exercise_restrictions: Optional[str] = None

class MedicalRecordResponse(BaseModel):
    id: str
    pet_id: str
    blood_type: Optional[str]
    microchip_number: Optional[str]
    insurance_policy: Optional[str]
    medical_history: Optional[str]
    surgical_history: Optional[str]
    allergies: Optional[str]
    chronic_conditions: Optional[str]
    current_medications: Optional[str]
    behavioral_notes: Optional[str]
    is_sterilized: bool
    sterilization_date: Optional[date]
    sterilization_type: Optional[str]
    last_heat_date: Optional[date]
    breeding_history: Optional[str]
    emergency_contact: Optional[str]
    special_instructions: Optional[str]
    diet_instructions: Optional[str]
    exercise_restrictions: Optional[str]
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class ConsultationCreate(BaseModel):
    medical_record_id: str
    appointment_id: Optional[str] = None
    veterinarian_id: str
    consultation_type: str = 'general'
    chief_complaint: str
    
    # Signos vitales
    weight: Optional[Decimal] = None
    temperature: Optional[Decimal] = None
    heart_rate: Optional[int] = None
    respiratory_rate: Optional[int] = None
    blood_pressure_systolic: Optional[int] = None
    blood_pressure_diastolic: Optional[int] = None
    capillary_refill_time: Optional[str] = None
    
    # Examen físico
    general_appearance: Optional[str] = None
    behavior_attitude: Optional[str] = None
    body_condition_score: Optional[str] = None
    hydration_status: Optional[str] = None
    
    # Evaluación
    assessment: str
    diagnosis: str
    differential_diagnosis: Optional[str] = None
    treatment_plan: str
    prescribed_medications: Optional[str] = None
    recommendations: Optional[str] = None
    
    # Seguimiento
    next_visit_date: Optional[date] = None
    follow_up_instructions: Optional[str] = None
    notes: Optional[str] = None

class ConsultationResponse(BaseModel):
    id: str
    medical_record_id: str
    appointment_id: Optional[str]
    veterinarian_id: str
    consultation_date: datetime
    consultation_type: str
    chief_complaint: str
    weight: Optional[Decimal]
    temperature: Optional[Decimal]
    heart_rate: Optional[int]
    respiratory_rate: Optional[int]
    assessment: str
    diagnosis: str
    treatment_plan: str
    prescribed_medications: Optional[str]
    recommendations: Optional[str]
    next_visit_date: Optional[date]
    follow_up_instructions: Optional[str]
    notes: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True

class VaccinationCreate(BaseModel):
    medical_record_id: str
    veterinarian_id: str
    vaccine_name: str
    vaccine_type: VaccinationType
    vaccine_brand: Optional[str] = None
    manufacturer: Optional[str] = None
    batch_number: Optional[str] = None
    expiration_date: Optional[date] = None
    vaccination_date: date
    next_due_date: Optional[date] = None
    site_of_injection: Optional[str] = None
    route: Optional[str] = None
    dose_volume: Optional[str] = None
    immediate_reaction: Optional[str] = None
    notes: Optional[str] = None

class VaccinationResponse(BaseModel):
    id: str
    medical_record_id: str
    veterinarian_id: str
    vaccine_name: str
    vaccine_type: str
    vaccine_brand: Optional[str]
    manufacturer: Optional[str]
    batch_number: Optional[str]
    expiration_date: Optional[date]
    vaccination_date: date
    next_due_date: Optional[date]
    site_of_injection: Optional[str]
    route: Optional[str]
    dose_volume: Optional[str]
    immediate_reaction: Optional[str]
    delayed_reaction: Optional[str]
    reaction_severity: Optional[str]
    notes: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True

class PrescriptionCreate(BaseModel):
    consultation_id: str
    medication_name: str
    generic_name: Optional[str] = None
    active_ingredient: Optional[str] = None
    concentration: Optional[str] = None
    dosage: str
    frequency: str
    duration: str
    total_quantity: Optional[str] = None
    administration_instructions: Optional[str] = None
    special_instructions: Optional[str] = None
    food_interactions: Optional[str] = None
    refills_allowed: int = 0

class PrescriptionResponse(BaseModel):
    id: str
    consultation_id: str
    medication_name: str
    generic_name: Optional[str]
    active_ingredient: Optional[str]
    concentration: Optional[str]
    dosage: str
    frequency: str
    duration: str
    total_quantity: Optional[str]
    administration_instructions: Optional[str]
    special_instructions: Optional[str]
    food_interactions: Optional[str]
    refills_allowed: int
    refills_used: int
    dispensed_date: Optional[datetime]
    dispensed_by: Optional[str]
    created_at: datetime
    
    class Config:
        from_attributes = True

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
async def get_pet_info(pet_id: str, token: str):
    """Obtener información de la mascota desde el servicio de clientes"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{os.getenv('CLIENTS_SERVICE_URL')}/pets/{pet_id}",
                headers={"Authorization": f"Bearer {token}"}
            )
            if response.status_code == 200:
                return response.json()
    except Exception as e:
        logger.error(f"Error obteniendo información de mascota: {e}")
    return None

async def get_veterinarian_info(vet_id: str, token: str):
    """Obtener información del veterinario desde el servicio de empleados"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{os.getenv('EMPLOYEES_SERVICE_URL')}/employees/{vet_id}",
                headers={"Authorization": f"Bearer {token}"}
            )
            if response.status_code == 200:
                return response.json()
    except Exception as e:
        logger.error(f"Error obteniendo información de veterinario: {e}")
    return None

# ENDPOINTS

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "medical_records"}

# ENDPOINTS DE HISTORIA CLÍNICA

@app.post("/medical-records", response_model=MedicalRecordResponse)
async def create_medical_record(
    record: MedicalRecordCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Crear nueva historia clínica"""
    # Verificar que no existe historia clínica para esa mascota
    existing_record = db.query(MedicalRecord).filter(
        MedicalRecord.pet_id == record.pet_id
    ).first()
    
    if existing_record:
        raise HTTPException(
            status_code=400,
            detail="Ya existe una historia clínica para esta mascota"
        )
    
    # Crear historia clínica
    db_record = MedicalRecord(
        pet_id=record.pet_id,
        blood_type=record.blood_type,
        microchip_number=record.microchip_number,
        insurance_policy=record.insurance_policy,
        medical_history=record.medical_history,
        surgical_history=record.surgical_history,
        allergies=record.allergies,
        chronic_conditions=record.chronic_conditions,
        current_medications=record.current_medications,
        behavioral_notes=record.behavioral_notes,
        special_instructions=record.special_instructions,
        diet_instructions=record.diet_instructions,
        exercise_restrictions=record.exercise_restrictions
    )
    
    db.add(db_record)
    db.commit()
    db.refresh(db_record)
    
    return MedicalRecordResponse.from_orm(db_record)

@app.get("/medical-records/pet/{pet_id}", response_model=MedicalRecordResponse)
async def get_medical_record_by_pet(
    pet_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Obtener historia clínica por ID de mascota"""
    record = db.query(MedicalRecord).filter(MedicalRecord.pet_id == pet_id).first()
    
    if not record:
        raise HTTPException(status_code=404, detail="Historia clínica no encontrada")
    
    return MedicalRecordResponse.from_orm(record)

@app.get("/medical-records/{record_id}", response_model=MedicalRecordResponse)
async def get_medical_record(
    record_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Obtener historia clínica por ID"""
    record = db.query(MedicalRecord).filter(MedicalRecord.id == record_id).first()
    
    if not record:
        raise HTTPException(status_code=404, detail="Historia clínica no encontrada")
    
    return MedicalRecordResponse.from_orm(record)

@app.put("/medical-records/{record_id}", response_model=MedicalRecordResponse)
async def update_medical_record(
    record_id: str,
    record_update: MedicalRecordUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Actualizar historia clínica"""
    db_record = db.query(MedicalRecord).filter(MedicalRecord.id == record_id).first()
    
    if not db_record:
        raise HTTPException(status_code=404, detail="Historia clínica no encontrada")
    
    # Actualizar campos
    update_data = record_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_record, field, value)
    
    db_record.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(db_record)
    
    return MedicalRecordResponse.from_orm(db_record)

# ENDPOINTS DE CONSULTAS

@app.post("/consultations", response_model=ConsultationResponse)
async def create_consultation(
    consultation: ConsultationCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Crear nueva consulta"""
    # Verificar que existe la historia clínica
    record = db.query(MedicalRecord).filter(
        MedicalRecord.id == consultation.medical_record_id
    ).first()
    
    if not record:
        raise HTTPException(status_code=404, detail="Historia clínica no encontrada")
    
    # Crear consulta
    db_consultation = Consultation(
        medical_record_id=consultation.medical_record_id,
        appointment_id=consultation.appointment_id,
        veterinarian_id=consultation.veterinarian_id,
        consultation_type=consultation.consultation_type,
        chief_complaint=consultation.chief_complaint,
        weight=consultation.weight,
        temperature=consultation.temperature,
        heart_rate=consultation.heart_rate,
        respiratory_rate=consultation.respiratory_rate,
        blood_pressure_systolic=consultation.blood_pressure_systolic,
        blood_pressure_diastolic=consultation.blood_pressure_diastolic,
        capillary_refill_time=consultation.capillary_refill_time,
        general_appearance=consultation.general_appearance,
        behavior_attitude=consultation.behavior_attitude,
        body_condition_score=consultation.body_condition_score,
        hydration_status=consultation.hydration_status,
        assessment=consultation.assessment,
        diagnosis=consultation.diagnosis,
        differential_diagnosis=consultation.differential_diagnosis,
        treatment_plan=consultation.treatment_plan,
        prescribed_medications=consultation.prescribed_medications,
        recommendations=consultation.recommendations,
        next_visit_date=consultation.next_visit_date,
        follow_up_instructions=consultation.follow_up_instructions,
        notes=consultation.notes
    )
    
    db.add(db_consultation)
    db.commit()
    db.refresh(db_consultation)
    
    return ConsultationResponse.from_orm(db_consultation)

@app.get("/medical-records/{record_id}/consultations", response_model=List[ConsultationResponse])
async def get_consultations_by_record(
    record_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, le=100)
):
    """Obtener consultas de una historia clínica"""
    consultations = db.query(Consultation).filter(
        Consultation.medical_record_id == record_id
    ).order_by(Consultation.consultation_date.desc()).offset(skip).limit(limit).all()
    
    return [ConsultationResponse.from_orm(consultation) for consultation in consultations]

@app.get("/consultations/{consultation_id}", response_model=ConsultationResponse)
async def get_consultation(
    consultation_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Obtener consulta específica"""
    consultation = db.query(Consultation).filter(Consultation.id == consultation_id).first()
    
    if not consultation:
        raise HTTPException(status_code=404, detail="Consulta no encontrada")
    
    return ConsultationResponse.from_orm(consultation)

# ENDPOINTS DE VACUNAS

@app.post("/vaccinations", response_model=VaccinationResponse)
async def create_vaccination(
    vaccination: VaccinationCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Registrar nueva vacuna"""
    # Verificar que existe la historia clínica
    record = db.query(MedicalRecord).filter(
        MedicalRecord.id == vaccination.medical_record_id
    ).first()
    
    if not record:
        raise HTTPException(status_code=404, detail="Historia clínica no encontrada")
    
    # Crear vacuna
    db_vaccination = Vaccination(
        medical_record_id=vaccination.medical_record_id,
        veterinarian_id=vaccination.veterinarian_id,
        vaccine_name=vaccination.vaccine_name,
        vaccine_type=vaccination.vaccine_type,
        vaccine_brand=vaccination.vaccine_brand,
        manufacturer=vaccination.manufacturer,
        batch_number=vaccination.batch_number,
        expiration_date=vaccination.expiration_date,
        vaccination_date=vaccination.vaccination_date,
        next_due_date=vaccination.next_due_date,
        site_of_injection=vaccination.site_of_injection,
        route=vaccination.route,
        dose_volume=vaccination.dose_volume,
        immediate_reaction=vaccination.immediate_reaction,
        notes=vaccination.notes
    )
    
    db.add(db_vaccination)
    db.commit()
    db.refresh(db_vaccination)
    
    return VaccinationResponse.from_orm(db_vaccination)

@app.get("/medical-records/{record_id}/vaccinations", response_model=List[VaccinationResponse])
async def get_vaccinations_by_record(
    record_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Obtener vacunas de una historia clínica"""
    vaccinations = db.query(Vaccination).filter(
        Vaccination.medical_record_id == record_id
    ).order_by(Vaccination.vaccination_date.desc()).all()
    
    return [VaccinationResponse.from_orm(vaccination) for vaccination in vaccinations]

@app.get("/vaccinations/due")
async def get_vaccinations_due(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
    days_ahead: int = Query(30, ge=1, le=365)
):
    """Obtener vacunas próximas a vencer"""
    future_date = date.today() + timedelta(days=days_ahead)
    
    vaccinations_due = db.query(Vaccination).filter(
        Vaccination.next_due_date.between(date.today(), future_date)
    ).order_by(Vaccination.next_due_date).all()
    
    return [VaccinationResponse.from_orm(vaccination) for vaccination in vaccinations_due]

# ENDPOINTS DE PRESCRIPCIONES

@app.post("/prescriptions", response_model=PrescriptionResponse)
async def create_prescription(
    prescription: PrescriptionCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Crear nueva prescripción"""
    # Verificar que existe la consulta
    consultation = db.query(Consultation).filter(
        Consultation.id == prescription.consultation_id
    ).first()
    
    if not consultation:
        raise HTTPException(status_code=404, detail="Consulta no encontrada")
    
    # Crear prescripción
    db_prescription = Prescription(
        consultation_id=prescription.consultation_id,
        medication_name=prescription.medication_name,
        generic_name=prescription.generic_name,
        active_ingredient=prescription.active_ingredient,
        concentration=prescription.concentration,
        dosage=prescription.dosage,
        frequency=prescription.frequency,
        duration=prescription.duration,
        total_quantity=prescription.total_quantity,
        administration_instructions=prescription.administration_instructions,
        special_instructions=prescription.special_instructions,
        food_interactions=prescription.food_interactions,
        refills_allowed=prescription.refills_allowed
    )
    
    db.add(db_prescription)
    db.commit()
    db.refresh(db_prescription)
    
    return PrescriptionResponse.from_orm(db_prescription)

@app.get("/consultations/{consultation_id}/prescriptions", response_model=List[PrescriptionResponse])
async def get_prescriptions_by_consultation(
    consultation_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Obtener prescripciones de una consulta"""
    prescriptions = db.query(Prescription).filter(
        Prescription.consultation_id == consultation_id
    ).order_by(Prescription.created_at.desc()).all()
    
    return [PrescriptionResponse.from_orm(prescription) for prescription in prescriptions]

# ENDPOINTS DE BÚSQUEDA Y REPORTES

@app.get("/search")
async def search_medical_records(
    q: str = Query(..., min_length=2),
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
    record_type: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None
):
    """Búsqueda en registros médicos"""
    search_pattern = f"%{q}%"
    
    results = {}
    
    # Buscar en consultas
    if not record_type or record_type == "consultations":
        consultations = db.query(Consultation).filter(
            (Consultation.chief_complaint.ilike(search_pattern)) |
            (Consultation.diagnosis.ilike(search_pattern)) |
            (Consultation.assessment.ilike(search_pattern))
        )
        
        if date_from:
            consultations = consultations.filter(Consultation.consultation_date >= date_from)
        if date_to:
            consultations = consultations.filter(Consultation.consultation_date <= date_to)
        
        results["consultations"] = [
            ConsultationResponse.from_orm(c) for c in consultations.limit(10).all()
        ]
    
    # Buscar en vacunas
    if not record_type or record_type == "vaccinations":
        vaccinations = db.query(Vaccination).filter(
            (Vaccination.vaccine_name.ilike(search_pattern)) |
            (Vaccination.vaccine_type.ilike(search_pattern))
        )
        
        if date_from:
            vaccinations = vaccinations.filter(Vaccination.vaccination_date >= date_from)
        if date_to:
            vaccinations = vaccinations.filter(Vaccination.vaccination_date <= date_to)
        
        results["vaccinations"] = [
            VaccinationResponse.from_orm(v) for v in vaccinations.limit(10).all()
        ]
    
    return results

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)