import frappe
import requests

def to_float(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default

def is_testlify_webhook(payload: dict) -> bool:
    # Payload de TEST (quand tu enregistres l’URL) => pas de event/type
    return True if not payload.get("type") and not payload.get("event") else False


@frappe.whitelist(allow_guest=True, methods=["POST"])
def completed():
    try:
        payload = frappe.request.get_json() or {}
        settings = frappe.get_single("Job Matching Integration Settings")

        # 1) Acquittement du payload de test (ngrok)
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

        # 3) Clés attendues
        assessment_id = data.get("assessmentId")
        email = (data.get("email") or "").strip().lower()
        if not assessment_id:
            frappe.local.response["http_status_code"] = 400
            return {"status": 400, "reason": "`assessmentId` manquant dans la charge utile."}

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

        # 5) Récupération du candidat
        assessment_desc = (assessment_json.get("assessmentDescription") or "").strip()
        candidates = frappe.get_list(
            "Job Applicant",
            filters={"email_id": email, "job_title": assessment_desc} if assessment_desc else {"email_id": email},
            fields=["name"],
            ignore_permissions=True,
        )
        if not candidates:
            frappe.local.response["http_status_code"] = 404
            return {"status": 404, "reason": email}

        candidate = frappe.get_doc("Job Applicant", candidates[0]["name"])
        candidate.flags.ignore_permissions = True

        # 6) Mise à jour du tableau des évaluations
        updated_row = False
        total_score = 0.0
        completed_count = 0

        incoming_score = to_float(data.get("avgScorePercentage", 0), 0.0)

        rows = candidate.assessments or []
        for i, row in enumerate(rows):
            if row.assessment_id == assessment_id:
                candidate.assessments[i].completed = True
                candidate.assessments[i].assessment_score = incoming_score  # stocker en float
                updated_row = True
            if row.completed:
                completed_count += 1
            # addition ALWAYS in float
            total_score += to_float(row.assessment_score, 0.0)

        # Si l'évaluation n'existe pas encore, on l'ajoute
        if not updated_row:
            candidate.append("assessments", {
                "assessment_id": assessment_id,
                "completed": True,
                "assessment_score": incoming_score,
            })
            completed_count += 1
            total_score += incoming_score

        item_count = len(candidate.assessments or [])
        print(f"completed_acount : {completed_count} ,  item_count : {item_count}")


        # 7) Si toutes complétées -> score global + statut
        if item_count > 0 and completed_count == item_count:
            global_score = round(total_score / float(item_count), 2)
              # Normalisation du score (0-100) vers (0.0-1.0)
            rating = global_score / 100

            # Forcer la plage 0.0 - 1.0
            rating = max(0.0, min(1.0, rating))

            # Formatage en DECIMAL(3,2) pour MariaDB
            candidate.applicant_rating = float(f"{rating:.2f}")
            candidate.testlify_score = global_score
            candidate.status = "Accepted" if global_score >= 40 else "Rejected"

            if candidate.status == "Rejected":
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

        candidate.save()
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
