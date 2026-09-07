from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib.auth import login, logout
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.utils import timezone
from django.db.models import Count, Q
import json

from .models import Broker, Scan, RemovalRequest, DataStopRequest, UserProfile, ActivityLog, BrokerCategory
from .forms import SignUpForm, UserProfileForm, ScanForm, DataStopForm
from .services.scan_engine import ScanEngine
from .models import Scan as ScanModel


def index(request):
    broker_count = Broker.objects.filter(is_active=True).count()
    return render(request, "core/index.html", {
        "broker_count": broker_count,
        "categories": BrokerCategory.choices,
    })


def signup(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            UserProfile.objects.create(
                user=user,
            )
            login(request, user)
            messages.success(request, "Welcome to Incognitor!")
            return redirect("dashboard")
    else:
        form = SignUpForm()
    return render(request, "core/auth/signup.html", {"form": form})


def logout_view(request):
    logout(request)
    return redirect("index")


@login_required
def dashboard(request):
    user = request.user
    profile = getattr(user, "profile", None)

    recent_scans = user.scans.all()[:5]
    data_stops = user.data_stops.all()[:5]
    total_removals = sum(s.removed_count for s in user.scans.all())
    total_found = sum(s.found_count for s in user.scans.all())

    ctx = {
        "profile": profile,
        "recent_scans": recent_scans,
        "data_stops": data_stops,
        "total_removals": total_removals,
        "total_found": total_found,
    }
    return render(request, "core/dashboard.html", ctx)


@login_required
def new_scan(request):
    if request.method == "POST":
        form = ScanForm(request.POST)
        if form.is_valid():
            scan = ScanModel.objects.create(
                user=request.user,
                full_name=form.cleaned_data["full_name"],
                email=form.cleaned_data["email"],
                phone=form.cleaned_data.get("phone", ""),
                address=form.cleaned_data.get("address", ""),
                is_recurring=form.cleaned_data.get("is_recurring", False),
            )
            return redirect("scan_detail", scan_id=scan.id)
    else:
        user = request.user
        profile = getattr(user, "profile", None)
        initial = {
            "full_name": f"{user.first_name} {user.last_name}".strip(),
            "email": user.email,
            "phone": profile.phone if profile else "",
            "address": profile.address if profile else "",
        }
        form = ScanForm(initial=initial)

    return render(request, "core/scan/new.html", {"form": form, "broker_count": Broker.objects.filter(is_active=True).count()})


@login_required
def scan_detail(request, scan_id):
    scan = get_object_or_404(ScanModel, id=scan_id, user=request.user)
    removal_requests = scan.requests.select_related("broker").all()

    # Group by status for the dashboard
    status_counts = {
        s: removal_requests.filter(status=s).count()
        for s in RemovalRequest.Status.values
    }

    # Check if the threading engine has completed the run
    still_processing = scan.status in [
        ScanModel.Status.PENDING,
        ScanModel.Status.RUNNING,
    ]

    return render(request, "core/scan/detail.html", {
        "scan": scan,
        "removal_requests": removal_requests,
        "status_counts": status_counts,
        "still_processing": still_processing,
    })


@login_required
@require_POST
def start_scan(request, scan_id):
    """Start a scan in a background thread (falls back to sync if needed)."""
    scan = get_object_or_404(ScanModel, id=scan_id, user=request.user)

    if scan.status in [ScanModel.Status.RUNNING, ScanModel.Status.COMPLETED]:
        return JsonResponse({"error": "Scan already started or finished"}, status=400)

    try:
        # Try to use Celery if configured
        from .tasks import run_scan as run_scan_task
        result = run_scan_task.delay(str(scan.id))
        scan.celery_task_id = result.id
        scan.save()
        return JsonResponse({"status": "started", "celery_task_id": result.id})
    except (ImportError, Exception) as e:
        # Fall back to background thread
        import threading
        from .services.scan_engine import ScanEngine

        def _run():
            try:
                ScanEngine(scan.id).run()
            except Exception as err:
                scan.refresh_from_db()
                scan.status = ScanModel.Status.FAILED
                scan.error_message = str(err)
                scan.save()

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        return JsonResponse({"status": "started", "mode": "thread"})


@login_required
def scan_status_api(request, scan_id):
    """API endpoint for the dashboard to poll scan progress."""
    scan = get_object_or_404(ScanModel, id=scan_id, user=request.user)
    by_status = (
        scan.requests.values("status").annotate(count=Count("id"))
    )
    status_map = {s["status"]: s["count"] for s in by_status}
    return JsonResponse({
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
    })


@login_required
def data_stops(request):
    """Manage 'stop selling my data' requests."""
    form = None
    if request.method == "POST":
        form = DataStopForm(request.POST)
        if form.is_valid():
            broker_ids = form.cleaned_data.get("broker_ids", [])
            for bid in broker_ids:
                broker = get_object_or_404(Broker, id=bid)
                try:
                    ScanEngine.submit_data_stop_request(
                        request.user,
                        broker,
                        stop_selling=form.cleaned_data.get("stop_selling", True),
                        stop_sharing=form.cleaned_data.get("stop_sharing", True),
                        stop_marketing=form.cleaned_data.get("stop_marketing", True),
                    )
                    messages.success(
                        request, f"Stop request submitted to {broker.name}"
                    )
                except Exception as e:
                    messages.error(
                        request, f"Failed to submit stop request to {broker.name}: {e}"
                    )
            return redirect("data_stops")

    existing_stops = DataStopRequest.objects.filter(user=request.user)
    existing_broker_ids = {str(ds.broker_id) for ds in existing_stops}

    available = Broker.objects.filter(is_active=True).exclude(
        id__in=existing_broker_ids
    )

    form = DataStopForm()
    form.fields["broker_ids"].choices = [
        (str(b.id), f"{b.name} ({b.category})") for b in available
    ]

    return render(request, "core/data_stops.html", {
        "form": form,
        "my_stops": existing_stops.select_related("broker"),
    })


@login_required
def brokers_list(request):
    brokers = Broker.objects.filter(is_active=True)
    category = request.GET.get("category")
    if category:
        brokers = brokers.filter(category=category)
    return render(request, "core/brokers.html", {
        "brokers": brokers,
        "categories": BrokerCategory.choices,
        "active_category": category,
    })


@login_required
def profile_view(request):
    profile = getattr(request.user, "profile", None)
    if request.method == "POST":
        if profile:
            profile_form = UserProfileForm(request.POST, instance=profile)
        else:
            profile_form = UserProfileForm(request.POST)
        if profile_form.is_valid():
            profile = profile_form.save(commit=False)
            profile.user = request.user
            profile.save()
            messages.success(request, "Profile updated")
            return redirect("profile")
    else:
        profile_form = UserProfileForm(instance=profile)
    return render(request, "core/profile.html", {"form": profile_form})
