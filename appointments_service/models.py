from django.db import models
from shared.models import BaseModel
import uuid

class Appointment(BaseModel):
    """Citas médicas"""
    STATUS_CHOICES = [
        ('scheduled', 'Programada'),
        ('confirmed', 'Confirmada'), 
        ('in_progress', 'En Progreso'),
        ('completed', 'Completada'),
        ('cancelled', 'Cancelada'),
        ('no_show', 'No Asistió'),
        ('rescheduled', 'Reprogramada'),
    ]
    
    PRIORITY_CHOICES = [
        ('low', 'Baja'),
        ('normal', 'Normal'),
        ('high', 'Alta'),
        ('emergency', 'Emergencia'),
    ]
    
    # Referencias a otros servicios
    client_id = models.UUIDField()
    pet_id = models.UUIDField()
    veterinarian_id = models.UUIDField()
    service_id = models.UUIDField()
    
    # Información de la cita
    appointment_number = models.CharField(max_length=20, unique=True)
    scheduled_date = models.DateField()
    scheduled_time = models.TimeField()
    estimated_end_time = models.TimeField(null=True, blank=True)
    actual_start_time = models.DateTimeField(null=True, blank=True)
    actual_end_time = models.DateTimeField(null=True, blank=True)
    
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='scheduled')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='normal')
    
    # Detalles
    reason = models.TextField()  # Motivo de la consulta
    symptoms = models.TextField(blank=True)  # Síntomas reportados
    observations = models.TextField(blank=True)  # Observaciones del veterinario
    
    # Notificaciones
    reminder_sent = models.BooleanField(default=False)
    reminder_sent_at = models.DateTimeField(null=True, blank=True)
    confirmation_required = models.BooleanField(default=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    
    # Seguimiento
    follow_up_required = models.BooleanField(default=False)
    follow_up_date = models.DateField(null=True, blank=True)
    follow_up_notes = models.TextField(blank=True)
    
    def __str__(self):
        return f"Cita {self.appointment_number} - {self.scheduled_date} {self.scheduled_time}"
    
    def save(self, *args, **kwargs):
        if not self.appointment_number:
            # Generar número de cita automático
            last_appointment = Appointment.objects.filter(
                scheduled_date__year=self.scheduled_date.year
            ).order_by('appointment_number').last()
            
            if last_appointment:
                last_number = int(last_appointment.appointment_number[-6:])
                new_number = last_number + 1
            else:
                new_number = 1
            
            self.appointment_number = f"{self.scheduled_date.year}{new_number:06d}"
        
        super().save(*args, **kwargs)
    
    class Meta:
        db_table = 'appointments'
        ordering = ['scheduled_date', 'scheduled_time']
        indexes = [
            models.Index(fields=['scheduled_date', 'veterinarian_id']),
            models.Index(fields=['client_id']),
            models.Index(fields=['pet_id']),
        ]


class AppointmentSlot(BaseModel):
    """Disponibilidad de horarios para citas"""
    veterinarian_id = models.UUIDField()
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    is_available = models.BooleanField(default=True)
    max_appointments = models.IntegerField(default=1)
    current_appointments = models.IntegerField(default=0)
    notes = models.CharField(max_length=200, blank=True)
    
    class Meta:
        db_table = 'appointment_slots'
        unique_together = ['veterinarian_id', 'date', 'start_time']


class AppointmentHistory(BaseModel):
    """Historial de cambios en citas"""
    appointment = models.ForeignKey(Appointment, on_delete=models.CASCADE, related_name='history')
    changed_by_user_id = models.UUIDField()
    change_type = models.CharField(max_length=20, choices=[
        ('created', 'Creada'),
        ('updated', 'Actualizada'),
        ('confirmed', 'Confirmada'),
        ('cancelled', 'Cancelada'),
        ('completed', 'Completada'),
        ('rescheduled', 'Reprogramada'),
    ])
    old_values = models.JSONField(default=dict)
    new_values = models.JSONField(default=dict)
    reason = models.TextField(blank=True)
    
    class Meta:
        db_table = 'appointment_history'
        ordering = ['-created_at']


# =============================================================================
# MEDICAL RECORDS SERVICE MODELS
# =============================================================================

class MedicalRecord(BaseModel):
    """Historia clínica de la mascota"""
    pet_id = models.UUIDField(unique=True)
    
    # Información general
    blood_type = models.CharField(max_length=10, blank=True)
    microchip_number = models.CharField(max_length=50, blank=True)
    insurance_policy = models.CharField(max_length=100, blank=True)
    
    # Antecedentes
    medical_history = models.TextField(blank=True)
    surgical_history = models.TextField(blank=True)
    allergies = models.TextField(blank=True)
    chronic_conditions = models.TextField(blank=True)
    current_medications = models.TextField(blank=True)
    
    # Información reproductiva
    is_sterilized = models.BooleanField(default=False)
    sterilization_date = models.DateField(null=True, blank=True)
    last_heat_date = models.DateField(null=True, blank=True)
    
    # Datos de emergencia
    emergency_contact = models.TextField(blank=True)
    special_instructions = models.TextField(blank=True)
    
    def __str__(self):
        return f"Historia clínica - Pet {self.pet_id}"
    
    class Meta:
        db_table = 'medical_records'


class Consultation(BaseModel):
    """Consultas médicas individuales"""
    medical_record = models.ForeignKey(MedicalRecord, on_delete=models.CASCADE, related_name='consultations')
    appointment_id = models.UUIDField(unique=True)
    veterinarian_id = models.UUIDField()
    
    # Signos vitales
    weight = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    temperature = models.DecimalField(max_digits=4, decimal_places=1, null=True, blank=True)
    heart_rate = models.IntegerField(null=True, blank=True)
    respiratory_rate = models.IntegerField(null=True, blank=True)
    
    # Examen físico
    physical_exam = models.TextField()
    symptoms = models.TextField()
    diagnosis = models.TextField()
    differential_diagnosis = models.TextField(blank=True)
    
    # Tratamiento
    treatment_plan = models.TextField()
    prescribed_medications = models.TextField(blank=True)
    recommendations = models.TextField(blank=True)
    
    # Seguimiento
    next_visit_date = models.DateField(null=True, blank=True)
    follow_up_instructions = models.TextField(blank=True)
    
    # Archivos adjuntos
    attachments = models.JSONField(default=list)  # URLs de archivos
    
    class Meta:
        db_table = 'consultations'
        ordering = ['-created_at']


class Vaccination(BaseModel):
    """Registro de vacunas"""
    medical_record = models.ForeignKey(MedicalRecord, on_delete=models.CASCADE, related_name='vaccinations')
    veterinarian_id = models.UUIDField()
    
    vaccine_name = models.CharField(max_length=200)
    vaccine_brand = models.CharField(max_length=100)
    batch_number = models.CharField(max_length=50)
    vaccination_date = models.DateField()
    next_due_date = models.DateField()
    site_of_injection = models.CharField(max_length=100)
    reaction = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    
    class Meta:
        db_table = 'vaccinations'
        ordering = ['-vaccination_date']


class Laboratory(BaseModel):
    """Resultados de laboratorio"""
    consultation = models.ForeignKey(Consultation, on_delete=models.CASCADE, related_name='lab_results')
    
    test_type = models.CharField(max_length=100)
    test_name = models.CharField(max_length=200)
    sample_type = models.CharField(max_length=50)  # sangre, orina, heces, etc.
    collection_date = models.DateField()
    results_date = models.DateField()
    
    results = models.JSONField()  # Estructura flexible para diferentes tipos de exámenes
    reference_values = models.JSONField(default=dict)
    interpretation = models.TextField()
    veterinarian_notes = models.TextField(blank=True)
    
    # Archivos
    report_file_url = models.URLField(blank=True)
    images = models.JSONField(default=list)
    
    class Meta:
        db_table = 'laboratory_results'


class Surgery(BaseModel):
    """Registro de cirugías"""
    medical_record = models.ForeignKey(MedicalRecord, on_delete=models.CASCADE, related_name='surgeries')
    veterinarian_id = models.UUIDField()
    assistant_ids = models.JSONField(default=list)  # IDs de asistentes
    
    surgery_type = models.CharField(max_length=200)
    surgery_date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    
    # Pre-operatorio
    preoperative_assessment = models.TextField()
    anesthesia_protocol = models.TextField()
    complications_during_surgery = models.TextField(blank=True)
    
    # Post-operatorio
    postoperative_instructions = models.TextField()
    medications_prescribed = models.TextField()
    follow_up_date = models.DateField()
    suture_removal_date = models.DateField(null=True, blank=True)
    
    # Archivos
    surgical_report_url = models.URLField(blank=True)
    photos = models.JSONField(default=list)
    
    class Meta:
        db_table = 'surgeries'


class Prescription(BaseModel):
    """Recetas médicas"""
    consultation = models.ForeignKey(Consultation, on_delete=models.CASCADE, related_name='prescriptions')
    
    medication_name = models.CharField(max_length=200)
    dosage = models.CharField(max_length=100)
    frequency = models.CharField(max_length=100)
    duration = models.CharField(max_length=100)
    instructions = models.TextField()
    refills_allowed = models.IntegerField(default=0)
    refills_used = models.IntegerField(default=0)
    
    class Meta:
        db_table = 'prescriptions'