import re
from datetime import datetime

from flask import Blueprint, request, jsonify
from flask_login import login_user, logout_user, login_required, current_user

from extensions import db
from models import User, DoctorRequest

EMAIL_REGEX = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")
PHONE_REGEX = re.compile(r"^[0-9]{10}$")

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def is_valid_email(email):
    return bool(email) and bool(EMAIL_REGEX.match(email))


@auth_bp.post("/signup")
def signup():
    data = request.get_json(force=True) or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    role = data.get("role") if data.get("role") in ("doctor", "patient") else "patient"
    specialty = data.get("specialty")  # relevant if role == doctor

    if not name or not email or not password:
        return jsonify({"error": "name, email and password are required"}), 400

    if not is_valid_email(email):
        return jsonify({"error": "Please enter a valid email address"}), 400

    if User.query.filter_by(email=email).first():
        return jsonify({"error": "An account with this email already exists"}), 409

    dob = None
    phone = None

    if role == "patient":
        dob_str = (data.get("dob") or "").strip()
        phone = (data.get("phone") or "").strip() or None

        if not dob_str:
            return jsonify({"error": "Date of birth is required for patients"}), 400
        try:
            dob = datetime.strptime(dob_str, "%Y-%m-%d").date()
        except ValueError:
            return jsonify({"error": "Date of birth must be in YYYY-MM-DD format"}), 400

        if dob >= datetime.utcnow().date():
            return jsonify({"error": "Date of birth must be in the past"}), 400

        if phone and not PHONE_REGEX.match(phone):
            return jsonify({"error": "Phone number must be exactly 10 digits"}), 400

    user = User(
        name=name,
        email=email,
        role=role,
        specialty=specialty if role == "doctor" else None,
        dob=dob,
        phone=phone,
    )
    user.set_password(password)

    # NOTE: patients are no longer auto-assigned to a doctor at signup.
    # They now browse doctors and send a request; the doctor must accept
    # it before assigned_doctor_id gets set (see /doctors, /request-doctor,
    # and /requests/<id>/accept below).

    db.session.add(user)
    db.session.commit()
    login_user(user)
    return jsonify({"message": "Account created", "user": user.to_dict()}), 201


@auth_bp.post("/login")
def login():
    data = request.get_json(force=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""

    if not is_valid_email(email):
        return jsonify({"error": "Please enter a valid email address"}), 400

    user = User.query.filter_by(email=email).first()
    if not user or not user.check_password(password):
        return jsonify({"error": "Invalid email or password"}), 401

    login_user(user)
    return jsonify({"message": "Logged in", "user": user.to_dict()})


@auth_bp.post("/logout")
@login_required
def logout():
    logout_user()
    return jsonify({"message": "Logged out"})


@auth_bp.get("/me")
@login_required
def me():
    """Used by the home page to show the logged-in user + their assigned doctor."""
    return jsonify({"user": current_user.to_dict()})


@auth_bp.get("/my-patients")
@login_required
def my_patients():
    """Used by the dashboard so a doctor can pick which patient to upload a scan for."""
    if current_user.role != "doctor":
        return jsonify({"error": "Only doctors can view their patient list"}), 403

    patients = (
        User.query.filter_by(role="patient", assigned_doctor_id=current_user.id)
        .order_by(User.name.asc())
        .all()
    )
    return jsonify({
        "patients": [{"id": p.id, "name": p.name, "email": p.email} for p in patients]
    })


@auth_bp.get("/doctors")
@login_required
def list_doctors():
    """Used by patients to browse doctors they can send a request to."""
    if current_user.role != "patient":
        return jsonify({"error": "Only patients can browse doctors"}), 403

    doctors = User.query.filter_by(role="doctor").order_by(User.name.asc()).all()

    existing = {
        r.doctor_id: r.status
        for r in DoctorRequest.query.filter_by(patient_id=current_user.id)
        .filter(DoctorRequest.status.in_(["pending", "accepted"]))
        .all()
    }

    return jsonify({
        "doctors": [
            {
                "id": d.id,
                "name": d.name,
                "specialty": d.specialty,
                "request_status": existing.get(d.id),
            }
            for d in doctors
        ]
    })


@auth_bp.post("/request-doctor")
@login_required
def request_doctor():
    """Patient sends a request to be taken on by a specific doctor."""
    if current_user.role != "patient":
        return jsonify({"error": "Only patients can request a doctor"}), 403

    if current_user.assigned_doctor_id:
        return jsonify({"error": "You already have an assigned doctor"}), 400

    data = request.get_json(force=True) or {}
    doctor_id = data.get("doctor_id")
    doctor = User.query.filter_by(id=doctor_id, role="doctor").first()
    if not doctor:
        return jsonify({"error": "Valid doctor_id is required"}), 400

    already_pending = DoctorRequest.query.filter_by(
        patient_id=current_user.id, doctor_id=doctor.id, status="pending"
    ).first()
    if already_pending:
        return jsonify({"error": "You already have a pending request with this doctor"}), 409

    req = DoctorRequest(patient_id=current_user.id, doctor_id=doctor.id)
    db.session.add(req)
    db.session.commit()
    return jsonify({"message": "Request sent", "request": req.to_dict()}), 201


@auth_bp.get("/my-requests")
@login_required
def my_requests():
    """Patient checks the status of the request(s) they've sent."""
    if current_user.role != "patient":
        return jsonify({"error": "Only patients can view their requests"}), 403

    reqs = (
        DoctorRequest.query.filter_by(patient_id=current_user.id)
        .order_by(DoctorRequest.created_at.desc())
        .all()
    )
    return jsonify({"requests": [r.to_dict() for r in reqs]})


@auth_bp.get("/pending-requests")
@login_required
def pending_requests():
    """Doctor views incoming patient requests waiting on their decision."""
    if current_user.role != "doctor":
        return jsonify({"error": "Only doctors can view pending requests"}), 403

    reqs = (
        DoctorRequest.query.filter_by(doctor_id=current_user.id, status="pending")
        .order_by(DoctorRequest.created_at.asc())
        .all()
    )
    return jsonify({"requests": [r.to_dict() for r in reqs]})


@auth_bp.post("/requests/<int:request_id>/accept")
@login_required
def accept_request(request_id):
    """Doctor accepts a patient's request - this is what actually assigns
    the patient to the doctor."""
    if current_user.role != "doctor":
        return jsonify({"error": "Only doctors can accept requests"}), 403

    req = DoctorRequest.query.get_or_404(request_id)
    if req.doctor_id != current_user.id:
        return jsonify({"error": "This request was not sent to you"}), 403
    if req.status != "pending":
        return jsonify({"error": f"Request already {req.status}"}), 400

    req.status = "accepted"
    req.responded_at = datetime.utcnow()

    patient = User.query.get(req.patient_id)
    patient.assigned_doctor_id = current_user.id

    # Auto-reject any other pending requests this patient sent out, since
    # they can only have one doctor.
    DoctorRequest.query.filter(
        DoctorRequest.patient_id == req.patient_id,
        DoctorRequest.id != req.id,
        DoctorRequest.status == "pending",
    ).update({"status": "rejected", "responded_at": datetime.utcnow()})

    db.session.commit()
    return jsonify({"message": "Request accepted", "request": req.to_dict()})


@auth_bp.post("/requests/<int:request_id>/reject")
@login_required
def reject_request(request_id):
    """Doctor declines a patient's request."""
    if current_user.role != "doctor":
        return jsonify({"error": "Only doctors can reject requests"}), 403

    req = DoctorRequest.query.get_or_404(request_id)
    if req.doctor_id != current_user.id:
        return jsonify({"error": "This request was not sent to you"}), 403
    if req.status != "pending":
        return jsonify({"error": f"Request already {req.status}"}), 400

    req.status = "rejected"
    req.responded_at = datetime.utcnow()
    db.session.commit()
    return jsonify({"message": "Request rejected", "request": req.to_dict()})
