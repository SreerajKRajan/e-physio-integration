from django.db import models

class EPhysioAuth(models.Model):
    token = models.TextField()
    crypto_key = models.CharField(max_length=255)
    practice_id = models.CharField(max_length=50)
    expires_at = models.BigIntegerField(null=True, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"EPhysio ({self.practice_id})"
