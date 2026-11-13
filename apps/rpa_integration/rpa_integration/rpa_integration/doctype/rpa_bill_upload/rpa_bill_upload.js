// CA team: turn an uploaded bill into an expense entry in one step.
frappe.ui.form.on("RPA Bill Upload", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.status !== "New" || !frappe.user.has_role(["Accounts User", "Accounts Manager"])) return;
		frm.add_custom_button(__("Record as expense"), async () => {
			const accounts = await frappe.db.get_list("Account", {
				filters: { company: frm.doc.company, root_type: "Expense", is_group: 0, disabled: 0 }, pluck: "name", limit: 500 });
			const d = new frappe.ui.Dialog({
				title: __("Record as expense"),
				fields: [
					{ fieldname: "category", label: __("Expense account"), fieldtype: "Select", options: accounts.join("\n"), reqd: 1 },
					{ fieldname: "amount", label: __("Amount"), fieldtype: "Currency", reqd: 1, default: frm.doc.amount },
					{ fieldname: "paid_from", label: __("Paid from"), fieldtype: "Select", options: "Cash\nBank", default: frm.doc.paid_from === "Cash" ? "Cash" : "Bank" },
					{ fieldname: "date", label: __("Date"), fieldtype: "Date", default: frm.doc.bill_date || frappe.datetime.get_today() },
				],
				primary_action_label: __("Save entry"),
				primary_action: async (v) => {
					await frappe.call({ method: "rpa_integration.books_api.enter_upload_as_expense", freeze: true,
						args: { upload: frm.doc.name, category: v.category, amount: v.amount, paid_from: v.paid_from, expense_date: v.date } });
					d.hide();
					frm.reload_doc();
				},
			});
			d.show();
		}).addClass("btn-primary");
		frm.add_custom_button(__("Not a bill"), () => frm.set_value("status", "Not a bill").then(() => frm.save()));
	},
});
