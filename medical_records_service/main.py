from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.security import HTTPBearer
import httpx
from typing import List, Optional
import os
from datetime import datetime, date, time
import json
import logging
from sqlalchemy import create_engine, Column, String, DateTime, Boolean, Text, Integer, Date, Time, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from sqlalchemy.dialects.postgresql import UUID
import uuid
from pydantic import BaseModel, EmailStr, validator
from enum import Enum
from decimal import Decimal

# Configuración
app = FastAPI(title="Employees Service", version="1.0.0")
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
class EmployeeRole(str, Enum):
    admin = "admin"
    veterinarian = "veterinarian"
    receptionist = "receptionist"
    assistant = "assistant"
    groomer = "groomer"
    manager = "manager"

class DayOfWeek(int, Enum):
    monday = 0
    tuesday = 1
    wednesday = 2
    thursday = 3
    friday = 4
    saturday = 5
    sunday = 6

# Modelos de base de datos
class Employee(Base):
    __tablename__ = "employees"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), unique=True, nullable=False)  # Referencia al usuario
    employee_code = Column(String(20), unique=True, nullable=False)
    full_name = Column(String(200), nullable=False)
    document_number = Column(String(20), unique=True, nullable=False)
    phone = Column(String(15), nullable=False)
    email = Column(String(255), nullable=False)
    roles = Column(Text, nullable=False)  # JSON string con lista de roles
    specialization = Column(String(200))  # Para veterinarios
    license_number = Column(String(50))  # Tarjeta profesional
    hire_date = Column(Date, nullable=False)
    
    # Información laboral
    department = Column(String(100))
    position = Column(String(100))
    salary = Column(String(100))  # Encriptado por seguridad
    emergency_contact_name = Column(String(200))
    emergency_contact_phone = Column(String(15))
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    # Relaciones
    schedules = relationship("WorkSchedule", back_populates="employee")
    availability = relationship("EmployeeAvailability", back_populates="employee")

class WorkSchedule(Base):
    __tablename__ = "work_schedules"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id = Column(UUID(as_uuid=True), ForeignKey('employees.id'), nullable=False)
    day_of_week = Column(Integer, nullable=False)  # 0=Lunes, 6=Domingo
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    break_start = Column(Time)
    break_end = Column(Time)
    is_active = Column(Boolean, default=True)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relaciones
    employee = relationship("Employee", back_populates="schedules")

class EmployeeAvailability(Base):
    __tablename__ = "employee_availability"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id = Column(UUID(as_uuid=True), ForeignKey('employees.id'), nullable=False)
    date = Column(Date, nullable=False)
    start_time = Column(Time, nullable=False)
    end_time = Column(Time, nullable=False)
    is_available = Column(Boolean, default=True)
    reason = Column(String(200))  # Vacaciones, enfermedad, etc.
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relaciones
    employee = relationship("Employee", back_populates="availability")

class Department(Base):
    __tablename__ = "departments"
    
    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), unique=True, nullable=False)
    description = Column(Text)
    manager_id = Column(UUID(as_uuid=True), ForeignKey('employees.id'))
    
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)

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
class EmployeeCreate(BaseModel):
    user_id: str
    full_name: str
    document_number: str
    phone: str
    email: EmailStr
    roles: List[EmployeeRole]
    specialization: Optional[str] = None
    license_number: Optional[str] = None
    hire_date: date
    department: Optional[str] = None
    position: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    
    @validator('roles')
    def validate_roles(cls, v):
        if not v:
            raise ValueError('Debe asignar al menos un rol')
        return v
    
    @validator('document_number')
    def validate_document_number(cls, v):
        if not v or len(v) < 7:
            raise ValueError('Número de documento inválido')
        return v

class EmployeeUpdate(BaseModel):
    full_name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[EmailStr] = None
    roles: Optional[List[EmployeeRole]] = None
    specialization: Optional[str] = None
    license_number: Optional[str] = None
    department: Optional[str] = None
    position: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None

class EmployeeResponse(BaseModel):
    id: str
    employee_code: str
    full_name: str
    document_number: str
    phone: str
    email: str
    roles: List[str]
    specialization: Optional[str]
    license_number: Optional[str]
    hire_date: date
    department: Optional[str]
    position: Optional[str]
    created_at: datetime
    is_active: bool
    
    class Config:
        from_attributes = True

class WorkScheduleCreate(BaseModel):
    employee_id: str
    day_of_week: DayOfWeek
    start_time: time
    end_time: time
    break_start: Optional[time] = None
    break_end: Optional[time] = None
    
    @validator('end_time')
    def validate_times(cls, v, values):
        if 'start_time' in values and v <= values['start_time']:
            raise ValueError('Hora de fin debe ser posterior a hora de inicio')
        return v

class WorkScheduleResponse(BaseModel):
    id: str
    employee_id: str
    day_of_week: int
    start_time: time
    end_time: time
    break_start: Optional[time]
    break_end: Optional[time]
    is_active: bool
    
    class Config:
        from_attributes = True

class AvailabilityCreate(BaseModel):
    employee_id: str
    date: date
    start_time: time
    end_time: time
    is_available: bool = True
    reason: Optional[str] = None

class AvailabilityResponse(BaseModel):
    id: str
    employee_id: str
    date: date
    start_time: time
    end_time: time
    is_available: bool
    reason: Optional[str]
    
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

def check_admin_permission(user: dict):
    """Verificar que el usuario tiene permisos de administrador"""
    if user.get("user_type") not in ["admin", "manager"]:
        raise HTTPException(
            status_code=403,
            detail="No tiene permisos para realizar esta acción"
        )

# Funciones auxiliares
def generate_employee_code(db: Session) -> str:
    """Generar código único de empleado"""
    year = datetime.now().year
    # Buscar último empleado del año
    last_employee = db.query(Employee).filter(
        Employee.employee_code.like(f"EMP{year}%")
    ).order_by(Employee.employee_code.desc()).first()
    
    if last_employee:
        last_number = int(last_employee.employee_code[-4:])
        new_number = last_number + 1
    else:
        new_number = 1
    
    return f"EMP{year}{new_number:04d}"

# ENDPOINTS

@app.get("/health")
async def health_check():
    return {"status": "healthy", "service": "employees"}

@app.post("/employees", response_model=EmployeeResponse)
async def create_employee(
    employee: EmployeeCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Crear nuevo empleado"""
    check_admin_permission(current_user)
    
    # Verificar que no existe empleado con ese documento
    existing_employee = db.query(Employee).filter(
        Employee.document_number == employee.document_number
    ).first()
    
    if existing_employee:
        raise HTTPException(
            status_code=400,
            detail="Ya existe un empleado con ese número de documento"
        )
    
    # Verificar email único
    existing_email = db.query(Employee).filter(Employee.email == employee.email).first()
    if existing_email:
        raise HTTPException(
            status_code=400,
            detail="Ya existe un empleado con ese email"
        )
    
    # Generar código de empleado
    employee_code = generate_employee_code(db)
    
    # Crear empleado
    db_employee = Employee(
        user_id=employee.user_id,
        employee_code=employee_code,
        full_name=employee.full_name,
        document_number=employee.document_number,
        phone=employee.phone,
        email=employee.email,
        roles=json.dumps(employee.roles),  # Almacenar como JSON string
        specialization=employee.specialization,
        license_number=employee.license_number,
        hire_date=employee.hire_date,
        department=employee.department,
        position=employee.position,
        emergency_contact_name=employee.emergency_contact_name,
        emergency_contact_phone=employee.emergency_contact_phone
    )
    
    db.add(db_employee)
    db.commit()
    db.refresh(db_employee)
    
    # Convertir roles de JSON a lista para la respuesta
    response = EmployeeResponse.from_orm(db_employee)
    response.roles = json.loads(db_employee.roles)
    
    return response

@app.get("/employees", response_model=List[EmployeeResponse])
async def get_employees(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, le=100),
    role: Optional[EmployeeRole] = None,
    department: Optional[str] = None,
    is_active: Optional[bool] = None,
    search: Optional[str] = None
):
    """Obtener lista de empleados con filtros"""
    query = db.query(Employee)
    
    if is_active is not None:
        query = query.filter(Employee.is_active == is_active)
    
    if role:
        # Buscar en el JSON de roles
        query = query.filter(Employee.roles.contains(role))
    
    if department:
        query = query.filter(Employee.department.ilike(f"%{department}%"))
    
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            (Employee.full_name.ilike(search_pattern)) |
            (Employee.employee_code.ilike(search_pattern)) |
            (Employee.document_number.ilike(search_pattern)) |
            (Employee.email.ilike(search_pattern))
        )
    
    employees = query.order_by(Employee.created_at.desc()).offset(skip).limit(limit).all()
    
    # Convertir roles de JSON a lista para cada empleado
    response_list = []
    for emp in employees:
        emp_response = EmployeeResponse.from_orm(emp)
        emp_response.roles = json.loads(emp.roles) if emp.roles else []
        response_list.append(emp_response)
    
    return response_list

@app.get("/employees/{employee_id}", response_model=EmployeeResponse)
async def get_employee(
    employee_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Obtener empleado específico"""
    employee = db.query(Employee).filter(
        Employee.id == employee_id,
        Employee.is_active == True
    ).first()
    
    if not employee:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")
    
    response = EmployeeResponse.from_orm(employee)
    response.roles = json.loads(employee.roles) if employee.roles else []
    
    return response

@app.put("/employees/{employee_id}", response_model=EmployeeResponse)
async def update_employee(
    employee_id: str,
    employee_update: EmployeeUpdate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Actualizar empleado"""
    check_admin_permission(current_user)
    
    db_employee = db.query(Employee).filter(
        Employee.id == employee_id,
        Employee.is_active == True
    ).first()
    
    if not db_employee:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")
    
    # Verificar email único si se está actualizando
    if employee_update.email and employee_update.email != db_employee.email:
        existing_email = db.query(Employee).filter(
            Employee.email == employee_update.email,
            Employee.id != employee_id
        ).first()
        if existing_email:
            raise HTTPException(
                status_code=400,
                detail="Ya existe un empleado con ese email"
            )
    
    # Actualizar campos
    update_data = employee_update.dict(exclude_unset=True)
    for field, value in update_data.items():
        if field == 'roles':
            # Convertir lista de roles a JSON string
            setattr(db_employee, field, json.dumps(value))
        else:
            setattr(db_employee, field, value)
    
    db_employee.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(db_employee)
    
    response = EmployeeResponse.from_orm(db_employee)
    response.roles = json.loads(db_employee.roles) if db_employee.roles else []
    
    return response

@app.delete("/employees/{employee_id}")
async def deactivate_employee(
    employee_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Desactivar empleado (soft delete)"""
    check_admin_permission(current_user)
    
    db_employee = db.query(Employee).filter(
        Employee.id == employee_id,
        Employee.is_active == True
    ).first()
    
    if not db_employee:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")
    
    # Soft delete
    db_employee.is_active = False
    db_employee.updated_at = datetime.utcnow()
    db.commit()
    
    return {"message": "Empleado desactivado exitosamente"}

# ENDPOINTS DE HORARIOS

@app.post("/employees/{employee_id}/schedules", response_model=WorkScheduleResponse)
async def create_work_schedule(
    employee_id: str,
    schedule: WorkScheduleCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Crear horario de trabajo para empleado"""
    check_admin_permission(current_user)
    
    # Verificar que existe el empleado
    employee = db.query(Employee).filter(
        Employee.id == employee_id,
        Employee.is_active == True
    ).first()
    
    if not employee:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")
    
    # Verificar que no existe horario para ese día
    existing_schedule = db.query(WorkSchedule).filter(
        WorkSchedule.employee_id == employee_id,
        WorkSchedule.day_of_week == schedule.day_of_week,
        WorkSchedule.is_active == True
    ).first()
    
    if existing_schedule:
        raise HTTPException(
            status_code=400,
            detail="Ya existe un horario para ese día. Use actualizar para modificarlo."
        )
    
    # Crear horario
    db_schedule = WorkSchedule(
        employee_id=employee_id,
        day_of_week=schedule.day_of_week,
        start_time=schedule.start_time,
        end_time=schedule.end_time,
        break_start=schedule.break_start,
        break_end=schedule.break_end
    )
    
    db.add(db_schedule)
    db.commit()
    db.refresh(db_schedule)
    
    return WorkScheduleResponse.from_orm(db_schedule)

@app.get("/employees/{employee_id}/schedules", response_model=List[WorkScheduleResponse])
async def get_employee_schedules(
    employee_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Obtener horarios de trabajo del empleado"""
    schedules = db.query(WorkSchedule).filter(
        WorkSchedule.employee_id == employee_id,
        WorkSchedule.is_active == True
    ).order_by(WorkSchedule.day_of_week).all()
    
    return [WorkScheduleResponse.from_orm(schedule) for schedule in schedules]

@app.put("/schedules/{schedule_id}", response_model=WorkScheduleResponse)
async def update_work_schedule(
    schedule_id: str,
    schedule_update: WorkScheduleCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Actualizar horario de trabajo"""
    check_admin_permission(current_user)
    
    db_schedule = db.query(WorkSchedule).filter(
        WorkSchedule.id == schedule_id,
        WorkSchedule.is_active == True
    ).first()
    
    if not db_schedule:
        raise HTTPException(status_code=404, detail="Horario no encontrado")
    
    # Actualizar campos
    db_schedule.start_time = schedule_update.start_time
    db_schedule.end_time = schedule_update.end_time
    db_schedule.break_start = schedule_update.break_start
    db_schedule.break_end = schedule_update.break_end
    
    db.commit()
    db.refresh(db_schedule)
    
    return WorkScheduleResponse.from_orm(db_schedule)

@app.delete("/schedules/{schedule_id}")
async def delete_work_schedule(
    schedule_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Eliminar horario de trabajo"""
    check_admin_permission(current_user)
    
    db_schedule = db.query(WorkSchedule).filter(
        WorkSchedule.id == schedule_id,
        WorkSchedule.is_active == True
    ).first()
    
    if not db_schedule:
        raise HTTPException(status_code=404, detail="Horario no encontrado")
    
    # Soft delete
    db_schedule.is_active = False
    db.commit()
    
    return {"message": "Horario eliminado exitosamente"}

# ENDPOINTS DE DISPONIBILIDAD

@app.post("/employees/{employee_id}/availability", response_model=AvailabilityResponse)
async def create_availability(
    employee_id: str,
    availability: AvailabilityCreate,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Crear disponibilidad específica (vacaciones, permisos, etc.)"""
    # Verificar que existe el empleado
    employee = db.query(Employee).filter(
        Employee.id == employee_id,
        Employee.is_active == True
    ).first()
    
    if not employee:
        raise HTTPException(status_code=404, detail="Empleado no encontrado")
    
    # Solo admin o el mismo empleado pueden crear disponibilidad
    if (current_user.get("user_type") not in ["admin", "manager"] and 
        str(employee.user_id) != current_user.get("id")):
        raise HTTPException(
            status_code=403,
            detail="No tiene permisos para gestionar la disponibilidad de este empleado"
        )
    
    # Crear disponibilidad
    db_availability = EmployeeAvailability(
        employee_id=employee_id,
        date=availability.date,
        start_time=availability.start_time,
        end_time=availability.end_time,
        is_available=availability.is_available,
        reason=availability.reason
    )
    
    db.add(db_availability)
    db.commit()
    db.refresh(db_availability)
    
    return AvailabilityResponse.from_orm(db_availability)

@app.get("/employees/{employee_id}/availability")
async def get_employee_availability(
    employee_id: str,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user),
    date_from: Optional[date] = None,
    date_to: Optional[date] = None
):
    """Obtener disponibilidad del empleado"""
    query = db.query(EmployeeAvailability).filter(
        EmployeeAvailability.employee_id == employee_id
    )
    
    if date_from:
        query = query.filter(EmployeeAvailability.date >= date_from)
    
    if date_to:
        query = query.filter(EmployeeAvailability.date <= date_to)
    
    availability = query.order_by(EmployeeAvailability.date).all()
    
    return [AvailabilityResponse.from_orm(av) for av in availability]

# ENDPOINTS DE VETERINARIOS (para el servicio de citas)

@app.get("/veterinarians", response_model=List[EmployeeResponse])
async def get_veterinarians(
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Obtener lista de veterinarios activos"""
    veterinarians = db.query(Employee).filter(
        Employee.is_active == True,
        Employee.roles.contains('"veterinarian"')  # Buscar en JSON
    ).all()
    
    # Convertir roles de JSON a lista
    response_list = []
    for vet in veterinarians:
        vet_response = EmployeeResponse.from_orm(vet)
        vet_response.roles = json.loads(vet.roles) if vet.roles else []
        response_list.append(vet_response)
    
    return response_list

@app.get("/employees/{employee_id}/availability/{date}")
async def check_employee_availability_date(
    employee_id: str,
    date: date,
    db: Session = Depends(get_db),
    current_user = Depends(get_current_user)
):
    """Verificar disponibilidad de empleado en fecha específica"""
    # Obtener horario regular del empleado
    day_of_week = date.weekday()  # 0=Lunes, 6=Domingo
    
    regular_schedule = db.query(WorkSchedule).filter(
        WorkSchedule.employee_id == employee_id,
        WorkSchedule.day_of_week == day_of_week,
        WorkSchedule.is_active == True
    ).first()
    
    # Obtener disponibilidad específica para esa fecha
    specific_availability = db.query(EmployeeAvailability).filter(
        EmployeeAvailability.employee_id == employee_id,
        EmployeeAvailability.date == date
    ).first()
    
    if specific_availability:
        # Si hay disponibilidad específica, usar esa
        return {
            "date": date,
            "is_available": specific_availability.is_available,
            "start_time": specific_availability.start_time if specific_availability.is_available else None,
            "end_time": specific_availability.end_time if specific_availability.is_available else None,
            "reason": specific_availability.reason
        }
    elif regular_schedule:
        # Si no hay disponibilidad específica, usar horario regular
        return {
            "date": date,
            "is_available": True,
            "start_time": regular_schedule.start_time,
            "end_time": regular_schedule.end_time,
            "break_start": regular_schedule.break_start,
            "break_end": regular_schedule.break_end
        }
    else:
        # No hay horario para ese día
        return {
            "date": date,
            "is_available": False,
            "reason": "No hay horario asignado para este día"
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8007)