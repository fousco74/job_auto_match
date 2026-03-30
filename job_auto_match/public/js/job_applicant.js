frappe.ui.form.on('Job Applicant', {
	refresh(frm) {
		hide_specific_action_button(frm);
		update_custom_job_title(frm);

		// Cacher le champ status standard, custom_status est le champ principal
		frm.set_df_property('status', 'hidden', 1);

		// Synchroniser custom_status avec workflow_state (après action workflow)
		if (frm.doc.workflow_state && frm.doc.custom_status !== frm.doc.workflow_state) {
			frm.doc.custom_status = frm.doc.workflow_state;
			frm.refresh_field('custom_status');
		}

		if (frm.is_new()) return;

		// Récupère l'état du matching sur l'offre, puis construit l'UI
		if (frm.doc.job_title) {
			frappe.db.get_value('Job Opening', frm.doc.job_title, 'custom_active_cv_auto_matching')
				.then(r => {
					const enabled = !!(r?.message?.custom_active_cv_auto_matching);
					render_matching_ui(frm, enabled);
				})
				.catch(() => render_matching_ui(frm, true));
		} else {
			render_matching_ui(frm, false);
		}
	},

	job_title(frm) {
		update_custom_job_title(frm);
	}
});


function render_matching_ui(frm, matching_enabled) {
	const in_prog   = !!frm.doc.custom_is_matching_in_progress;
	const failed    = !!frm.doc.custom_is_matching_failed;
	const emailSent = !!frm.doc.custom_not_match_email_sent;
	const invites   = !!frm.doc.custom_invites_sent;

	// --- Actions IA ---
	if (matching_enabled && !in_prog) {
		frm.add_custom_button('Relancer matching', () => {
			frappe.call({
				method: 'job_auto_match.api.retry_matching',
				args: { applicant_name: frm.doc.name },
				freeze: true,
				freeze_message: 'Relance en cours…',
				callback: () => frm.reload_doc()
			});
		}, 'Actions IA');
	}

	if (emailSent) {
		frm.add_custom_button('Renvoyer email "Non retenu"', () => {
			frappe.call({
				method: 'job_auto_match.api.resend_not_match_email',
				args: { applicant_name: frm.doc.name },
				freeze: true,
				freeze_message: 'Envoi e-mail…',
				callback: () => frm.reload_doc()
			});
		}, 'Actions IA');
	}

	if (!invites) {
		frm.add_custom_button('Renvoyer invitations', () => {
			frappe.call({
				method: 'job_auto_match.api.resend_invites',
				args: { applicant_name: frm.doc.name },
				freeze: true,
				freeze_message: 'Envoi invitations…',
				callback: () => frm.reload_doc()
			});
		}, 'Actions IA');
	}

	// --- Bannière d'état ---
	frm.dashboard.clear_headline();

	if (!matching_enabled) {
		const offer_link = frm.doc.job_title
			? ` — <a href="/app/job-opening/${encodeURIComponent(frm.doc.job_title)}" target="_blank">Ouvrir l'offre pour l'activer</a>`
			: '';
		frm.dashboard.set_headline_alert(
			`Matching IA désactivé pour cette offre${offer_link}`,
			'orange'
		);
		stop_matching_poll(frm);
	} else if (in_prog) {
		frm.dashboard.set_headline_alert('Matching en cours…', 'blue');
		start_matching_poll(frm);
	} else {
		stop_matching_poll(frm);
		if (failed) {
			frm.dashboard.set_headline_alert(
				`Dernière erreur IA : ${frappe.utils.escape_html(frm.doc.custom_ai_last_error || '')}`,
				'red'
			);
		}
	}
}


function start_matching_poll(frm) {
	if (frm._matching_poll) return;
	frm._matching_poll = setInterval(() => {
		frappe.db.get_value('Job Applicant', frm.doc.name, 'custom_is_matching_in_progress')
			.then(r => {
				if (!r?.message?.custom_is_matching_in_progress) {
					frm.reload_doc();
				}
			});
	}, 3000);
}

function stop_matching_poll(frm) {
	if (frm._matching_poll) {
		clearInterval(frm._matching_poll);
		frm._matching_poll = null;
	}
}

function update_custom_job_title(frm) {
	if (frm.doc.job_title && !frm.doc.custom_nom_de_loffre) {
		frappe.db.get_value('Job Opening', frm.doc.job_title, 'job_title')
			.then(r => {
				if (r?.message?.job_title) {
					frm.set_value('custom_nom_de_loffre', r.message.job_title);
				}
			});
	}
}

function hide_specific_action_button() {
	setTimeout(() => {
		$('div.actions-btn-group').hide();
	}, 300);
}
