import frappe
from frappe.model.document import Document


class RPABillUpload(Document):
	def before_insert(self):
		self.uploaded_by = frappe.session.user
