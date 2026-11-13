// CA team: one screen across all allotted clients — what needs doing.
frappe.pages["client-review"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({ parent: wrapper, title: __("Client Review"), single_column: true });
	const $body = $(wrapper).find(".layout-main-section");
	const inr = (v) => format_currency(v || 0, "INR");
	const link = (route, n, label) => n ? `<a href="${route}">${n} ${label}</a>` : `<span class="text-muted">—</span>`;
	const load = async () => {
		$body.html(`<div class="text-muted p-3">${__("Loading…")}</div>`);
		const rows = (await frappe.call({ method: "rpa_integration.books_api.team_overview" })).message || [];
		const enc = encodeURIComponent;
		$body.html(`<div class="cr-wrap">
			<p class="text-muted">${__("Your allotted clients. Click a number to open the list for that client.")}</p>
			<table class="table cr-table"><thead><tr>
				<th>${__("Client")}</th><th>${__("Plans")}</th><th>${__("Bills to enter")}</th><th>${__("Draft entries")}</th>
				<th>${__("Overdue invoices")}</th><th class="text-right">${__("To collect")}</th><th class="text-right">${__("To pay")}</th><th>${__("Last entry")}</th>
			</tr></thead><tbody>
			${rows.map((r) => `<tr>
				<td><b>${frappe.utils.escape_html(r.company)}</b></td>
				<td class="small">${(r.features || []).join(", ")}</td>
				<td>${link(`/app/rpa-bill-upload?company=${enc(r.company)}&status=New`, r.uploads_new, __("waiting"))}</td>
				<td>${link(`/app/sales-invoice?company=${enc(r.company)}&docstatus=0`, r.drafts, __("drafts"))}</td>
				<td>${link(`/app/sales-invoice?company=${enc(r.company)}&status=Overdue`, r.overdue, __("overdue"))}</td>
				<td class="text-right">${inr(r.to_collect)}</td>
				<td class="text-right">${inr(r.to_pay)}</td>
				<td class="small">${r.last_entry ? frappe.datetime.comment_when(r.last_entry) : "—"}</td>
			</tr>`).join("") || `<tr><td colspan="8" class="text-muted">${__("No clients allotted yet.")}</td></tr>`}
			</tbody></table></div>`);
	};
	page.set_primary_action(__("Refresh"), load, "refresh");
	load();
};
