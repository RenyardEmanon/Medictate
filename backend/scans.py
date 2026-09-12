import os
import uuid

from flask import Blueprint, request, jsonify, current_app, send_from_directory
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from extensions import db
from models import Scan, Report, User
from stt import TranscriptionError
from report_utils import run_transcription_pipeline, build_docx

scans_bp = Blueprint("scans", __name__, url_prefix="/api/scans")


def _allowed(filename, allowed_set):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed_set


@scans_bp.post("/upload")
@login_required
def upload_scan():
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
    db.session.flush()  # get scan.id before we might attach a report to it

    response_payload = {"message": "Scan uploaded", "scan": scan.to_dict()}

    # Optional: a voice recording was bundled in with the scan upload.
    # Transcribe it and attach it as this scan's report. If transcription
    # fails, the scan upload itself still succeeds - we surface a warning
    # instead of losing the uploaded scan.
    audio_file = request.files.get("audio")
    if audio_file and audio_file.filename:
        try:
            final_text = run_transcription_pipeline(audio_file)
            report = Report(scan_id=scan.id, patient_id=patient.id, author_id=current_user.id, transcript_text=final_text)
            db.session.add(report)
            db.session.flush()
            report.docx_path = build_docx(report)
            scan.status = "reported"
            response_payload["report"] = report.to_dict()
        except (ValueError, TranscriptionError) as e:
            message = e.message if isinstance(e, TranscriptionError) else str(e)
            response_payload["transcription_warning"] = message
        except Exception as e:
            current_app.logger.exception("Unexpected error transcribing bundled audio")
            response_payload["transcription_warning"] = f"Unexpected error while transcribing audio: {e}"

    db.session.commit()
    return jsonify(response_payload), 201


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
