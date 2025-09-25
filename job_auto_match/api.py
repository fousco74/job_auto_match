import frappe
import requests
from contextlib import contextmanager

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
                subject_template = settings.candidate_rejected_after_test_subject or "Résultat de votre évaluation"
                subject = frappe.render_template(subject_template, ctx)
                template_html = settings.candidate_rejected_after_test_template
                if template_html:
                    message_html = frappe.render_template(template_html, ctx)
                else:
                    message_html = frappe.get_template("candidate_rejected.html").render(ctx)

                frappe.sendmail(recipients=[recipient], subject=subject, message=message_html)

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
