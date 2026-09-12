Cell wise distribution:

Cell 1:
!nvidia-smi

Cell 2:
# Force-reinstall transformers to remove corrupted/mixed files
!pip uninstall -y transformers
!pip install -q --no-cache-dir transformers==4.49.0 accelerate bitsandbytes soundfile librosa gradio

Cell 3:
from huggingface_hub import login
login()

Cell 4:
!pip install -q faster-whisper gradio

Cell 5:
# 1. Remove the broken torchvision library that causes the crash
!pip uninstall -y torchvision

# 2. Install audio & LLM dependencies cleanly
!pip install -q transformers accelerate bitsandbytes soundfile librosa gradio

Cell 6:
# Install the exact matching torchvision build for Colab
!pip install -q torchvision

Cell 7:
from faster_whisper import WhisperModel
import torch

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
COMPUTE_TYPE = "float16" if torch.cuda.is_available() else "int8"
print(f"Loading Whisper on {DEVICE} ({COMPUTE_TYPE})...")

# Loads Whisper Base model on GPU instantly with zero torchvision dependency
whisper_model = WhisperModel("base", device=DEVICE, compute_type=COMPUTE_TYPE)

print("OpenAI Whisper loaded successfully!")

Cell 8:
import torch
from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig

# BioMistral: Open medical reasoning LLM (no gating, no token needed)
MODEL_ID = "BioMistral/BioMistral-7B"

bnb_config = BitsAndBytesConfig(
    load_in_4bit=True,
    bnb_4bit_quant_type="nf4",
    bnb_4bit_compute_dtype=torch.bfloat16,
    bnb_4bit_use_double_quant=True
)

print(f"Loading Medical LLM from {MODEL_ID} in 4-bit...")

medgemma_tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
medgemma_model = AutoModelForCausalLM.from_pretrained(
    MODEL_ID,
    quantization_config=bnb_config,
    device_map="auto"
)

print("Medical Reasoning LLM loaded successfully!")

Cell 9:
import numpy as np
import librosa
import soundfile as sf

def infer_study_protocol(transcript: str) -> str:
    """Automatically detects examination type from clinical dictation content."""
    text = transcript.lower()
    if any(k in text for k in ["chest", "cxr", "pa and lateral", "lungs", "pulmonary", "cardiomegaly", "infiltrate", "pleural", "rib"]):
        if "ct" in text:
            return "CT Chest (Thorax) with IV Contrast"
        return "Chest Radiograph (PA & Lateral)"
    elif any(k in text for k in ["abdomen", "pelvic", "pelvis", "liver", "spleen", "kidney", "appendix", "diverticul", "bowel"]):
        return "CT Abdomen & Pelvis with IV Contrast"
    elif any(k in text for k in ["brain", "head", "mri", "stroke", "infarct", "intracranial", "ventricle", "hemorrhage"]):
        return "MRI Brain without Contrast"
    elif any(k in text for k in ["spine", "lumbar", "cervical", "thoracic spine", "vertebra"]):
        return "MRI Spine (Sagittal & Axial)"
    return "Clinical Diagnostic Examination"

def transcribe_with_whisper(audio_path) -> str:
    """Transcribes audio using faster-whisper."""
    segments, info = whisper_model.transcribe(audio_path, beam_size=5)
    return " ".join([seg.text.strip() for seg in segments])

Cell 10:
import re
import json

SYSTEM_PROMPT = """You are a certified clinical AI radiologist.
Analyze the transcribed medical dictation and produce a structured, professional radiology report.
Automatically determine the appropriate study protocol, clinical indication, findings, and impression.
Strictly output your response as valid JSON with the following structure:
{
  "examination": "<Detected examination protocol>",
  "indication": "<Clinical indication or presenting symptoms>",
  "technique": "<Standard imaging technique or protocol>",
  "comparison": "<Prior comparisons or 'None available'>",
  "findings": ["<Detailed observation 1>", "<Detailed observation 2>"],
  "impression": ["<Prioritized diagnostic conclusion 1>", "<Prioritized diagnostic conclusion 2>"]
}"""

def generate_medical_report(raw_transcript: str) -> dict:
    """Generates structured radiology report from raw transcript using BioMistral."""
    detected_protocol = infer_study_protocol(raw_transcript)
    
    # Prompt formatted for Mistral / BioMistral instruction format [INST] ... [/INST]
    prompt_text = f"""<s>[INST] {SYSTEM_PROMPT}

DETECTED STUDY TYPE: {detected_protocol}
RAW DICTATION TRANSCRIPT: {raw_transcript}

Generate the structured JSON report: [/INST]"""

    inputs = medgemma_tokenizer(prompt_text, return_tensors="pt").to(medgemma_model.device)

    with torch.no_grad():
        output_ids = medgemma_model.generate(
            **inputs, 
            max_new_tokens=600, 
            temperature=0.2, 
            do_sample=False
        )

    # Decode newly generated tokens
    response_ids = output_ids[0][inputs["input_ids"].shape[-1]:]
    response_content = medgemma_tokenizer.decode(response_ids, skip_special_tokens=True)
    
    # Extract JSON object from model generation
    json_match = re.search(r"\{.*\}", response_content, re.DOTALL)
    if json_match:
        try:
            parsed = json.loads(json_match.group(0))
            if "examination" not in parsed:
                parsed["examination"] = detected_protocol
            return parsed
        except Exception:
            pass
            
    return {
        "examination": detected_protocol,
        "indication": "Clinical evaluation requested",
        "technique": "Standard clinical projection",
        "comparison": "None available",
        "findings": [s.strip() for s in raw_transcript.split(". ") if s.strip()],
        "impression": ["Clinical evaluation recommended based on findings."]
    }

Cell 11:
sample_dictation = (
    "Frontal and lateral chest radiographs demonstrate persistent focal airspace consolidation in the right middle lobe with air bronchograms, "
    "highly suspicious for acute bronchopneumonia. Mild cardiomegaly without overt pulmonary edema. "
    "Costophrenic angles are sharp. No visible pneumothorax or pleural effusion. "
    "Impression: Right middle lobe acute pneumonia. Mild cardiomegaly."
)

print("--- INPUT CLINICAL DICTATION ---")
print(sample_dictation)

print("\n--- GENERATED STRUCTURED REPORT (BioMistral) ---")
report = generate_medical_report(sample_dictation)
print(json.dumps(report, indent=2))


Cell 12:
import gradio as gr

def full_pipeline(audio_path):
    if audio_path is None:
        return "Please record or upload clinical audio.", ""
    
    # Step 1: Transcribe via Whisper
    transcript = transcribe_with_whisper(audio_path)
    if not transcript:
        return "[No speech detected]", "No report generated."
    
    # Step 2: Generate structured report via BioMistral
    report = generate_medical_report(transcript)
    
    findings = report.get("findings", [])
    impression = report.get("impression", [])
    
    findings_md = "\n".join([f"- {f}" for f in findings]) if isinstance(findings, list) else str(findings)
    impression_md = "\n".join([f"{i+1}. {imp}" for i, imp in enumerate(impression)]) if isinstance(impression, list) else str(impression)
    
    formatted_report = f"""# 📋 RADIOLOGY REPORT
**Examination:** {report.get('examination', 'Clinical Examination')}
**Indication:** {report.get('indication', 'Clinical correlation')}
**Technique:** {report.get('technique', 'Standard protocol')}
**Comparison:** {report.get('comparison', 'None available')}

---

### FINDINGS
{findings_md}

---

### IMPRESSION
{impression_md}

---
*Generated by OpenAI Whisper + BioMistral (Medical AI)*
"""
    return transcript, formatted_report

with gr.Blocks(title="Whisper + BioMistral Medical Report System") as demo:
    gr.Markdown("# 🎙️ Clinical Speech-to-Report Platform")
    gr.Markdown("Speak clinical observations via microphone or upload an audio file. The system transcribes with **OpenAI Whisper**, automatically detects the study protocol, and generates a structured medical report with **BioMistral**.")
    
    with gr.Row():
        with gr.Column():
            audio_in = gr.Audio(sources=["microphone", "upload"], type="filepath", label="Doctor Dictation")
            submit_btn = gr.Button("Generate Medical Report", variant="primary")
            
        with gr.Column():
            transcript_out = gr.Textbox(label="Whisper Transcript", lines=4)
            report_out = gr.Markdown(label="Structured Medical Report")
            
    submit_btn.click(
        fn=full_pipeline,
        inputs=[audio_in],
        outputs=[transcript_out, report_out]
    )

demo.launch(share=True)


