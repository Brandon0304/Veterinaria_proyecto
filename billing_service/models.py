from django.db import models
from shared.models import BaseModel
from decimal import Decimal

class Invoice(BaseModel):
    """Facturas"""
    STATUS_CHOICES = [
        ('draft', 'Borrador'),
        ('sent', 'Enviada'),
        ('paid', 'Pagada'),
        ('partially_paid', 'Parcialmente Pagada'),
        ('overdue', 'Vencida'),
        ('cancelled', 'Cancelada'),
    ]
    
    PAYMENT_TERMS = [
        (0, 'Inmediato'),
        (15, '15 días'),
        (30, '30 días'),
        (60, '60 días'),
    ]
    
    # Referencias
    client_id = models.UUIDField()
    appointment_id = models.UUIDField(null=True, blank=True)
    
    # Información de factura
    invoice_number = models.CharField(max_length=20, unique=True)
    issue_date = models.DateField()
    due_date = models.DateField()
    payment_terms = models.IntegerField(choices=PAYMENT_TERMS, default=0)
    
    # Montos
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=19.00)  # IVA Colombia
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    
    # Estado y metadatos
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    notes = models.TextField(blank=True)
    internal_notes = models.TextField(blank=True)
    
    # DIAN (Colombia)
    dian_authorized = models.BooleanField(default=False)
    dian_cufe = models.CharField(max_length=100, blank=True)  # Código Único de Facturación Electrónica
    dian_qr_code = models.TextField(blank=True)
    
    def __str__(self):
        return f"Factura {self.invoice_number} - ${self.total_amount}"
    
    def calculate_totals(self):
        """Calcular totales de la factura"""
        # Calcular subtotal de items
        self.subtotal = sum(item.total for item in self.items.all())
        
        # Aplicar descuento
        self.discount_amount = (self.subtotal * self.discount_percentage) / 100
        subtotal_after_discount = self.subtotal - self.discount_amount
        
        # Calcular impuestos
        self.tax_amount = (subtotal_after_discount * self.tax_rate) / 100
        
        # Total final
        self.total_amount = subtotal_after_discount + self.tax_amount
        
        # Actualizar estado según pago
        if self.paid_amount >= self.total_amount:
            self.status = 'paid'
        elif self.paid_amount > 0:
            self.status = 'partially_paid'
        elif self.due_date < models.date.today() and self.status != 'paid':
            self.status = 'overdue'
    
    def save(self, *args, **kwargs):
        if not self.invoice_number:
            # Generar número de factura automático
            current_year = self.issue_date.year
            last_invoice = Invoice.objects.filter(
                issue_date__year=current_year
            ).order_by('invoice_number').last()
            
            if last_invoice:
                last_number = int(last_invoice.invoice_number[-6:])
                new_number = last_number + 1
            else:
                new_number = 1
            
            self.invoice_number = f"VET{current_year}{new_number:06d}"
        
        super().save(*args, **kwargs)
    
    class Meta:
        db_table = 'invoices'
        ordering = ['-created_at']


class InvoiceItem(BaseModel):
    """Items de factura"""
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='items')
    service_id = models.UUIDField()
    
    description = models.CharField(max_length=500)
    quantity = models.DecimalField(max_digits=8, decimal_places=2, default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    
    # Para servicios con descuento específico
    discount_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    # Información del servicio
    service_date = models.DateField()
    veterinarian_id = models.UUIDField(null=True, blank=True)
    
    def save(self, *args, **kwargs):
        # Calcular total del item
        subtotal = self.quantity * self.unit_price
        self.discount_amount = (subtotal * self.discount_percentage) / 100
        self.total = subtotal - self.discount_amount
        super().save(*args, **kwargs)
    
    class Meta:
        db_table = 'invoice_items'


class Payment(BaseModel):
    """Pagos recibidos"""
    PAYMENT_METHODS = [
        ('cash', 'Efectivo'),
        ('card', 'Tarjeta'),
        ('transfer', 'Transferencia'),
        ('check', 'Cheque'),
        ('paypal', 'PayPal'),
        ('nequi', 'Nequi'),
        ('daviplata', 'Daviplata'),
    ]
    
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='payments')
    
    # Información del pago
    payment_number = models.CharField(max_length=20, unique=True)
    payment_date = models.DateField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHODS)
    
    # Detalles específicos del método
    reference_number = models.CharField(max_length=100, blank=True)  # Para transferencias
    check_number = models.CharField(max_length=50, blank=True)  # Para cheques
    card_last_four = models.CharField(max_length=4, blank=True)  # Últimos 4 dígitos
    transaction_id = models.CharField(max_length=100, blank=True)  # ID de transacción
    
    # Metadatos
    received_by_user_id = models.UUIDField()
    notes = models.TextField(blank=True)
    
    def save(self, *args, **kwargs):
        if not self.payment_number:
            # Generar número de pago automático
            prefix = self.payment_method.upper()[:3]
            last_payment = Payment.objects.filter(
                payment_date__year=self.payment_date.year
            ).order_by('payment_number').last()
            
            if last_payment:
                last_number = int(last_payment.payment_number[-6:])
                new_number = last_number + 1
            else:
                new_number = 1
            
            self.payment_number = f"{prefix}{self.payment_date.year}{new_number:06d}"
        
        super().save(*args, **kwargs)
    
    class Meta:
        db_table = 'payments'


class PaymentPlan(BaseModel):
    """Planes de pago para servicios costosos"""
    STATUS_CHOICES = [
        ('active', 'Activo'),
        ('completed', 'Completado'),
        ('defaulted', 'En Mora'),
        ('cancelled', 'Cancelado'),
    ]
    
    invoice = models.OneToOneField(Invoice, on_delete=models.CASCADE, related_name='payment_plan')
    client_id = models.UUIDField()
    
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    down_payment = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    installments = models.IntegerField()
    installment_amount = models.DecimalField(max_digits=12, decimal_places=2)
    interest_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    
    start_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    
    class Meta:
        db_table = 'payment_plans'


class PaymentPlanInstallment(BaseModel):
    """Cuotas de planes de pago"""
    payment_plan = models.ForeignKey(PaymentPlan, on_delete=models.CASCADE, related_name='plan_installments')
    
    installment_number = models.IntegerField()
    due_date = models.DateField()
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    paid_date = models.DateField(null=True, blank=True)
    is_paid = models.BooleanField(default=False)
    late_fee = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    
    class Meta:
        db_table = 'payment_plan_installments'
        unique_together = ['payment_plan', 'installment_number']


# =============================================================================
# NOTIFICATIONS SERVICE MODELS
# =============================================================================

class NotificationTemplate(BaseModel):
    """Plantillas de notificaciones"""
    TEMPLATE_TYPES = [
        ('appointment_reminder', 'Recordatorio de Cita'),
        ('appointment_confirmation', 'Confirmación de Cita'),
        ('appointment_cancellation', 'Cancelación de Cita'),
        ('vaccination_reminder', 'Recordatorio de Vacuna'),
        ('invoice_generated', 'Factura Generada'),
        ('payment_received', 'Pago Recibido'),
        ('medical_report', 'Reporte Médico'),
        ('birthday_greeting', 'Felicitación de Cumpleaños'),
        ('welcome_message', 'Mensaje de Bienvenida'),
    ]
    
    CHANNELS = [
        ('email', 'Email'),
        ('whatsapp', 'WhatsApp'),
        ('sms', 'SMS'),
        ('push', 'Notificación Push'),
    ]
    
    name = models.CharField(max_length=200)
    template_type = models.CharField(max_length=50, choices=TEMPLATE_TYPES)
    channel = models.CharField(max_length=20, choices=CHANNELS)
    
    # Contenido de la plantilla
    subject = models.CharField(max_length=200, blank=True)  # Para email
    message_template = models.TextField()
    whatsapp_template_name = models.CharField(max_length=100, blank=True)  # Para WhatsApp Business
    
    # Variables disponibles
    available_variables = models.JSONField(default=list)  # ej: ['client_name', 'pet_name', 'appointment_date']
    
    # Configuración
    is_active = models.BooleanField(default=True)
    send_immediately = models.BooleanField(default=False)
    send_delay_minutes = models.IntegerField(default=0)  # Retraso antes de enviar
    
    class Meta:
        db_table = 'notification_templates'


class Notification(BaseModel):
    """Registro de notificaciones enviadas"""
    STATUS_CHOICES = [
        ('pending', 'Pendiente'),
        ('sent', 'Enviada'),
        ('delivered', 'Entregada'),
        ('read', 'Leída'),
        ('failed', 'Fallida'),
        ('cancelled', 'Cancelada'),
    ]
    
    template = models.ForeignKey(NotificationTemplate, on_delete=models.CASCADE)
    
    # Destinatario
    recipient_type = models.CharField(max_length=20, choices=[
        ('client', 'Cliente'),
        ('employee', 'Empleado'),
    ])
    recipient_id = models.UUIDField()
    recipient_email = models.EmailField(blank=True)
    recipient_phone = models.CharField(max_length=15, blank=True)
    
    # Contenido personalizado
    subject = models.CharField(max_length=200)
    message = models.TextField()
    
    # Estado de envío
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    scheduled_at = models.DateTimeField()
    sent_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    
    # Metadatos
    attempt_count = models.IntegerField(default=0)
    last_error = models.TextField(blank=True)
    external_id = models.CharField(max_length=100, blank=True)  # ID del proveedor de SMS/WhatsApp
    
    # Referencias
    related_model = models.CharField(max_length=50, blank=True)  # ej: 'appointment', 'invoice'
    related_id = models.UUIDField(null=True, blank=True)
    
    class Meta:
        db_table = 'notifications'
        ordering = ['-created_at']


class WhatsAppMessage(BaseModel):
    """Mensajes de WhatsApp específicos"""
    notification = models.OneToOneField(Notification, on_delete=models.CASCADE, related_name='whatsapp_message')
    
    # Información específica de WhatsApp
    whatsapp_id = models.CharField(max_length=100)  # ID de WhatsApp Business
    template_name = models.CharField(max_length=100)
    template_parameters = models.JSONField(default=list)
    
    # Estado de WhatsApp
    wa_message_id = models.CharField(max_length=100, blank=True)
    wa_status = models.CharField(max_length=50, blank=True)
    wa_timestamp = models.BigIntegerField(null=True)  # Timestamp de WhatsApp
    
    class Meta:
        db_table = 'whatsapp_messages'


class EmailMessage(BaseModel):
    """Emails específicos con tracking avanzado"""
    notification = models.OneToOneField(Notification, on_delete=models.CASCADE, related_name='email_message')
    
    # Información del email
    email_provider = models.CharField(max_length=50, default='smtp')  # smtp, sendgrid, mailgun, etc.
    message_id = models.CharField(max_length=200, blank=True)
    
    # Tracking
    opened_at = models.DateTimeField(null=True, blank=True)
    clicked_at = models.DateTimeField(null=True, blank=True)
    bounced_at = models.DateTimeField(null=True, blank=True)
    bounce_reason = models.TextField(blank=True)
    
    # Archivos adjuntos
    attachments = models.JSONField(default=list)  # URLs de archivos adjuntos
    
    class Meta:
        db_table = 'email_messages'