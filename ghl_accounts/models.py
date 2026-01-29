from django.db import models

# Create your models here.

class GHLAuthCredentials(models.Model):
    user_id = models.CharField(max_length=255, null=True, blank=True)
    access_token = models.TextField()
    refresh_token = models.TextField()
    expires_in = models.IntegerField()
    scope = models.TextField(null=True, blank=True)
    user_type = models.CharField(max_length=50, null=True, blank=True)
    company_id = models.CharField(max_length=255, null=True, blank=True)
    location_id = models.CharField(max_length=255, null=True, blank=True)

    def __str__(self):
        return f"{self.user_id} - {self.company_id} - {self.location_id}"
    
    
class ContactSync(models.Model):
    ghl_contact_id = models.CharField(max_length=100, null=True, blank=True, unique=True)
    ephysio_patient_id = models.CharField(max_length=100, null=True, blank=True, unique=True)

    # Contact information
    email = models.EmailField(null=True, blank=True)
    phone = models.CharField(max_length=20, null=True, blank=True)
    
    # Patient details from ephysio
    first_name = models.CharField(max_length=100, null=True, blank=True)
    last_name = models.CharField(max_length=100, null=True, blank=True)
    salutation = models.CharField(max_length=20, null=True, blank=True)
    street = models.CharField(max_length=200, null=True, blank=True)
    zip = models.CharField(max_length=20, null=True, blank=True)
    city = models.CharField(max_length=100, null=True, blank=True)
    birth_date = models.CharField(max_length=20, null=True, blank=True)  # Storing as string since format is "DD.MM.YYYY"
    sex = models.BooleanField(null=True, blank=True)

    source = models.CharField(
        max_length=20,
        choices=(("ghl", "GHL"), ("ephysio", "EPHYSIO"))
    )

    last_synced_at = models.DateTimeField(auto_now=True)

    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        name = f"{self.first_name} {self.last_name}".strip() or "Unknown"
        return f"{name} | GHL: {self.ghl_contact_id or 'N/A'} | ePhysio: {self.ephysio_patient_id or 'N/A'}"
    
class AppointmentSync(models.Model):
    ghl_appointment_id = models.CharField(max_length=100, null=True, blank=True, unique=True)

    # link to patient
    ghl_contact_id = models.CharField(max_length=100, null=True, blank=True)
    ephysio_patient_id = models.CharField(max_length=100)

    # appointment mapping
    ephysio_appointment_id = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        unique=True
    )

    start_time = models.DateTimeField()
    end_time = models.DateTimeField()

    status = models.CharField(
        max_length=30,
        null=True,
        blank=True
    )
    
    # Additional fields from ephysio
    event_type_id = models.IntegerField(null=True, blank=True)
    user_id = models.IntegerField(null=True, blank=True)
    client_id = models.IntegerField(null=True, blank=True)
    admin_info_id = models.IntegerField(null=True, blank=True)

    source = models.CharField(
        max_length=20,
        choices=(("ghl", "GHL"), ("ephysio", "EPHYSIO")),
        default="ephysio"
    )

    last_synced_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        appt_id = self.ghl_appointment_id or self.ephysio_appointment_id or "N/A"
        return f"Appt: {appt_id} | Patient: {self.ephysio_patient_id}"