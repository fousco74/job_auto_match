import frappe
from contextlib import contextmanager
from jinja2.exceptions import TemplateNotFound

from job_auto_match.job_auto_match.utils.matching import (
    send_candidate_not_matching_email,
    send_candidate_invite,
    _set_flag, _set_text, _set_statut,
    FLAG_MATCHING_IN_PROGRESS, FLAG_MATCHING_FAILED, FIELD_AI_LAST_ERROR,
)

# ── Constantes ───────────────────────────────────────────────────────────────
FLAG_REJECTED_AFTER_TEST_EMAIL_SENT = "custom_rejected_after_test_email_sent"
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
  <p>Nous vous remercions pour le temps consacré et conserverons votre profil pour des opportunités futures.</p>
  <p>Bien cordialement,<br>Équipe Recrutement</p>
</div>
""".strip()


# ── Helpers ──────────────────────────────────────────────────────────────────
def _to_float(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _is_test_ping(payload: dict) -> bool:
    return not payload.get("type") and not payload.get("event")


def _get_password_safely(doc, fieldname: str) -> str:
    """Récupère un password sans lever d'exception"""
    try:
        return (doc.get_password(fieldname, raise_exception=False) or "").strip()
    except Exception:
        return ""


@contextmanager
def _as_user(user: str):
    prev = frappe.session.user
    frappe.set_user(user)
    try:
        yield
    finally:
        frappe.set_user(prev)


# ── Webhook Testlify ─────────────────────────────────────────────────────────
@frappe.whitelist(allow_guest=True, methods=["POST"])
def completed():
    """Reçoit le webhook 'candidate completed' de Testlify."""
    try:
        payload = frappe.request.get_json(silent=True) or {}
        settings = frappe.get_cached_doc("Job Matching Integration Settings")

        frappe.logger().info(f"[TESTLIFY] Webhook appelé - Payload keys: {list(payload.keys())}")

        # 1) Ping de validation Testlify
        if _is_test_ping(payload):
            frappe.logger().info("[TESTLIFY] Ping de validation détecté")
            return {"status": 200, "reason": "webhook ok"}

        data = payload.get("data") or {}

        # 2) Authentification webhook
        expected = _get_password_safely(settings, "testlify_webhook_token")
        received = (frappe.get_request_header("X-Webhook-Token") or "").strip()

        frappe.logger().info(f"[TESTLIFY] Token reçu = '{received}' | Token attendu (début) = '{expected[:15]}...'")

        if expected and received != expected:
            frappe.logger().error("[TESTLIFY] Token invalide")
            frappe.local.response["http_status_code"] = 401
            return {"status": 401, "reason": "Token invalide."}

        # 3) Champs obligatoires
        assessment_id = data.get("assessmentId")
        candidate_data = data.get("candidate") or {}
        email = (candidate_data.get("email") or "").strip().lower()

        if not assessment_id:
            frappe.local.response["http_status_code"] = 400
            return {"status": 400, "reason": "`assessmentId` manquant."}

        if not email:
            frappe.local.response["http_status_code"] = 400
            return {"status": 400, "reason": "`data.candidate.email` manquant."}

        # 4) Recherche du candidat
        applicant_name = frappe.db.get_value(
            "Assessment Score", {"assessment_id": assessment_id}, "parent"
        )
        if not applicant_name:
            frappe.local.response["http_status_code"] = 404
            return {"status": 404, "reason": f"Aucun candidat pour assessment_id '{assessment_id}'."}

        # 5) Chargement du Job Applicant
        candidate = frappe.get_doc("Job Applicant", applicant_name)
        candidate.flags.ignore_permissions = True

        scores_data = data.get("scores") or {}
        incoming_score = _to_float(scores_data.get("avgScorePercentage", 0))

        # Mise à jour des assessments
        row_found = False
        for row in candidate.get("custom_assessments") or []:
            if getattr(row, "assessment_id", None) == assessment_id:
                row.completed = True
                row.assessment_score = incoming_score
                row_found = True
                break

        if not row_found:
            candidate.append("custom_assessments", {
                "assessment_id": assessment_id,
                "completed": True,
                "assessment_score": incoming_score,
            })

        # 6) Calcul score global
        all_rows = candidate.get("custom_assessments") or []
        item_count = len(all_rows)
        completed_count = sum(1 for r in all_rows if getattr(r, "completed", False))
        total_score = sum(_to_float(getattr(r, "assessment_score", 0)) for r in all_rows)

        frappe.logger().info(
            f"[TESTLIFY] {applicant_name} — {completed_count}/{item_count} évaluations complètes"
        )

        if item_count > 0 and completed_count == item_count:
            global_score = round(total_score / item_count, 2)
            rating = max(0.0, min(1.0, global_score / 100.0))

            candidate.applicant_rating = float(f"{rating:.2f}")
            candidate.custom_testlify_score = global_score

            # Mise à jour du statut
            threshold = getattr(settings, "score_test", 0) or 0
            new_status = getattr(settings, "status_after_test", None) if global_score >= threshold else getattr(settings, "status_rejected", None)
            _set_statut(candidate, new_status)

            # Envoi email de rejet
            if getattr(candidate, "custom_status", None) == getattr(settings, "status_rejected", None):
                recipient = (getattr(candidate, "email_id", "") or "").strip()
                if not recipient:
                    frappe.local.response["http_status_code"] = 404
                    return {"status": 404, "reason": "Email candidat introuvable."}

                ctx = {
                    "applicant_name": getattr(candidate, "applicant_name", ""),
                    "job_title": getattr(candidate, "custom_nom_de_loffre", "") or getattr(candidate, "job_title", ""),
                    "score": global_score,
                }

                subject_tpl = getattr(settings, "candidate_rejected_after_test_subject", "") or "Résultat de votre évaluation"

                try:
                    subject = frappe.render_template(subject_tpl, ctx)
                except Exception:
                    subject = subject_tpl

                html_src = (getattr(settings, "candidate_rejected_after_test_template", "") or "").strip()

                try:
                    if html_src:
                        message_html = frappe.render_template(html_src, ctx)
                    else:
                        try:
                            message_html = frappe.get_template(TEMPLATE_REJECTED).render(ctx)
                        except (TemplateNotFound, Exception):
                            message_html = frappe.render_template(DEFAULT_REJECTED_HTML, ctx)

                    frappe.sendmail(
                        recipients=[recipient],
                        subject=subject,
                        message=message_html,
                        delayed=False
                    )
                    _set_flag(candidate, FLAG_REJECTED_AFTER_TEST_EMAIL_SENT, 1)
                except Exception as e:
                    frappe.log_error(title="[TESTLIFY] Envoi email rejet échoué", message=frappe.get_traceback())
                    _set_text(candidate, FIELD_AI_LAST_ERROR, f"Email rejet: {str(e)}")
                    _set_flag(candidate, FLAG_REJECTED_AFTER_TEST_EMAIL_SENT, 0)

        # 7) Sauvegarde sous un utilisateur de service (sécurisé)
        # On utilise le champ webhook_service_user s'il existe, sinon on prend "Administrator" en dernier recours
        service_user = "Administrator"  # Valeur par défaut minimale

        if hasattr(settings, "webhook_service_user"):
            configured_user = (getattr(settings, "webhook_service_user", "") or "").strip()
            if configured_user and frappe.db.exists("User", configured_user):
                service_user = configured_user
            else:
                frappe.logger().warning(f"[TESTLIFY] Utilisateur configuré '{configured_user}' inexistant → fallback sur Administrator")
        else:
            frappe.logger().warning("[TESTLIFY] Champ 'webhook_service_user' absent du doctype → utilisation d'Administrator")

        frappe.logger().info(f"[TESTLIFY] Sauvegarde effectuée en tant que : {service_user}")

        with _as_user(service_user):
            candidate.save(ignore_permissions=True)

        frappe.db.commit()

        return {
            "status": 200,
            "data": {
                "applicant": candidate.name,
                "global_score": getattr(candidate, "custom_testlify_score", None),
                "updated": True
            }
        }

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "[TESTLIFY] Erreur générale webhook")
        frappe.local.response["http_status_code"] = 500
        return {"status": 500, "reason": str(e)}


# ── Actions manuelles ────────────────────────────────────────────────────────
@frappe.whitelist()
def retry_matching(applicant_name: str):
    from job_auto_match.job_auto_match.doctype.job_applicant.job_applicant import _enqueue_matching
    doc = frappe.get_doc("Job Applicant", applicant_name)
    _set_text(doc, FIELD_AI_LAST_ERROR, "")
    _set_flag(doc, FLAG_MATCHING_FAILED, 0)
    _set_flag(doc, FLAG_MATCHING_IN_PROGRESS, 1)
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    _enqueue_matching(doc.name)
    return {"ok": True, "message": f"Relance planifiée pour {doc.name}"}


@frappe.whitelist()
def resend_not_match_email(applicant_name: str):
    doc = frappe.get_doc("Job Applicant", applicant_name)
    send_candidate_not_matching_email(doc)
    return {"ok": True, "message": "E-mail 'non retenu' renvoyé."}


@frappe.whitelist()
def resend_invites(applicant_name: str):
    doc = frappe.get_doc("Job Applicant", applicant_name)
    job_title = (getattr(doc, "job_title", "") or "").strip()

    if not job_title:
        frappe.throw("Aucune offre d'emploi associée à ce candidat.", title="Offre manquante")

    try:
        fiche = frappe.get_doc("Job Opening", job_title)
    except frappe.DoesNotExistError:
        frappe.throw(f"L'offre d'emploi '{job_title}' est introuvable.", title="Offre introuvable")

    assessments = getattr(fiche, "custom_assessments", None) or []
    res = send_candidate_invite(doc, assessments)
    return {"ok": True, "result": res}