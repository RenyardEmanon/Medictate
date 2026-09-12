import secrets
from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

from extensions import db


class User(db.Model, UserMixin):
    """A doctor or a patient."""
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(160), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="patient")
    specialty = db.Column(db.String(120))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    dob = db.Column(db.Date, nullable=True)
    phone = db.Column(db.String(15), nullable=True)

    assigned_doctor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    assigned_doctor = db.relationship(
        "User", remote_side=[id], backref="assigned_patients"
    )

    def set_password(self, raw_password):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        return check_password_hash(self.password_hash, raw_password)

    @property
    def age(self):
        if not self.dob:
            return None
        from datetime import date
        today = date.today()
        years = today.year - self.dob.year
        had_birthday = (today.month, today.day) >= (self.dob.month, self.dob.day)
        return years if had_birthday else years - 1

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "email": self.email,
            "role": self.role,
            "specialty": self.specialty,
            "dob": self.dob.isoformat() if self.dob else None,
            "age": self.age,
            "phone": self.phone,
            "assigned_doctor": (
                {"id": self.assigned_doctor.id, "name": self.assigned_doctor.name,
                 "specialty": self.assigned_doctor.specialty}
                if self.role == "patient" and self.assigned_doctor else None
            ),
        }


class DoctorRequest(db.Model):
    """A patient's request to be assigned to a specific doctor - stays
    pending until the doctor accepts (or rejects) it."""
    __tablename__ = "doctor_requests"

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    status = db.Column(db.String(20), default="pending")  # pending | accepted | rejected
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    responded_at = db.Column(db.DateTime, nullable=True)

    patient = db.relationship("User", foreign_keys=[patient_id])
    doctor = db.relationship("User", foreign_keys=[doctor_id])

    def to_dict(self):
        return {
            "id": self.id,
            "patient_id": self.patient_id,
            "patient_name": self.patient.name if self.patient else None,
            "patient_email": self.patient.email if self.patient else None,
            "doctor_id": self.doctor_id,
            "doctor_name": self.doctor.name if self.doctor else None,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
        }


class Scan(db.Model):
    """An uploaded radiology scan (X-ray / CT / MRI image or DICOM/PDF)."""
    __tablename__ = "scans"

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    doctor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    filename = db.Column(db.String(255), nullable=False)
    stored_path = db.Column(db.String(400), nullable=False)
    body_part = db.Column(db.String(120))
    notes = db.Column(db.Text)
    status = db.Column(db.String(30), default="uploaded")
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)

    patient = db.relationship("User", foreign_keys=[patient_id])
    doctor = db.relationship("User", foreign_keys=[doctor_id])

    def to_dict(self):
        return {
            "id": self.id,
            "patient_id": self.patient_id,
            "doctor_id": self.doctor_id,
            "filename": self.filename,
            "body_part": self.body_part,
            "notes": self.notes,
            "status": self.status,
            "uploaded_at": self.uploaded_at.isoformat(),
        }


class Report(db.Model):
    """A voice-dictated radiology report.

    scan_id is now OPTIONAL - a doctor can dictate a report for a patient
    directly, without it being tied to any specific uploaded scan.
    patient_id/doctor_id are stored directly on the report so it always
    knows who it's for/from, whether or not a scan exists.
    """
    __tablename__ = "reports"

    id = db.Column(db.Integer, primary_key=True)
    scan_id = db.Column(db.Integer, db.ForeignKey("scans.id"), nullable=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)  # doctor
    transcript_text = db.Column(db.Text, default="")
    docx_path = db.Column(db.String(400))
    api_key = db.Column(db.String(64), unique=True, index=True)
    sent_to_patient = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    scan = db.relationship("Scan")
    patient = db.relationship("User", foreign_keys=[patient_id])
    author = db.relationship("User", foreign_keys=[author_id])

    def generate_api_key(self):
        self.api_key = secrets.token_urlsafe(32)
        return self.api_key

    def to_dict(self):
        return {
            "id": self.id,
            "scan_id": self.scan_id,
            "patient_id": self.patient_id,
            "patient_name": self.patient.name if self.patient else None,
            "author_id": self.author_id,
            "transcript_text": self.transcript_text,
            "sent_to_patient": self.sent_to_patient,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }
