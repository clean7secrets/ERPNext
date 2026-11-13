// Books client experience: clients land on My Business and see short, simple forms.
(function () {
	const isClient = () => frappe.boot && frappe.boot.rpa_client;
	const HOME = "my-business";

	// Only the bare desk home (/desk or /app) sends a client to My Business; every other page is left alone.
	function goHome() {
		try {
			if (!isClient()) return;
			document.body.classList.add("rpa-client");
			const path = window.location.pathname.replace(/\/+$/, "");
			if (path === "/desk" || path === "/app") {
				setTimeout(() => frappe.set_route(HOME), 0);
			}
		} catch (e) {
			console.warn("books_client", e);
		}
	}
	$(document).on("startup", goHome);
	$(document).on("page-change", goHome);

	// Hide what a small business never needs on an invoice or quote.
	const HIDE = {
		"Sales Invoice": ["is_pos", "is_debit_note", "apply_tds", "update_stock", "currency_and_price_list", "accounting_dimensions_section",
			"time_sheet_list", "loyalty_points_redemption", "sales_team_section_break", "section_break2", "subscription_section",
			"more_info_tab", "edit_printing_settings", "scan_barcode", "pricing_rule_details", "packing_list", "advances_section",
			"write_off_section", "einvoice_section", "e_waybill_status", "gst_section", "named_place", "incoterm", "tax_category",
			"shipping_rule", "taxes_and_charges", "connections_tab", "set_posting_time", "posting_time", "cost_center", "project"],
		"Quotation": ["currency_and_price_list", "more_info_tab", "scan_barcode", "pricing_rule_details", "packed_items",
			"shipping_rule", "taxes_and_charges", "tax_category", "incoterm", "named_place", "opportunity", "order_type", "lost_reasons_section"],
	};
	Object.keys(HIDE).forEach((dt) => {
		frappe.ui.form.on(dt, {
			refresh(frm) {
				if (!isClient()) return;
				try {
				HIDE[dt].forEach((f) => frm.fields_dict[f] && frm.toggle_display(f, false));
				if (!frm.is_new() && frm.doc.docstatus === 1 && !frm._rpa_pdf) {
					frm._rpa_pdf = true;
					const fmt = dt === "Quotation" ? "Books Quote - My style" : "Books Invoice - My style";
					frm.add_custom_button(__("Download PDF"), () => window.open(
						`/api/method/frappe.utils.print_format.download_pdf?doctype=${encodeURIComponent(dt)}&name=${encodeURIComponent(frm.doc.name)}&format=${encodeURIComponent(fmt)}&no_letterhead=1`));
				}
				frm.add_custom_button(__("Back to My Business"), () => frappe.set_route(HOME));
				} catch (e) {
					console.warn("books_client form", e);
				}
			},
		});
	});
})();
