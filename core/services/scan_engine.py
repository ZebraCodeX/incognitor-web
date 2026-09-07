from django.utils import timezone
from datetime import timedelta
from core.models import (
    Scan,
    Broker,
    RemovalRequest,
    DataStopRequest,
    ActivityLog,
)
from core.services import EmailDeletionEngine, WebFormEngine
import logging

logger = logging.getLogger(__name__)


class ScanEngine:
    """Orchestrates a full privacy scan and deletion run for a user."""

    def __init__(self, scan_id):
        self.scan = Scan.objects.get(id=scan_id)
        self.personal_data = {
            "full_name": self.scan.full_name,
            "email": self.scan.email,
            "phone": self.scan.phone or "",
            "address": self.scan.address or "",
            "dob": "",
        }

    def run(self):
        """Execute the full scan - process each broker through its removal method."""
        from core.models import BrokerCategory

        if self.scan.status in [Scan.Status.RUNNING, Scan.Status.COMPLETED]:
            raise ValueError(f"Scan {self.scan.id} already in state {self.scan.status}")

        self.scan.status = Scan.Status.RUNNING
        self.scan.save()

        brokers = Broker.objects.filter(is_active=True)
        self.scan.total_brokers = brokers.count()
        self.scan.save()

        ActivityLog.objects.create(
            scan=self.scan,
            action="scan_started",
            details={"total_brokers": self.scan.total_brokers},
        )

        for broker in brokers:
            try:
                self._process_broker(broker)
            except Exception as e:
                logger.error(f"Failed processing {broker.name}: {e}")
                self.scan.failed_count += 1
                # Create failed removal request
                RemovalRequest.objects.update_or_create(
                    scan=self.scan,
                    broker=broker,
                    defaults={
                        "status": RemovalRequest.Status.FAILED,
                        "method": self._method_for(broker),
                        "error_message": str(e),
                    },
                )
                self.scan.completed_brokers += 1
                self.scan.save()

        self.scan.status = Scan.Status.COMPLETED
        self.scan.completed_at = timezone.now()

        # Schedule next scan if recurring
        if self.scan.is_recurring:
            self.scan.next_scan_date = timezone.now() + timedelta(
                days=self.scan.recurring_interval_days
            )

        self.scan.save()

        ActivityLog.objects.create(
            scan=self.scan,
            action="scan_completed",
            details={
                "found": self.scan.found_count,
                "removed": self.scan.removed_count,
                "failed": self.scan.failed_count,
            },
        )

        return self.scan

    def _method_for(self, broker):
        if broker.removal_method == "email":
            return RemovalRequest.Method.EMAIL
        if broker.removal_method == "web_form":
            return RemovalRequest.Method.WEB_FORM
        if broker.removal_method == "both":
            return RemovalRequest.Method.WEB_FORM
        return RemovalRequest.Method.MANUAL

    def _process_broker(self, broker):
        """Process a single broker."""
        method = self._method_for(broker)
        removal, created = RemovalRequest.objects.get_or_create(
            scan=self.scan,
            broker=broker,
            defaults={
                "method": method,
                "status": RemovalRequest.Status.PENDING,
            },
        )

        try:
            if broker.removal_method in ["email", "both"]:
                result = EmailDeletionEngine.send_request(
                    broker,
                    full_name=self.personal_data["full_name"],
                    email=self.personal_data["email"],
                    phone=self.personal_data["phone"],
                    address=self.personal_data["address"],
                    dob=self.personal_data["dob"],
                )
                removal.status = RemovalRequest.Status.SENT
                removal.response_data = {"email_result": result}
                removal.completed_at = timezone.now()
                removal.save()
                self.scan.removed_count += 1

            if broker.removal_method in ["web_form", "both"]:
                result = WebFormEngine().submit(broker, self.personal_data)
                removal.status = RemovalRequest.Status.SENT
                removal.response_data.update({"web_form_result": result})
                if result.get("page_text"):
                    removal.confirmation_code = result["page_text"][:200]
                removal.completed_at = timezone.now()
                removal.save()
                self.scan.removed_count += 1

            if broker.removal_method == "manual":
                removal.status = RemovalRequest.Status.NEEDS_MANUAL
                removal.save()
                self.scan.found_count += 1

            self.scan.completed_brokers += 1
            self.scan.save()

            ActivityLog.objects.create(
                scan=self.scan,
                action=f"broker_processed:{broker.slug}",
                details={"method": broker.removal_method, "status": removal.status},
            )

        except Exception as e:
            removal.status = RemovalRequest.Status.FAILED
            removal.error_message = str(e)
            removal.retry_count += 1
            removal.save()
            raise

    @staticmethod
    def submit_data_stop_request(user, broker, stop_selling=True, stop_sharing=True, stop_marketing=True):
        """Submit a 'stop selling my data' request to a broker."""
        profile = getattr(user, "profile", None)
        full_name = f"{user.first_name} {user.last_name}".strip()
        email = user.email

        result = EmailDeletionEngine.send_data_stop_request(
            broker,
            full_name=full_name,
            email=email,
            stop_selling=stop_selling,
            stop_sharing=stop_sharing,
            stop_marketing=stop_marketing,
        )

        stop_req, created = DataStopRequest.objects.update_or_create(
            user=user,
            broker=broker,
            defaults={
                "status": DataStopRequest.Status.SUBMITTED,
                "stop_selling": stop_selling,
                "stop_sharing": stop_sharing,
                "stop_marketing": stop_marketing,
                "confirmation_code": result.get("subject", ""),
            },
        )

        ActivityLog.objects.create(
            action="data_stop_submitted",
            details={"broker": broker.name, "user": user.username},
        )

        return stop_req
