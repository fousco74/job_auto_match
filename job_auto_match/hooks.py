app_name = "job_auto_match"
app_title = "job_auto_match"
app_publisher = "KONE Fousseni"
app_description = "automatiser le processus de recrutement"
app_email = "fkone@amoaman.com"
app_license = "mit"

# Apps
# ------------------

# required_apps = []

# Each item in the list will be shown as an app in the apps page
# add_to_apps_screen = [
# 	{
# 		"name": "job_auto_match",""
# 		"logo": "/assets/job_auto_match/logo.png",
# 		"title": "job_auto_match",
# 		"route": "/job_auto_match",
# 		"has_permission": "job_auto_match.api.permission.has_app_permission"
# 	}
# ]

# Includes in <head>
# ------------------

# include js, css files in header of desk.html
# app_include_css = "/assets/job_auto_match/css/job_auto_match.css"
# app_include_js = "/assets/job_auto_match/js/job_auto_match.js"

# include js, css files in header of web template
# web_include_css = "/assets/job_auto_match/css/job_auto_match.css"
# web_include_js = "/assets/job_auto_match/js/job_auto_match.js"

# include custom scss in every website theme (without file extension ".scss")
# website_theme_scss = "job_auto_match/public/scss/website"

# include js, css files in header of web form
# webform_include_js = {"doctype": "public/js/doctype.js"}
# webform_include_css = {"doctype": "public/css/doctype.css"}

# include js in page
# page_js = {"page" : "public/js/file.js"}

# include js in doctype views
doctype_js = {"Job Applicant" : "public/js/job_applicant/job_applicant.js"}
# doctype_list_js = {"doctype" : "public/js/doctype_list.js"}
# doctype_tree_js = {"doctype" : "public/js/doctype_tree.js"}
# doctype_calendar_js = {"doctype" : "public/js/doctype_calendar.js"}

# Svg Icons
# ------------------
# include app icons in desk
# app_include_icons = "job_auto_match/public/icons.svg"

# Home Pages
# ----------

# application home page (will override Website Settings)
# home_page = "login"

# website user home page (by Role)
# role_home_page = {
# 	"Role": "home_page"
# }

# Generators
# ----------

# automatically create page for each record of this doctype
# website_generators = ["Web Page"]

# Jinja
# ----------

# add methods and filters to jinja environment
# jinja = {
# 	"methods": "job_auto_match.utils.jinja_methods",
# 	"filters": "job_auto_match.utils.jinja_filters"
# }

# Installation
# ------------

# before_install = "job_auto_match.install.before_install"
# after_install = "job_auto_match.install.after_install"

# Uninstallation
# ------------

# before_uninstall = "job_auto_match.uninstall.before_uninstall"
# after_uninstall = "job_auto_match.uninstall.after_uninstall"

# Integration Setup
# ------------------
# To set up dependencies/integrations with other apps
# Name of the app being installed is passed as an argument

# before_app_install = "job_auto_match.utils.before_app_install"
# after_app_install = "job_auto_match.utils.after_app_install"

# Integration Cleanup
# -------------------
# To clean up dependencies/integrations with other apps
# Name of the app being uninstalled is passed as an argument

# before_app_uninstall = "job_auto_match.utils.before_app_uninstall"
# after_app_uninstall = "job_auto_match.utils.after_app_uninstall"

# Desk Notifications
# ------------------
# See frappe.core.notifications.get_notification_config

# notification_config = "job_auto_match.notifications.get_notification_config"

# Permissions
# -----------
# Permissions evaluated in scripted ways

# permission_query_conditions = {
# 	"Event": "frappe.desk.doctype.event.event.get_permission_query_conditions",
# }
#
# has_permission = {
# 	"Event": "frappe.desk.doctype.event.event.has_permission",
# }

# DocType Class
# ---------------
# Override standard doctype classes

# override_doctype_class = {
# 	"ToDo": "custom_app.overrides.CustomToDo"
# }

# Document Events
# ---------------
# Hook on document methods and events

 # apps/job_auto_match/job_auto_match/hooks.py

doc_events = {
    "Job Applicant": {
        "after_insert": "job_auto_match.job_auto_match.doctype.job_applicant.job_applicant.enqueue_matching",
        "before_insert" : "job_auto_match.job_auto_match.doctype.job_applicant.job_applicant.validate_unique_application",
        "on_update" : "job_auto_match.job_auto_match.doctype.job_applicant.job_applicant.sync_job_applicant_status"
    }
}


# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"all": [
# 		"job_auto_match.tasks.all"
# 	],
# 	"daily": [
# 		"job_auto_match.tasks.daily"
# 	],
# 	"hourly": [
# 		"job_auto_match.tasks.hourly"
# 	],
# 	"weekly": [
# 		"job_auto_match.tasks.weekly"
# 	],
# 	"monthly": [
# 		"job_auto_match.tasks.monthly"
# 	],
# }

# Testing
# -------

# before_tests = "job_auto_match.install.before_tests"

# Overriding Methods
# ------------------------------
#
# override_whitelisted_methods = {
# 	"frappe.desk.doctype.event.event.get_events": "job_auto_match.event.get_events"
# }
#
# each overriding function accepts a `data` argument;
# generated from the base implementation of the doctype dashboard,
# along with any modifications made in other Frappe apps
# override_doctype_dashboards = {
# 	"Task": "job_auto_match.task.get_dashboard_data"
# }

# exempt linked doctypes from being automatically cancelled
#
# auto_cancel_exempted_doctypes = ["Auto Repeat"]

# Ignore links to specified DocTypes when deleting documents
# -----------------------------------------------------------

# ignore_links_on_delete = ["Communication", "ToDo"]

# Request Events
# ----------------
# before_request = ["job_auto_match.utils.before_request"]
# after_request = ["job_auto_match.utils.after_request"]

# Job Events
# ----------
# before_job = ["job_auto_match.utils.before_job"]
# after_job = ["job_auto_match.utils.after_job"]

# User Data Protection
# --------------------

# user_data_fields = [
# 	{
# 		"doctype": "{doctype_1}",
# 		"filter_by": "{filter_by}",
# 		"redact_fields": ["{field_1}", "{field_2}"],
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_2}",
# 		"filter_by": "{filter_by}",
# 		"partial": 1,
# 	},
# 	{
# 		"doctype": "{doctype_3}",
# 		"strict": False,
# 	},
# 	{
# 		"doctype": "{doctype_4}"
# 	}
# ]

# Authentication and authorization
# --------------------------------

# auth_hooks = [
# 	"job_auto_match.auth.validate"
# ]

# Automatically update python controller files with type annotations for this app.
# export_python_type_annotations = True

# default_log_clearing_doctypes = {
# 	"Logging DocType Name": 30  # days to retain logs
# }

fixtures = [
   
    # Rapports liés au recrutement
    {"doctype": "Report", "filters": [["ref_doctype", "in", [
        "Job Requisition", "Job Opening", "Job Applicant", "Job Offer",
        "Interview", "Appointment"
    ]]]},

    # --- Personnalisations et automatisations ---
    # Champs personnalisés liés au recrutement
    {"doctype": "Custom Field", "filters": [["dt", "in", [
        "Staffing Plan", "Job Requisition", "Job Opening",
        "Job Applicant", "Job Offer", "Interview", "Appointment"
    ]]]},

    # Property Setters (modifications de propriétés sur des champs ou formulaires)
    {"doctype": "Property Setter", "filters": [["doc_type", "in", [
        "Staffing Plan", "Job Requisition", "Job Opening",
        "Job Applicant", "Job Offer", "Interview", "Appointment"
    ]]]},

    # Workflows
    {"doctype": "Workflow", "filters": [["document_type", "in", [
        "Job Requisition", "Job Opening", "Job Applicant", "Job Offer", "Interview", "Appointment"
    ]]]},

    # États de Workflow
    {"doctype": "Workflow State"},

    # Scripts côté serveur
    {"doctype": "Server Script", "filters": [["reference_doctype", "in", [
        "Staffing Plan", "Job Requisition", "Job Opening",
        "Job Applicant", "Job Offer", "Interview", "Appointment"
    ]]]},

    # Scripts côté client
    {"doctype": "Client Script", "filters": [["dt", "in", [
        "Staffing Plan", "Job Requisition", "Job Opening",
        "Job Applicant", "Job Offer", "Interview", "Appointment"
    ]]]},

    # Notifications liées au recrutement
    {"doctype": "Notification", "filters": [["document_type", "in", [
        "Job Applicant", "Job Offer", "Interview", "Appointment"
    ]]]},

    # Alertes email et modèles
    {"doctype": "Email Template", "filters": [["name", "like", "%Job%"]]},

    # Paramétrages automatiques (Auto Email Reports, etc.)
    {"doctype": "Auto Email Report", "filters": [["report", "in", [
        "Job Openings Report", "Job Applicants Report"
    ]]]},

    # Scripts de type Workflow Action
    {"doctype": "Workflow Action Master"}
]
