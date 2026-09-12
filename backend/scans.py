import os
import uuid

from flask import Blueprint, request, jsonify, current_app, send_from_directory
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from extensions import db
from models import Scan, User

scans_bp = Blueprint("scans", __name__, url_prefix="/api/scans")


def _allowed(filename, allowed_set):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed_set


@scans_bp.post("/upload")
@login_required
def upload_scan():
    # Only doctors can upload scans - patients view what their doctor uploads.
    if current_user.role != "doctor":
        return jsonify({"error": "Only doctors can upload scans"}), 403

    if "file" not in request.files:
        return jsonify({"error": "No file part named 'file'"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"error": "No file selected"}), 400

    if not _allowed(file.filename, current_app.config["ALLOWED_SCAN_EXTENSIONS"]):
        return jsonify({"error": "Unsupported file type"}), 400

    patient_id = request.form.get("patient_id", type=int)
    patient = User.query.get(patient_id) if patient_id else None
    if not patient or patient.role != "patient":
        return jsonify({"error": "Valid patient_id is required"}), 400

    # Doctor can only upload for their own assigned patients
    if patient.assigned_doctor_id != current_user.id:
        return jsonify({"error": "This patient is not assigned to you"}), 403

    safe_name = secure_filename(file.filename)
    unique_name = f"{uuid.uuid4().hex}_{safe_name}"
    dest_path = os.path.join(current_app.config["UPLOAD_FOLDER"], unique_name)
    file.save(dest_path)

    scan = Scan(
        patient_id=patient.id,
        doctor_id=current_user.id,
        filename=safe_name,
        stored_path=dest_path,
        body_part=request.form.get("body_part"),
        notes=request.form.get("notes"),
    )
    db.session.add(scan)
    db.session.commit()

    return jsonify({"message": "Scan uploaded", "scan": scan.to_dict()}), 201


@scans_bp.get("/history")
@login_required
def history():
    if current_user.role == "patient":
        scans = Scan.query.filter_by(patient_id=current_user.id).order_by(Scan.uploaded_at.desc()).all()
    else:
        scans = Scan.query.filter_by(doctor_id=current_user.id).order_by(Scan.uploaded_at.desc()).all()
    return jsonify({"scans": [s.to_dict() for s in scans]})


@scans_bp.get("/<int:scan_id>/file")
@login_required
def get_scan_file(scan_id):
    scan = Scan.query.get_or_404(scan_id)
    if current_user.id not in (scan.patient_id, scan.doctor_id):
        return jsonify({"error": "Not authorized to view this scan"}), 403
    directory, name = os.path.split(scan.stored_path)
    return send_from_directory(directory, name)
