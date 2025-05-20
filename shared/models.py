# shared/models.py - Modelos base compartidos
from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
import uuid

class BaseModel(models.Model):
    """Modelo base con campos comunes"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        abstract = True

# =============================================================================
# AUTH SERVICE MODELS
# =============================================================================

class CustomUser(AbstractUser):
    """Usuario extendido para el sistema"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    phone = models.CharField(max_length=15, blank=True)
    user_type = models.CharField(max_length=20, choices=[
        ('client', 'Cliente'),
        ('employee', 'Empleado'),
        ('admin', 'Administrador')
    ], default='client')
    is_verified = models.BooleanField(default=False)
    
    class Meta:
        db_table = 'auth_users'

# =============================================================================
# CLIENTS & PETS SERVICE MODELS  
# =============================================================================

class Client(BaseModel):
    """Clientes/Propietarios de mascotas"""
    user_id = models.UUIDField(unique=True)  # Referencia al usuario en auth_service
    document_type = models.CharField(max_length=10, choices=[
        ('CC', 'Cédula'),
        ('CE', 'Cédula Extranjera'),
        ('PAS', 'Pasaporte'),
        ('NIT', 'NIT')
    ])
    document_number = models.CharField(max_length=20, unique=True)
    full_name = models.CharField(max_length=200)
    email = models.EmailField()
    phone = models.CharField(max_length=15, validators=[
        RegexValidator(regex=r'^\+?1?\d{9,15}$', message="Formato inválido")
    ])
    whatsapp = models.CharField(max_length=15, blank=True)
    address = models.TextField()
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    emergency_contact_name = models.CharField(max_length=200, blank=True)
    emergency_contact_phone = models.CharField(max_length=15, blank=True)
    
    def __str__(self):
        return f"{self.full_name} - {self.document_number}"
    
    class Meta:
        db_table = 'clients'
        verbose_name = 'Cliente'
        verbose_name_plural = 'Clientes'


class Pet(BaseModel):
    """Mascotas"""
    SPECIES_CHOICES = [
        ('dog', 'Perro'),
        ('cat', 'Gato'),
        ('bird', 'Ave'),
        ('reptile', 'Reptil'),
        ('rodent', 'Roedor'),
        ('rabbit', 'Conejo'),
        ('other', 'Otro')
    ]
    
    GENDER_CHOICES = [
        ('M', 'Macho'),
        ('F', 'Hembra')
    ]
    
    name = models.CharField(max_length=100)
    species = models.CharField(max_length=20, choices=SPECIES_CHOICES)
    breed = models.CharField(max_length=100)
    gender = models.CharField(max_length=1, choices=GENDER_CHOICES)
    birth_date = models.DateField(null=True, blank=True)
    estimated_age_months = models.IntegerField(null=True, blank=True)
    color = models.CharField(max_length=100)
    weight = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    microchip = models.CharField(max_length=50, unique=True, null=True, blank=True)
    is_sterilized = models.BooleanField(default=False)
    
    # Relación con cliente
    owner = models.ForeignKey(Client, on_delete=models.CASCADE, related_name='pets')
    
    # Información adicional
    observations = models.TextField(blank=True)
    photo = models.URLField(blank=True)  # URL de la foto almacenada
    
    def __str__(self):
        return f"{self.name} ({self.get_species_display()}) - {self.owner.full_name}"
    
    @property
    def current_age_months(self):
        if self.birth_date:
            from django.utils import timezone
            today = timezone.now().date()
            return (today - self.birth_date).days // 30
        return self.estimated_age_months
    
    class Meta:
        db_table = 'pets'
        verbose_name = 'Mascota'
        verbose_name_plural = 'Mascotas'


# =============================================================================
# EMPLOYEES SERVICE MODELS
# =============================================================================

class Employee(BaseModel):
    """Empleados de la clínica"""
    ROLES = [
        ('admin', 'Administrador'),
        ('veterinarian', 'Veterinario'),
        ('receptionist', 'Recepcionista'),
        ('assistant', 'Auxiliar'),
        ('groomer', 'Peluquero'),
    ]
    
    user_id = models.UUIDField(unique=True)  # Referencia al usuario
    employee_code = models.CharField(max_length=20, unique=True)
    full_name = models.CharField(max_length=200)
    document_number = models.CharField(max_length=20, unique=True)
    phone = models.CharField(max_length=15)
    email = models.EmailField()
    roles = models.JSONField(default=list)  # Lista de roles
    specialization = models.CharField(max_length=200, blank=True)  # Para veterinarios
    license_number = models.CharField(max_length=50, blank=True)  # Tarjeta profesional
    hire_date = models.DateField()
    salary = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    
    def __str__(self):
        return f"{self.full_name} - {self.employee_code}"
    
    def has_role(self, role):
        return role in self.roles
    
    def is_veterinarian(self):
        return 'veterinarian' in self.roles
    
    class Meta:
        db_table = 'employees'
        verbose_name = 'Empleado'
        verbose_name_plural = 'Empleados'


class WorkSchedule(BaseModel):
    """Horarios de trabajo de empleados"""
    DAYS_OF_WEEK = [
        (0, 'Lunes'),
        (1, 'Martes'),
        (2, 'Miércoles'),
        (3, 'Jueves'),
        (4, 'Viernes'),
        (5, 'Sábado'),
        (6, 'Domingo'),
    ]
    
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='schedules')
    day_of_week = models.IntegerField(choices=DAYS_OF_WEEK)
    start_time = models.TimeField()
    end_time = models.TimeField()
    break_start = models.TimeField(null=True, blank=True)
    break_end = models.TimeField(null=True, blank=True)
    
    class Meta:
        db_table = 'work_schedules'
        unique_together = ['employee', 'day_of_week']


# =============================================================================
# SERVICES MODELS (Shared between appointments and billing)
# =============================================================================

class VeterinaryService(BaseModel):
    """Servicios veterinarios disponibles"""
    SERVICE_TYPES = [
        ('consultation', 'Consulta General'),
        ('vaccination', 'Vacunación'),
        ('surgery', 'Cirugía'),
        ('emergency', 'Emergencia'),
        ('grooming', 'Estética'),
        ('laboratory', 'Laboratorio'),
        ('radiology', 'Radiología'),
        ('hospitalization', 'Hospitalización'),
        ('dentistry', 'Odontología'),
        ('dermatology', 'Dermatología'),
    ]
    
    name = models.CharField(max_length=200)
    service_type = models.CharField(max_length=20, choices=SERVICE_TYPES)
    description = models.TextField()
    base_price = models.DecimalField(max_digits=10, decimal_places=2)
    estimated_duration_minutes = models.IntegerField()
    requires_appointment = models.BooleanField(default=True)
    available_for_species = models.JSONField(default=list)  # Lista de especies
    requires_fasting = models.BooleanField(default=False)
    preparation_instructions = models.TextField(blank=True)
    
    def __str__(self):
        return f"{self.name} - ${self.base_price}"
    
    class Meta:
        db_table = 'veterinary_services'
        verbose_name = 'Servicio Veterinario'
        verbose_name_plural = 'Servicios Veterinarios'