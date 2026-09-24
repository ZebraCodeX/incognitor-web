"""Generate a VAPID key pair for Web Push.

    python manage.py generate_vapid_keys

Copy the printed values into your environment (VAPID_PUBLIC_KEY /
VAPID_PRIVATE_KEY) and set VAPID_ADMIN_EMAIL.
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Generate a VAPID public/private key pair for Web Push notifications."

    def handle(self, *args, **options):
        try:
            from py_vapid import Vapid01
        except ImportError:
            self.stderr.write(self.style.ERROR("pywebpush/py-vapid is not installed."))
            return

        vapid = Vapid01()
        vapid.generate_keys()
        private_key = vapid.private_key
        public_key = vapid.public_key

        from cryptography.hazmat.primitives import serialization

        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()
        # Uncompressed public key point, base64url (what browsers expect).
        import base64

        raw = public_key.public_bytes(
            encoding=serialization.Encoding.X962,
            format=serialization.PublicFormat.UncompressedPoint,
        )
        b64 = base64.urlsafe_b64encode(raw).rstrip(b"=").decode()

        self.stdout.write(self.style.SUCCESS("VAPID keys generated:\n"))
        self.stdout.write(f"VAPID_PUBLIC_KEY={b64}\n")
        self.stdout.write(f"VAPID_PRIVATE_KEY={private_pem}\n")
