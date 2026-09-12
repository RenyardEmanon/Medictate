import os

from flask import Blueprint, request, jsonify, current_app, send_from_directory
from flask_login import login_required, current_user
from flask_mail import Message

from extensions import db, mail
from models import Scan, Report, User
from stt import TranscriptionError
from report_utils import run_transcription_pipeline, build_docx

reports_bp = Blueprint("reports", __name__, url_prefix="/api/reports")


@reports_bp.post("/record")
@login_required
def record_standalone():
    """Doctor dictates a report for a patient directly - no scan required."""
    if current_user.role != "doctor":
        return jsonify({"error": "Only doctors can dictate reports"}), 403

    patient_id = request.form.get("patient_id", type=int)
    patient = User.query.get(patient_id) if patient_id else None
    if not patient or patient.role != "patient":
        return jsonify({"error": "Valid patient_id is required"}), 400
    if patient.assigned_doctor_id != current_user.id:
        return jsonify({"error": "This patient is not assigned to you"}), 403

    if "audio" not in request.files:
        return jsonify({"error": "No audio file part named 'audio'"}), 400

    try:
        final_text = run_transcription_pipeline(request.files["audio"])
    except (ValueError, TranscriptionError) as e:
        message = e.message if isinstance(e, TranscriptionError) else str(e)
        status = e.status_code if isinstance(e, TranscriptionError) else 400
        return jsonify({"error": message}), status
    except Exception as e:
        current_app.logger.exception("Unexpected error during transcription pipeline")
        return jsonify({"error": f"Unexpected server error: {e}"}), 500

    try:
        report = Report(patient_id=patient.id, author_id=current_user.id, transcript_text=final_text)
        db.session.add(report)
        db.session.flush()
        report.docx_path = build_docx(report)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("Unexpected error while saving report / building docx")
        return jsonify({"error": f"Unexpected server error while saving report: {e}"}), 500

    return jsonify({"message": "Transcribed", "report": report.to_dict()})


@reports_bp.get("/my")
@login_required
def my_reports():
    if current_user.role == "patient":
        reports = Report.query.filter_by(patient_id=current_user.id).order_by(Report.created_at.desc()).all()
    else:
        reports = Report.query.filter_by(author_id=current_user.id).order_by(Report.created_at.desc()).all()
    return jsonify({"reports": [r.to_dict() for r in reports]})


@reports_bp.put("/<int:report_id>/correct")
@login_required
def correct(report_id):
    report = Report.query.get_or_404(report_id)
    if current_user.id != report.author_id:
        return jsonify({"error": "Only the authoring doctor can edit this report"}), 403

    data = request.get_json(force=True) or {}
    corrected_text = data.get("transcript_text")
    if corrected_text is None:
        return jsonify({"error": "transcript_text is required"}), 400

    try:
        report.transcript_text = corrected_text
        report.docx_path = build_docx(report)
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("Unexpected error while updating report")
        return jsonify({"error": f"Unexpected server error: {e}"}), 500

    return jsonify({"message": "Report updated", "report": report.to_dict()})


@reports_bp.get("/<int:report_id>/download")
@login_required
def download_own(report_id):
    report = Report.query.get_or_404(report_id)
    if current_user.id not in (report.author_id, report.patient_id):
        return jsonify({"error": "Not authorized"}), 403
    if not report.docx_path:
        return jsonify({"error": "Report has no generated document yet"}), 400
    directory, name = os.path.split(report.docx_path)
    return send_from_directory(directory, name, as_attachment=True, download_name="radiology_report.docx")


@reports_bp.post("/<int:report_id>/send-to-patient")
@login_required
def send_to_patient(report_id):
    report = Report.query.get_or_404(report_id)
    if current_user.id != report.author_id:
        return jsonify({"error": "Only the authoring doctor can send this report"}), 403
    if not report.docx_path:
        return jsonify({"error": "Report has no generated document yet"}), 400

    api_key = report.generate_api_key()
    report.sent_to_patient = True
    db.session.commit()

    download_link = f"{current_app.config['PUBLIC_BASE_URL']}/api/reports/public-download/{report.id}?key={api_key}"

    patient = report.patient
    try:
        msg = Message(
            subject="Your Radiology Report is Ready",
            recipients=[patient.email],
            body=(
                f"Hello {patient.name},\n\n"
                f"Your radiology report from Dr. {report.author.name} is ready.\n"
                f"You can securely download it here:\n{download_link}\n\n"
                "This link is unique to you - please don't share it.\n\n"
                "Regards,\nRadiology Team"
            ),
        )
        mail.send(msg)
    except Exception as exc:
        current_app.logger.warning("Email send failed: %s", exc)
        return jsonify({
            "message": "API key generated, but email failed to send (check MAIL_* config).",
            "download_link": download_link,
        }), 202

    return jsonify({"message": f"Report emailed to {patient.email}", "download_link": download_link})


@reports_bp.get("/public-download/<int:report_id>")
def public_download(report_id):
    report = Report.query.get_or_404(report_id)
    supplied_key = request.args.get("key")
    if not supplied_key or supplied_key != report.api_key:
        return jsonify({"error": "Invalid or missing API key"}), 401
    if not report.docx_path:
        return jsonify({"error": "Report has no generated document yet"}), 400
    directory, name = os.path.split(report.docx_path)
    return send_from_directory(directory, name, as_attachment=True, download_name="radiology_report.docx")
