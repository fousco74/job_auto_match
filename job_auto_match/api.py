import frappe
import requests
from frappe import enqueue
from contextlib import contextmanager
from jinja2 import TemplateNotFound


# Flag dédié (ajoute un Check field dans Job Applicant)
FLAG_REJECTED_AFTER_TEST_EMAIL_SENT = "custom_rejected_after_test_email_sent"

# Chemin Jinja complet + fallback HTML
TEMPLATE_REJECTED = "job_auto_match/templates/emails/candidate_rejected.html"
DEFAULT_REJECTED_HTML = """
<div style="font-family: Inter, Arial, sans-serif; line-height:1.5; color:#111">
  <h2 style="margin:0 0 8px">Résultat de votre évaluation</h2>
  <p>Bonjour {{ applicant_name or "Candidat" }},</p>
  <p>Suite à votre évaluation pour le poste <strong>{{ job_title or "—" }}</strong>,
     nous ne pouvons malheureusement pas donner suite favorablement à votre candidature.</p>
  {% if score is not none %}
    <p><strong>Score global :</strong> {{ score }} %</p>
  {% endif %}
  <p>Nous vous remercions pour le temps consacré et conserverons votre profil pour des opportunités plus adaptées.</p>
  <p>Bien cordialement,<br>Équipe Recrutement</p>
</div>
""".strip()



# ——— Imports depuis matching.py ———
from job_auto_match.job_auto_match.utils.matching import (
    send_candidate_not_matching_email,
    send_candidate_invite,
    _set_flag, _set_text,
    FIELD_AI_LAST_ERROR
)

# Flags & helpers (si tu les as définis dans matching.py, on les importe; sinon fallback local)
try:
    from job_auto_match.job_auto_match.utils.matching import (
        _set_flag, _set_text,
        FLAG_MATCHING_IN_PROGRESS, FLAG_MATCHING_FAILED,
        FIELD_AI_LAST_ERROR
    )
except Exception:
    # Fallback: versions locales minimales
    def _set_flag(doc, fieldname: str, value: int):
        if hasattr(doc, fieldname):
            setattr(doc, fieldname, 1 if value else 0)

    def _set_text(doc, fieldname: str, value: str, max_len=1000):
        if hasattr(doc, fieldname):
            setattr(doc, fieldname, (value or "")[:max_len])

    FLAG_MATCHING_IN_PROGRESS = "custom_is_matching_in_progress"
    FLAG_MATCHING_FAILED      = "custom_is_matching_failed"
    FIELD_AI_LAST_ERROR       = "custom_ai_last_error"



def to_float(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default

def is_testlify_webhook(payload: dict) -> bool:
    # Payload de TEST (quand tu enregistres l’URL) => pas de event/type
    return True if not payload.get("type") and not payload.get("event") else False

@contextmanager
def as_user(user: str):
    prev = frappe.session.user
    frappe.set_user(user)
    try:
        yield
    finally:
        frappe.set_user(prev)

@frappe.whitelist(allow_guest=True, methods=["POST"])
def completed():
    try:
        payload = frappe.request.get_json() or {}
        settings = frappe.get_single("Job Matching Integration Settings")

        # 1) Acquittement du payload de test
        if is_testlify_webhook(payload):
            frappe.local.response["http_status_code"] = 200
            return {"status": 200, "reason": "Testlify webhook ok (testdata)"}

        data = payload.get("data") or {}

        # 2) Vérif token
        expected_token = (getattr(settings, "testlify_webhook_token", None) or "").strip()
        received_token = (frappe.get_request_header("X-Webhook-Token") or "").strip()
        if expected_token and received_token != expected_token:
            frappe.local.response["http_status_code"] = 401
            return {"status": 401, "reason": "Token de webhook invalide."}

        # 3) Champs attendus
        assessment_id = data.get("assessmentId")
        email = (data.get("email") or "").strip().lower()
        if not assessment_id:
            frappe.local.response["http_status_code"] = 400
            return {"status": 400, "reason": "`assessmentId` manquant dans la charge utile."}
        if not email:
            frappe.local.response["http_status_code"] = 400
            return {"status": 400, "reason": "`email` manquant dans la charge utile."}

        # 4) Appel API Testlify
        base = (settings.testlify_base_url or "").rstrip("/")
        url = f"{base}/assessment/{assessment_id}"
        headers = {
            "Authorization": f"Bearer {settings.testlify_token}",
            "Content-Type": "application/json",
        }
        r = requests.get(url, headers=headers, timeout=30)
        r.raise_for_status()
        assessment_json = r.json() or {}

        # 5) Récupération du candidat (bypass perms pour lookup)
        assessment_desc = (assessment_json.get("assessmentDescription") or "").strip()
        filters = {"email_id": email}
        if assessment_desc:
            filters["job_title"] = assessment_desc

        candidates = frappe.db.get_all(
            "Job Applicant",
            filters=filters,
            fields=["name"],
        )
        if not candidates:
            frappe.local.response["http_status_code"] = 404
            return {"status": 404, "reason": f"Candidat introuvable pour email '{email}'."}

        candidate = frappe.get_doc("Job Applicant", candidates[0]["name"])
        candidate.flags.ignore_permissions = True  # utile mais pas suffisant pour le workflow

        # 6) Mise à jour des évaluations
        incoming_score = to_float(data.get("avgScorePercentage", 0), 0.0)
        updated_row = False

        rows = candidate.custom_assessments or []
        for i, row in enumerate(rows):
            if row.assessment_id == assessment_id:
                rows[i].completed = True
                rows[i].assessment_score = incoming_score
                updated_row = True

        if not updated_row:
            candidate.append("custom_assessments", {
                "assessment_id": assessment_id,
                "completed": True,
                "assessment_score": incoming_score,
            })

        # Recalcule après modifications
        item_count = len(candidate.custom_assessments or [])
        completed_count = sum(1 for r in candidate.custom_assessments if getattr(r, "completed", False))
        total_score = sum(to_float(getattr(r, "assessment_score", 0.0), 0.0) for r in candidate.custom_assessments)

        print(f"completed_count: {completed_count} , item_count: {item_count}")

        # 7) Si toutes complétées -> score global + statut
        if item_count > 0 and completed_count == item_count:
            global_score = round(total_score / float(item_count), 2)
            rating = max(0.0, min(1.0, global_score / 100.0))  # clamp 0..1

            candidate.applicant_rating = float(f"{rating:.2f}")  # DECIMAL(3,2)
            candidate.custom_testlify_score = global_score
            candidate.custom_status_x = "Accepted" if global_score >= 40 else "Rejected"

            if candidate.custom_status_x == "Rejected":
                recipient = (getattr(candidate, "email_id", "") or "").strip()
                if not recipient:
                    frappe.local.response["http_status_code"] = 404
                    return {"status": 404, "reason": "Email du candidat introuvable."}

                ctx = {
                    "applicant_name": getattr(candidate, "applicant_name", ""),
                    "job_title": getattr(candidate, "job_title", "") or assessment_desc,
                    "score": global_score,
                }

                subject_tpl = (settings.candidate_rejected_after_test_subject
                            or "Résultat de votre évaluation")
                try:
                    subject = frappe.render_template(subject_tpl, ctx)
                except Exception:
                    subject = subject_tpl  # si pas de variable, garder brut

                html_src = (settings.candidate_rejected_after_test_template or "").strip()
                try:
                    if html_src:
                        message_html = frappe.render_template(html_src, ctx)
                    else:
                        try:
                            message_html = frappe.get_template(TEMPLATE_REJECTED).render(ctx)
                        except TemplateNotFound:
                            message_html = frappe.render_template(DEFAULT_REJECTED_HTML, ctx)

                    frappe.sendmail(recipients=[recipient], subject=subject, message=message_html)
                    _set_flag(candidate, FLAG_REJECTED_AFTER_TEST_EMAIL_SENT, 1)

                except Exception as e:
                    # log propre et flags
                    try:
                        safe_title = "[TESTLIFY] Envoi email rejet échoué"[:140]
                        frappe.log_error(message=f"{frappe.get_traceback()}\n{repr(e)}", title=safe_title)
                    except Exception:
                        pass
                    _set_text(candidate, FIELD_AI_LAST_ERROR, f"Email rejet après test: {e}")
                    _set_flag(candidate, FLAG_REJECTED_AFTER_TEST_EMAIL_SENT, 0)


        # 8) Sauvegarde sous utilisateur de service pour éviter PermissionError (workflow)
        service_user = (getattr(settings, "webhook_service_user", None) or "Administrator").strip()
        with as_user(service_user):
            candidate.save(ignore_permissions=True)

        frappe.db.commit()

        return {
            "status": 200,
            "data": {
                "applicant": candidate.name,
                "assessment_id": assessment_id,
                "assessment_description": assessment_desc,
                "updated": True
            },
        }

    except requests.HTTPError as e:
        code = getattr(e.response, "status_code", 502) or 502
        frappe.local.response["http_status_code"] = code
        return {"status": code, "reason": f"Erreur Testlify API: {getattr(e.response, 'text', '')}"}

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Erreur dans le webhook Testlify")
        frappe.local.response["http_status_code"] = 500
        return {"status": 500, "reason": str(e)}





@frappe.whitelist()
def retry_matching(applicant_name: str):
    doc = frappe.get_doc("Job Applicant", applicant_name)
    _set_text(doc, FIELD_AI_LAST_ERROR, "")
    _set_flag(doc, FLAG_MATCHING_FAILED, 0)
    _set_flag(doc, FLAG_MATCHING_IN_PROGRESS, 1)
    doc.save(ignore_permissions=True)
    frappe.db.commit()

    enqueue(
        "job_auto_match.job_auto_match.utils.matching.process_job_applicant_matching",
        applicant_name=doc.name,
        queue="long",
        timeout=300,
        now=False
    )
    return {"ok": True, "message": f"Relance matching planifiée pour {doc.name}"}

@frappe.whitelist()
def resend_not_match_email(applicant_name: str):
    doc = frappe.get_doc("Job Applicant", applicant_name)
    send_candidate_not_matching_email(doc)
    return {"ok": True, "message": "E-mail 'non retenu' renvoyé."}

@frappe.whitelist()
def resend_invites(applicant_name: str):
    doc = frappe.get_doc("Job Applicant", applicant_name)
    # Utilise la fiche liée au titre du job
    fiche = frappe.get_doc("Job Opening", doc.job_title or "")
    res = send_candidate_invite(doc, fiche.custom_assessments)
    return {"ok": True, "result": res}

