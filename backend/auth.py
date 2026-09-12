import re
from datetime import datetime

from flask import Blueprint, request, jsonify
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy.orm import aliased

from extensions import db
from models import User

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

    # Simple auto-assignment: a new patient gets assigned to the doctor
    # with the fewest current patients (replace with your own matching logic).
    #
    # NOTE: this is a self-referential query (User joined back to User via
    # assigned_patients), so it needs an explicit alias - joining a table to
    # itself without one is what was causing the 500 error.
    if role == "patient":
        PatientAlias = aliased(User)
        doctor = (
            db.session.query(User)
            .filter(User.role == "doctor")
            .outerjoin(PatientAlias, PatientAlias.assigned_doctor_id == User.id)
            .group_by(User.id)
            .order_by(db.func.count(PatientAlias.id).asc())
            .first()
        )
        if doctor:
            user.assigned_doctor_id = doctor.id

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
