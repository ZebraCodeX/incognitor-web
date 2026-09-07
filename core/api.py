from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.contrib.auth.models import User
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.db.models import Count

from .models import Broker, Scan, RemovalRequest, DataStopRequest, ActivityLog, UserProfile
from .serializers import (
    UserSerializer,
    UserProfileSerializer,
    BrokerSerializer,
    ScanSerializer,
    RemovalRequestSerializer,
    DataStopRequestSerializer,
    ActivityLogSerializer,
)
from .services.scan_engine import ScanEngine


class AuthViewSet(viewsets.ViewSet):
    permission_classes = [AllowAny]

    @action(detail=False, methods=["post"])
    def login(self, request):
        from django.contrib.auth import authenticate, login
        user = authenticate(
            username=request.data.get("username"),
            password=request.data.get("password"),
        )
        if user:
            login(request, user)
            return Response(UserSerializer(user).data)
        return Response({"error": "Invalid credentials"}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["post"])
    def signup(self, request):
        data = request.data
        username = data.get("username")
        email = data.get("email")
        password = data.get("password1")
        password2 = data.get("password2")

        if not username or not email or not password:
            return Response({"error": "Username, email, and password are required"}, status=400)
        if password != password2:
            return Response({"error": "Passwords do not match"}, status=400)
        if User.objects.filter(username=username).exists():
            return Response({"error": "Username already taken"}, status=400)
        if User.objects.filter(email=email).exists():
            return Response({"error": "Email already registered"}, status=400)

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=data.get("first_name", ""),
            last_name=data.get("last_name", ""),
        )
        UserProfile.objects.create(user=user)
        from django.contrib.auth import login
        login(request, user)
        return Response(UserSerializer(user).data, status=201)

    @action(detail=False, methods=["post"])
    def logout(self, request):
        from django.contrib.auth import logout
        logout(request)
        return Response({"status": "ok"})


class BrokerViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Broker.objects.filter(is_active=True)
    serializer_class = BrokerSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        category = self.request.query_params.get("category")
        if category:
            qs = qs.filter(category=category)
        return qs


class ScanViewSet(viewsets.ModelViewSet):
    serializer_class = ScanSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Scan.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        scan = serializer.save(user=self.request.user)
        # Auto-start the scan in the background
        try:
            from .tasks import run_scan as run_scan_task
            result = run_scan_task.delay(str(scan.id))
            scan.celery_task_id = result.id
            scan.save(update_fields=["celery_task_id"])
        except Exception:
            import threading

            scan_ref = scan.id

            def _run():
                try:
                    ScanEngine(scan_ref).run()
                except Exception as e:
                    s = Scan.objects.get(id=scan_ref)
                    s.status = Scan.Status.FAILED
                    s.error_message = str(e)
                    s.save()

            threading.Thread(target=_run, daemon=True).start()

    @action(detail=True, methods=["post"])
    def start(self, request, pk=None):
        scan = self.get_object()
        if scan.status in [Scan.Status.RUNNING, Scan.Status.COMPLETED]:
            return Response(
                {"error": f"Scan already {scan.status}"}, status=400
            )
        try:
            from .tasks import run_scan as run_scan_task
            result = run_scan_task.delay(str(scan.id))
            scan.celery_task_id = result.id
            scan.save(update_fields=["celery_task_id"])
            return Response({"status": "started", "celery_task_id": result.id})
        except Exception:
            import threading

            scan_id = scan.id

            def _run():
                try:
                    ScanEngine(scan_id).run()
                except Exception as e:
                    s = Scan.objects.get(id=scan_id)
                    s.status = Scan.Status.FAILED
                    s.error_message = str(e)
                    s.save()

            threading.Thread(target=_run, daemon=True).start()
            return Response({"status": "started", "mode": "thread"})

    @action(detail=True, methods=["get"])
    def status(self, request, pk=None):
        scan = self.get_object()
        by_status = (
            scan.requests.values("status").annotate(count=Count("id"))
        )
        status_map = {s["status"]: s["count"] for s in by_status}
        return Response({
            "id": str(scan.id),
            "status": scan.status,
            "progress_percent": scan.progress_percent,
            "total_brokers": scan.total_brokers,
            "completed_brokers": scan.completed_brokers,
            "removed_count": scan.removed_count,
            "found_count": scan.found_count,
            "failed_count": scan.failed_count,
            "by_status": status_map,
            "error_message": scan.error_message,
            "requests": RemovalRequestSerializer(
                scan.requests.select_related("broker").all(), many=True
            ).data,
        })


class DataStopViewSet(viewsets.ModelViewSet):
    serializer_class = DataStopRequestSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return DataStopRequest.objects.filter(user=self.request.user).select_related("broker")

    def perform_create(self, serializer):
        broker = get_object_or_404(Broker, id=self.request.data.get("broker_id"))
        try:
            result = ScanEngine.submit_data_stop_request(
                self.request.user,
                broker,
                stop_selling=serializer.validated_data.get("stop_selling", True),
                stop_sharing=serializer.validated_data.get("stop_sharing", True),
                stop_marketing=serializer.validated_data.get("stop_marketing", True),
            )
            return Response(DataStopRequestSerializer(result).data, status=201)
        except Exception as e:
            serializer.save(
                user=self.request.user,
                broker=broker,
                status=DataStopRequest.Status.FAILED,
                notes=str(e),
            )

    @action(detail=False, methods=["post"])
    def bulk_submit(self, request):
        broker_ids = request.data.get("broker_ids", [])
        stop_selling = request.data.get("stop_selling", True)
        stop_sharing = request.data.get("stop_sharing", True)
        stop_marketing = request.data.get("stop_marketing", True)

        results = []
        for bid in broker_ids:
            broker = get_object_or_404(Broker, id=bid)
            try:
                result = ScanEngine.submit_data_stop_request(
                    request.user, broker,
                    stop_selling=stop_selling,
                    stop_sharing=stop_sharing,
                    stop_marketing=stop_marketing,
                )
                results.append({"broker": broker.name, "status": "submitted"})
            except Exception as e:
                results.append({"broker": broker.name, "status": "failed", "error": str(e)})

        return Response({"results": results})


class ProfileViewSet(viewsets.ModelViewSet):
    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return UserProfile.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class ActivityViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = ActivityLogSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        qs = ActivityLog.objects.all()
        scan_id = self.request.query_params.get("scan")
        if scan_id:
            qs = qs.filter(scan_id=scan_id)
        return qs[:50]